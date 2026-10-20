"""Admin view into the distributed runtime, plus the Employee Simulator.

    GET  /api/admin/cluster/status      live pods, leader, stream backlog, locks, Lamport-ordered events
    POST /api/admin/cluster/simulate    send requests *as employees* through the gateway Service
    POST /api/admin/cluster/nodes/{pod}/stop  crash an alert-worker (leader failover demo)
    POST /api/admin/cluster/reset-stats clear lock counters and the recent-event log

The simulator never talks to a pod directly: it calls GATEWAY_INTERNAL_URL
(the Kubernetes Service), with a fresh connection per request, so traffic is
spread across gateway replicas exactly as real employee traffic would be.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from collections import Counter

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.distributed import events, leader, membership
from app.distributed.lamport import clock
from app.distributed.lock import STATS_KEY as LOCK_STATS_KEY
from app.distributed.redis_client import get_redis
from app.models import AdminUser, Organization, User
from app.services.auth_service import get_current_admin

router = APIRouter(prefix="/api/admin/cluster", tags=["cluster"])


def _stream_info(redis) -> dict:
    stream, group = settings.USAGE_STREAM, settings.USAGE_GROUP
    info = {"name": stream, "group": group, "length": 0, "pending": 0, "lag": None, "consumers": []}
    if not redis.exists(stream):
        return info
    info["length"] = redis.xlen(stream)
    for g in redis.xinfo_groups(stream):
        if g.get("name") == group:
            info["pending"] = g.get("pending", 0)
            info["lag"] = g.get("lag")
            info["last_delivered_id"] = g.get("last-delivered-id")
    try:
        info["consumers"] = [
            {"name": c["name"], "pending": c["pending"], "idle_ms": c["idle"]}
            for c in redis.xinfo_consumers(stream, group)
        ]
    except Exception:  # noqa: BLE001 - group not created yet
        pass
    return info


@router.get("/status")
def cluster_status(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    redis = get_redis()
    base = {
        "served_by": settings.pod_name,
        "usage_mode": "stream" if settings.stream_mode else "sync",
        "gateway_lamport": clock.value,
    }
    if redis is None:
        return {**base, "redis": False, "nodes": [], "leader": None, "stream": None,
                "locks": {}, "recent_events": []}
    try:
        redis.ping()
    except Exception as exc:  # noqa: BLE001
        return {**base, "redis": False, "error": str(exc), "nodes": [], "leader": None,
                "stream": None, "locks": {}, "recent_events": []}

    org_users = {
        u.id: u.name
        for u in db.execute(select(User).where(User.org_id == admin.org_id)).scalars()
    }
    recent = [
        {**e, "user": org_users[e["user_id"]]}
        for e in events.recent_events(redis)
        if e.get("user_id") in org_users
    ]

    return {
        **base,
        "redis": True,
        "nodes": membership.list_nodes(redis),
        "leader": leader.current_leader(redis),
        "stream": _stream_info(redis),
        "locks": {k: int(v) for k, v in redis.hgetall(LOCK_STATS_KEY).items()},
        "recent_events": recent,
    }


@router.post("/nodes/{pod}/stop")
def stop_node(pod: str, admin: AdminUser = Depends(get_current_admin)):
    """Crash one alert-worker to demonstrate leader failover.

    The worker exits without giving up its lease, like a real crash, and
    Kubernetes (or compose's restart policy) starts it again.
    """
    redis = get_redis()
    if redis is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Redis is not configured.")
    node = redis.hgetall(membership.NODE_PREFIX + pod)
    if not node:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No live pod with that name.")
    if node.get("role") != "alert-worker":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only alert-workers can be stopped here.")
    membership.request_stop(redis, pod)
    return {"ok": True, "pod": pod, "was_leader": leader.current_leader(redis)["leader"] == pod}


@router.post("/reset-stats")
def reset_stats(admin: AdminUser = Depends(get_current_admin)):
    redis = get_redis()
    if redis is not None:
        redis.delete(LOCK_STATS_KEY, events.RECENT_KEY)
    return {"ok": True}


class SimulateRequest(BaseModel):
    user_ids: list[int] = Field(min_length=1, max_length=100)
    count: int = Field(default=20, ge=1, le=300)
    concurrency: int = Field(default=10, ge=1, le=50)
    model: str = Field(default="gpt-4o-mini", max_length=120)
    prompt: str = Field(default="Summarize the quarterly churn report in three bullets.",
                        min_length=1, max_length=4000)
    endpoint: str = Field(default="proxy", pattern="^(proxy|governed)$")


async def _one(client: httpx.AsyncClient, url: str, key: str, user: User, body: dict, index: int):
    started = time.perf_counter()
    try:
        response = await client.post(url, json=body, headers={"Authorization": f"Bearer {key}"})
        latency = (time.perf_counter() - started) * 1000
        error = None
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail") or response.json()
                error = (detail.get("error") or {}).get("message") if isinstance(detail, dict) else str(detail)
            except Exception:  # noqa: BLE001
                error = response.text[:200]
        h = response.headers
        return {
            "index": index,
            "user_id": user.id,
            "user": user.name,
            "status": response.status_code,
            "latency_ms": round(latency, 1),
            "gateway_pod": h.get("x-acg-gateway-pod"),
            "upstream_pod": h.get("x-acg-upstream-pod"),
            "lamport": int(h["x-acg-lamport"]) if h.get("x-acg-lamport") else None,
            "lock_wait_ms": float(h["x-acg-lock-wait-ms"]) if h.get("x-acg-lock-wait-ms") else None,
            "usage_mode": h.get("x-acg-usage-mode"),
            "error": error,
        }
    except httpx.HTTPError as exc:
        return {
            "index": index, "user_id": user.id, "user": user.name, "status": 0,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "gateway_pod": None, "upstream_pod": None, "lamport": None,
            "lock_wait_ms": None, "usage_mode": None, "error": str(exc),
        }


@router.post("/simulate")
async def simulate(
    body: SimulateRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Act as one or more employees and fire `count` requests at the gateway."""
    org: Organization = db.get(Organization, admin.org_id)
    users = db.execute(
        select(User).where(User.id.in_(body.user_ids), User.org_id == admin.org_id)
    ).scalars().all()
    if not users:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No matching employees in your organization.")
    # Detach and return the connection before awaiting the burst: these
    # requests come back into this same pod, and they need pool connections.
    for row in (org, *users):
        db.expunge(row)
    db.close()

    path = "governed/chat/completions" if body.endpoint == "governed" else "chat/completions"
    url = f"{settings.GATEWAY_INTERNAL_URL.rstrip('/')}/v1/org/{org.slug}/{path}"
    payload = {
        "model": body.model,
        "max_tokens": 256,
        "messages": [{"role": "user", "content": body.prompt}],
    }

    semaphore = asyncio.Semaphore(body.concurrency)
    # No keep-alive: each request opens a new connection, which is what lets
    # the Service's load balancing pick a (possibly different) pod every time.
    limits = httpx.Limits(max_keepalive_connections=0, max_connections=body.concurrency)
    started = time.perf_counter()

    async with httpx.AsyncClient(timeout=60, limits=limits) as client:
        async def run(i: int):
            user = users[i % len(users)]  # round-robin across selected employees
            async with semaphore:
                return await _one(client, url, user.proxy_api_key, user, payload, i)

        results = await asyncio.gather(*(run(i) for i in range(body.count)))

    elapsed = (time.perf_counter() - started) * 1000
    latencies = sorted(r["latency_ms"] for r in results if r["status"] == 200)

    def pct(p: float):
        if not latencies:
            return None
        return latencies[min(len(latencies) - 1, int(round(p * (len(latencies) - 1))))]

    return {
        "requested": body.count,
        "elapsed_ms": round(elapsed, 1),
        "throughput_rps": round(body.count / (elapsed / 1000), 1) if elapsed else None,
        "status_counts": dict(Counter(str(r["status"]) for r in results)),
        "by_gateway_pod": dict(Counter(r["gateway_pod"] or "—" for r in results)),
        "by_upstream_pod": dict(Counter(r["upstream_pod"] or "—" for r in results)),
        "latency_ms": {
            "p50": pct(0.5),
            "p95": pct(0.95),
            "mean": round(statistics.mean(latencies), 1) if latencies else None,
        },
        "simulated_from": settings.pod_name,
        "results": results,
    }
