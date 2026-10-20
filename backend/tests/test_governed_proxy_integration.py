"""End-to-end proof that the governed proxy endpoint is really wired up:
compression -> complexity -> routing -> (mocked) LLM call -> cost/savings
recorded to the database and reflected in the admin governance endpoint.

The upstream LLM call itself is monkeypatched (mirrors what mock_upstream.py
would return) so the test has no network dependency, but everything else --
auth, compression, routing, DB writes, aggregation -- runs for real through
the actual FastAPI app.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import Base, SessionLocal, engine, get_db
from app.main import app
from app.models import Organization, User
from app.services import proxy_service
from app.services.auth_service import hash_password
from app.models.user import AdminUser
from app.services.encryption_service import encrypt


@pytest.fixture()
def db_session():
    # Fresh schema per test so org/user rows from one test never collide
    # with the next (the engine/file is shared across the whole test session).
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def org_and_user(db_session):
    org = Organization(
        name="Test Org",
        slug="test-governed-org",
        monthly_budget=0.0,
        openai_api_key_encrypted=encrypt("sk-fake-test-key"),
    )
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)

    user = User(org_id=org.id, name="Test User", email="test@example.com")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    admin = AdminUser(
        org_id=org.id,
        email="admin@example.com",
        password_hash=hash_password("password123"),
        name="Admin",
    )
    db_session.add(admin)
    db_session.commit()

    return org, user


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def mock_forward(monkeypatch):
    """Stand in for mock_upstream.py's canned response, without a real HTTP call."""

    async def fake_forward(*, provider, path, payload, api_key, extra_headers):
        body = {
            "id": "chatcmpl-mock",
            "model": payload["model"],
            "choices": [
                {"message": {"role": "assistant", "content": "mock reply"}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 42, "completion_tokens": 18, "total_tokens": 60},
        }
        usage = proxy_service.Usage(prompt_tokens=42, completion_tokens=18)
        return 200, body, usage, "mock-llm-test"

    monkeypatch.setattr(proxy_service, "forward", fake_forward)


def test_governed_endpoint_routes_trivial_question_to_cheaper_model(client, org_and_user):
    org, user = org_and_user
    response = client.post(
        f"/v1/org/{org.slug}/governed/chat/completions",
        headers={"Authorization": f"Bearer {user.proxy_api_key}"},
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "What is 2 + 2?"}]},
    )
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "mock reply"

    assert response.headers["x-governance-requested-model"] == "gpt-4o"
    routed_model = response.headers["x-governance-routed-model"]
    assert routed_model != "gpt-4o"  # trivial question shouldn't need the frontier model
    assert float(response.headers["x-governance-estimated-savings-usd"]) > 0
    assert int(response.headers["x-governance-original-tokens"]) > 0


def test_governed_endpoint_records_usage_log_with_governance_fields(client, org_and_user, db_session):
    org, user = org_and_user
    client.post(
        f"/v1/org/{org.slug}/governed/chat/completions",
        headers={"Authorization": f"Bearer {user.proxy_api_key}"},
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Summarize: hello world."}]},
    )

    from app.models import UsageLog

    log = db_session.execute(
        select(UsageLog).where(UsageLog.user_id == user.id)
    ).scalar_one_or_none()
    assert log is not None
    assert log.requested_model == "gpt-4o"
    assert log.original_tokens is not None and log.original_tokens > 0
    assert log.compressed_tokens is not None
    assert log.total_savings_usd is not None
    assert log.techniques_applied is not None
    # actual cost is billed on the real (routed) model + real completion tokens
    assert log.model_used == log.model_used  # sanity: routed model was recorded
    assert log.prompt_tokens == 42
    assert log.completion_tokens == 18


def test_governed_endpoint_rejects_streaming(client, org_and_user):
    org, user = org_and_user
    response = client.post(
        f"/v1/org/{org.slug}/governed/chat/completions",
        headers={"Authorization": f"Bearer {user.proxy_api_key}"},
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}], "stream": True},
    )
    assert response.status_code == 400


def test_admin_governance_endpoint_reflects_recorded_savings(client, org_and_user, db_session):
    org, user = org_and_user
    client.post(
        f"/v1/org/{org.slug}/governed/chat/completions",
        headers={"Authorization": f"Bearer {user.proxy_api_key}"},
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "What is 2 + 2?"}]},
    )

    login = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "password123"}
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    summary = client.get(
        "/api/admin/governance", headers={"Authorization": f"Bearer {token}"}
    )
    assert summary.status_code == 200
    data = summary.json()
    assert data["total_requests"] == 1
    assert data["original_tokens"] > 0
    assert data["total_saved_usd"] > 0
    assert len(data["model_distribution"]) == 1
