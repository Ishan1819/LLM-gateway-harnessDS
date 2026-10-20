"""Tests for the distributed building blocks: Lamport clock, distributed lock,
leader election, stream-based usage pipeline, pending-spend caps, simulator.

Redis is replaced by fakeredis (sync + async clients sharing one fake server),
so these run without any external service.
"""

from __future__ import annotations

import asyncio

import fakeredis
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.database import Base, SessionLocal, engine, get_db
from app.distributed import events, membership
from app.distributed.lamport import LamportClock
from app.distributed.leader import LEADER_KEY, LeaderElector, current_leader
from app.distributed.lock import DistributedLock
from app.distributed.redis_client import set_clients
from app.main import app
from app.models import Organization, UsageLog, User
from app.models.user import AdminUser
from app.routes import cluster
from app.services import cap_service, proxy_service
from app.services.accounting import account_usage
from app.services.auth_service import hash_password
from app.services.encryption_service import encrypt
from app.utils.model_catalog import get_tier
from app.utils.pricing import get_rate
from app.workers import usage_worker


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------
@pytest.fixture()
def fake_redis():
    server = fakeredis.FakeServer()
    sync = fakeredis.FakeRedis(server=server, decode_responses=True)
    async_ = fakeredis.FakeAsyncRedis(server=server, decode_responses=True)
    set_clients(sync, async_)
    yield sync, async_
    set_clients(None, None)


@pytest.fixture()
def stream_mode(monkeypatch, fake_redis):
    monkeypatch.setattr(settings, "REDIS_URL", "redis://fake")
    monkeypatch.setattr(settings, "USAGE_MODE", "stream")
    return fake_redis


@pytest.fixture()
def db_session():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def org_user(db_session):
    org = Organization(
        name="Dist Org", slug="dist-org", monthly_budget=0.0,
        openai_api_key_encrypted=encrypt("sk-fake"),
    )
    db_session.add(org)
    db_session.commit()
    user = User(org_id=org.id, name="Employee One", email="e1@example.com")
    admin = AdminUser(org_id=org.id, email="boss@example.com",
                      password_hash=hash_password("password123"), name="Boss")
    db_session.add_all([user, admin])
    db_session.commit()
    db_session.refresh(user)
    return org, user


# --------------------------------------------------------------------------
# Lamport clock
# --------------------------------------------------------------------------
def test_lamport_tick_is_monotonic():
    c = LamportClock()
    assert [c.tick(), c.tick(), c.tick()] == [1, 2, 3]


def test_lamport_receive_jumps_past_sender():
    sender, receiver = LamportClock(), LamportClock()
    for _ in range(10):
        sender.tick()
    sent = sender.tick()  # 11
    assert receiver.update(sent) == 12
    assert receiver.update(3) == 13  # an older message never moves the clock back


def test_lamport_happened_before_implies_smaller_timestamp():
    a, b = LamportClock(), LamportClock()
    send = a.tick()
    recv = b.update(send)
    after = b.tick()
    assert send < recv < after


# --------------------------------------------------------------------------
# Distributed lock (mutual exclusion)
# --------------------------------------------------------------------------
def test_lock_is_exclusive_and_released(fake_redis):
    _, r = fake_redis

    async def scenario():
        first = DistributedLock(r, "user:1", wait_ms=50)
        second = DistributedLock(r, "user:1", wait_ms=50)
        assert await first.acquire()
        assert not await second.acquire()  # held by first
        assert await first.release()
        assert await second.acquire()
        await second.release()

    asyncio.run(scenario())


def test_lock_never_releases_someone_elses_lock(fake_redis):
    _, r = fake_redis

    async def scenario():
        mine = DistributedLock(r, "user:2", ttl_ms=50)
        assert await mine.acquire()
        await asyncio.sleep(0.1)  # lease expires
        theirs = DistributedLock(r, "user:2", wait_ms=50)
        assert await theirs.acquire()
        assert not await mine.release()  # token mismatch: must not delete theirs
        assert await r.get(theirs.key) is not None
        await theirs.release()

    asyncio.run(scenario())


def test_lock_prevents_lost_updates_under_concurrency(fake_redis):
    """Classic read-modify-write race: with the lock no increment is lost."""
    _, r = fake_redis

    async def worker():
        async with DistributedLock(r, "counter", wait_ms=5_000, retry_ms=1):
            value = int(await r.get("shared") or 0)
            await asyncio.sleep(0.001)  # widen the race window
            await r.set("shared", value + 1)

    async def scenario():
        await asyncio.gather(*(worker() for _ in range(25)))
        return int(await r.get("shared"))

    assert asyncio.run(scenario()) == 25


# --------------------------------------------------------------------------
# Leader election
# --------------------------------------------------------------------------
def test_only_one_leader_at_a_time(fake_redis):
    r, _ = fake_redis
    a, b = LeaderElector(r, "pod-a"), LeaderElector(r, "pod-b")
    assert a.tick() is True
    assert b.tick() is False
    assert a.tick() is True  # renews its own lease
    assert current_leader(r)["leader"] == "pod-a"


def test_follower_takes_over_when_leader_resigns(fake_redis):
    r, _ = fake_redis
    a, b = LeaderElector(r, "pod-a"), LeaderElector(r, "pod-b")
    a.tick()
    term_a = a.term
    a.resign()
    assert b.tick() is True
    assert b.term == term_a + 1
    assert current_leader(r)["leader"] == "pod-b"


def test_follower_takes_over_when_leader_crashes(fake_redis):
    r, _ = fake_redis
    a, b = LeaderElector(r, "pod-a"), LeaderElector(r, "pod-b")
    a.tick()
    r.delete(LEADER_KEY)  # lease expired: pod-a stopped renewing
    assert b.tick() is True
    assert a.tick() is False  # old leader notices it lost the lease
    assert a.is_leader is False


# --------------------------------------------------------------------------
# Membership
# --------------------------------------------------------------------------
def test_membership_lists_live_nodes_and_drops_expired(fake_redis):
    r, _ = fake_redis
    membership.heartbeat(r, pod="gw-1", role="gateway", ttl_s=10, requests=3)
    membership.heartbeat(r, pod="gw-2", role="gateway", ttl_s=10)
    r.delete(membership.NODE_PREFIX + "gw-2")  # heartbeat expired
    nodes = membership.list_nodes(r)
    assert [n["pod"] for n in nodes] == ["gw-1"]
    assert nodes[0]["requests"] == "3"


# --------------------------------------------------------------------------
# Stream pipeline: gateway publish -> usage-worker persist
# --------------------------------------------------------------------------
def _drain(r, consumer="worker-test"):
    usage_worker.ensure_group(r)
    response = r.xreadgroup(settings.USAGE_GROUP, consumer, {settings.USAGE_STREAM: ">"}, count=100)
    outcomes = []
    for _stream, entries in response or []:
        for message_id, fields in entries:
            outcomes.append(usage_worker.process_event(r, message_id, fields, consumer))
    return outcomes


def test_stream_mode_defers_the_write_to_the_worker(stream_mode, db_session, org_user):
    r, _ = stream_mode
    _, user = org_user

    result = account_usage(user=user, model="gpt-4o-mini", prompt_tokens=1000,
                           completion_tokens=500, preview="hello")
    assert result["mode"] == "stream"
    assert db_session.execute(select(UsageLog)).first() is None  # not written yet
    assert r.xlen(settings.USAGE_STREAM) == 1

    pending = events.pending_spend(r, user_id=user.id, team_id=None, org_id=user.org_id)
    assert pending["user"] > 0

    assert _drain(r) == ["stored"]
    db_session.expire_all()
    row = db_session.execute(select(UsageLog)).scalar_one()
    assert row.processed_by == "worker-test"
    assert row.lamport_ts == result["lamport_ts"]
    assert events.pending_spend(r, user_id=user.id, team_id=None, org_id=user.org_id)["user"] == 0


def test_redelivered_event_is_not_stored_twice(stream_mode, db_session, org_user):
    r, _ = stream_mode
    _, user = org_user
    account_usage(user=user, model="gpt-4o", prompt_tokens=100, completion_tokens=50, preview="x")

    usage_worker.ensure_group(r)
    [(_s, [(message_id, fields)])] = r.xreadgroup(
        settings.USAGE_GROUP, "w1", {settings.USAGE_STREAM: ">"}, count=1
    )
    assert usage_worker.process_event(r, message_id, fields, "w1") == "stored"
    # Simulate an at-least-once redelivery of the same message.
    assert usage_worker.process_event(r, message_id, fields, "w2") == "duplicate"
    db_session.expire_all()
    assert len(db_session.execute(select(UsageLog)).scalars().all()) == 1


def test_crashed_workers_events_are_reclaimed(stream_mode, db_session, org_user, monkeypatch):
    r, _ = stream_mode
    _, user = org_user
    account_usage(user=user, model="gpt-4o", prompt_tokens=100, completion_tokens=50, preview="x")

    usage_worker.ensure_group(r)
    # "dead-worker" reads the event and dies without acking it.
    r.xreadgroup(settings.USAGE_GROUP, "dead-worker", {settings.USAGE_STREAM: ">"}, count=1)
    monkeypatch.setattr(usage_worker, "RECLAIM_IDLE_MS", 0)

    assert usage_worker.reclaim_stale(r, "healthy-worker") == 1
    db_session.expire_all()
    row = db_session.execute(select(UsageLog)).scalar_one()
    assert row.processed_by == "healthy-worker"
    assert r.xpending(settings.USAGE_STREAM, settings.USAGE_GROUP)["pending"] == 0


def test_cap_check_counts_pending_spend(stream_mode, db_session, org_user):
    r, _ = stream_mode
    _, user = org_user
    user.monthly_cap = 0.01
    db_session.commit()

    assert cap_service.check(db_session, user).allowed
    # $0.02 reserved by another gateway pod but not yet persisted.
    r.set(f"{events.PENDING_PREFIX}user:{user.id}", "0.02")
    decision = cap_service.check(db_session, user)
    assert not decision.allowed
    assert decision.scope == "user_monthly"


# --------------------------------------------------------------------------
# Pricing fix
# --------------------------------------------------------------------------
def test_dated_snapshots_use_the_longest_matching_prefix():
    assert get_rate("gpt-4o-mini-2024-07-18") == get_rate("gpt-4o-mini")
    assert get_rate("gpt-4.1-mini-2025-04-14") == get_rate("gpt-4.1-mini")
    assert get_rate("gpt-4o-2024-11-20") == get_rate("gpt-4o")
    assert get_tier("gpt-4o-mini-2024-07-18") == 1


# --------------------------------------------------------------------------
# Admin cluster API + Employee Simulator (end to end through the ASGI app)
# --------------------------------------------------------------------------
@pytest.fixture()
def client(db_session, monkeypatch):
    def override_get_db():
        yield db_session

    async def fake_forward(*, provider, path, payload, api_key, extra_headers):
        body = {"choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10}}
        return 200, body, proxy_service.Usage(20, 10), "mock-llm-0"

    monkeypatch.setattr(proxy_service, "forward", fake_forward)

    # Route the simulator's "Service" calls back into this same app.
    real_client = httpx.AsyncClient

    def asgi_client(*args, **kwargs):
        kwargs.pop("limits", None)
        return real_client(*args, transport=httpx.ASGITransport(app=app),
                           base_url="http://gateway", **kwargs)

    monkeypatch.setattr(cluster.httpx, "AsyncClient", asgi_client)
    monkeypatch.setattr(settings, "GATEWAY_INTERNAL_URL", "http://gateway")

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _admin_headers(client):
    token = client.post(
        "/api/auth/login", json={"email": "boss@example.com", "password": "password123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_simulator_sends_requests_as_the_employee(client, org_user, db_session):
    _, user = org_user
    headers = _admin_headers(client)
    response = client.post(
        "/api/admin/cluster/simulate",
        json={"user_ids": [user.id], "count": 5, "concurrency": 1},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status_counts"] == {"200": 5}
    assert data["by_upstream_pod"] == {"mock-llm-0": 5}
    assert all(r["gateway_pod"] for r in data["results"])
    db_session.expire_all()
    assert len(db_session.execute(select(UsageLog)).scalars().all()) == 5


def test_simulator_rejects_employees_of_another_org(client, org_user, db_session):
    other = Organization(name="Other", slug="other-org", monthly_budget=0.0)
    db_session.add(other)
    db_session.commit()
    stranger = User(org_id=other.id, name="Stranger", email="s@example.com")
    db_session.add(stranger)
    db_session.commit()

    response = client.post(
        "/api/admin/cluster/simulate",
        json={"user_ids": [stranger.id], "count": 1},
        headers=_admin_headers(client),
    )
    assert response.status_code == 404


def test_cluster_status_without_redis_reports_sync_mode(client, org_user):
    response = client.get("/api/admin/cluster/status", headers=_admin_headers(client))
    assert response.status_code == 200
    body = response.json()
    assert body["redis"] is False
    assert body["usage_mode"] == "sync"


def test_cluster_status_with_redis_shows_nodes_and_leader(client, org_user, stream_mode):
    r, _ = stream_mode
    membership.heartbeat(r, pod="gateway-abc", role="gateway", ttl_s=10)
    LeaderElector(r, "alert-worker-1").tick()
    body = client.get("/api/admin/cluster/status", headers=_admin_headers(client)).json()
    assert body["redis"] is True
    assert body["leader"]["leader"] == "alert-worker-1"
    assert any(n["pod"] == "gateway-abc" for n in body["nodes"])


def test_stop_node_flags_only_alert_workers(client, org_user, stream_mode):
    r, _ = stream_mode
    membership.heartbeat(r, pod="alert-worker-1", role="alert-worker", ttl_s=10)
    membership.heartbeat(r, pod="gateway-abc", role="gateway", ttl_s=10)
    LeaderElector(r, "alert-worker-1").tick()
    headers = _admin_headers(client)

    response = client.post("/api/admin/cluster/nodes/alert-worker-1/stop", headers=headers)
    assert response.status_code == 200
    assert response.json()["was_leader"] is True
    assert membership.consume_stop(r, "alert-worker-1") is True
    assert membership.consume_stop(r, "alert-worker-1") is False  # consumed once

    assert client.post("/api/admin/cluster/nodes/gateway-abc/stop", headers=headers).status_code == 400
    assert client.post("/api/admin/cluster/nodes/ghost/stop", headers=headers).status_code == 404
