"""OpenAI- and Anthropic-compatible proxy endpoints (the gateway's data plane).

A developer changes nothing but `base_url`:

    OpenAI(base_url="https://<host>/v1/org/demo", api_key="<proxy key>")
    Anthropic(base_url="https://<host>/v1/org/demo", api_key="<proxy key>")

Per request, across however many gateway pods are running:

    authenticate -> rate limit -> [ per-user distributed lock:
        cap check (DB spend + pending spend) -> RPC to provider -> account usage ]

Response headers name the gateway pod and the provider pod that served the
call, plus the Lamport timestamp of the usage event, so load balancing and
event ordering are visible from the admin dashboard.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.distributed.lock import DistributedLock
from app.distributed.redis_client import get_async_redis
from app.middleware.rate_limiter import check_rate_limit
from app.models import Organization, User
from app.services import alert_service, cap_service, proxy_service
from app.services.accounting import account_usage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/org/{org_slug}", tags=["proxy"])

# Requests served by this pod, reported in its heartbeat.
served = {"requests": 0}


def _extract_proxy_key(authorization: str | None, x_api_key: str | None) -> str:
    """Accept both auth styles so either SDK works unchanged."""
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if x_api_key:
        return x_api_key.strip()
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error": {
                "message": "Missing proxy API key. Send it as `Authorization: Bearer <key>` "
                "or `x-api-key: <key>`.",
                "type": "authentication_error",
            }
        },
    )


def authenticate(
    org_slug: str,
    db: Session,
    authorization: str | None,
    x_api_key: str | None,
) -> tuple[Organization, User]:
    key = _extract_proxy_key(authorization, x_api_key)

    org = db.execute(
        select(Organization).where(Organization.slug == org_slug)
    ).scalar_one_or_none()
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"message": f"Unknown organization '{org_slug}'.",
                              "type": "not_found_error"}},
        )

    user = db.execute(
        select(User).where(User.proxy_api_key == key, User.org_id == org.id)
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"message": "Invalid proxy API key for this organization.",
                              "type": "authentication_error"}},
        )

    return org, user


def rate_limit(user: User) -> None:
    allowed, _remaining = check_rate_limit(user.proxy_api_key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": {"message": "Rate limit exceeded. Slow down and retry shortly.",
                              "type": "rate_limit_error"}},
        )


def release_connection(db: Session, *objects) -> None:
    """Detach the loaded rows and hand the DB connection back to the pool.

    Proxy handlers are async and spend most of their life awaiting (the lock,
    the upstream RPC). If the request session kept its connection across those
    awaits, a burst larger than the pool would block the event loop on
    checkout while the connection holders can't resume -- a deadlock. So the
    session is released before any await, and the cap check uses its own
    short-lived session.
    """
    for obj in objects:
        db.expunge(obj)
    db.close()


def check_caps(user_id: int) -> None:
    """Cap check on a fresh, short-lived session (no await while it is open)."""
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        decision = cap_service.check(db, user)
        if not decision.allowed:
            alert_service.record_limit_reached(db, user, decision.scope or "unknown")
    finally:
        db.close()
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": {"message": decision.reason, "type": "budget_exceeded"}},
        )


def _enforce(db: Session, user: User) -> None:
    """Rate limit + cap check (kept for callers outside a critical section)."""
    rate_limit(user)
    check_caps(user.id)


@asynccontextmanager
async def user_critical_section(user_id: int):
    """Mutual exclusion per employee across all gateway pods.

    Without Redis (single process) there is nothing to coordinate with, so this
    is a no-op. If Redis is unreachable we degrade to no lock rather than
    failing the request.
    """
    redis = get_async_redis()
    if redis is None:
        yield None
        return

    lock = DistributedLock(
        redis, f"user:{user_id}", ttl_ms=settings.LOCK_TTL_MS, wait_ms=settings.LOCK_WAIT_MS
    )
    try:
        acquired = await lock.acquire()
    except Exception:  # noqa: BLE001
        logger.warning("Lock service unavailable; continuing without mutual exclusion")
        yield None
        return

    if not acquired:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": {"message": "Too many concurrent requests for this account; retry.",
                              "type": "lock_timeout"}},
        )
    try:
        yield lock
    finally:
        try:
            await lock.release()
        except Exception:  # noqa: BLE001 - TTL frees it anyway
            logger.warning("Lock release failed for %s", lock.key)


def distributed_headers(upstream_pod: str | None, accounting: dict, lock) -> dict[str, str]:
    headers = {"x-acg-gateway-pod": settings.pod_name}
    if upstream_pod:
        headers["x-acg-upstream-pod"] = upstream_pod
    if accounting.get("lamport_ts") is not None:
        headers["x-acg-lamport"] = str(accounting["lamport_ts"])
    headers["x-acg-usage-mode"] = accounting.get("mode", "skipped")
    if lock is not None:
        headers["x-acg-lock-wait-ms"] = f"{lock.waited_ms:.1f}"
    return headers


async def _handle(
    *,
    org_slug: str,
    upstream_path: str,
    request: Request,
    db: Session,
    authorization: str | None,
    x_api_key: str | None,
    force_provider: str | None = None,
):
    org, user = authenticate(org_slug, db, authorization, x_api_key)
    release_connection(db, org, user)
    rate_limit(user)
    served["requests"] += 1

    try:
        payload = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"message": "Request body must be valid JSON.",
                              "type": "invalid_request_error"}},
        ) from None

    model = payload.get("model") or ""
    provider = force_provider or proxy_service.detect_provider(model)

    try:
        api_key = proxy_service.resolve_api_key(org, provider)
    except proxy_service.UpstreamKeyMissing as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"message": str(exc), "type": "configuration_error"}},
        ) from exc

    extra_headers = proxy_service.passthrough_headers(dict(request.headers), provider)
    preview = proxy_service.prompt_preview(payload)

    if payload.get("stream"):
        # A stream can last minutes, so the lock covers only the cap check.
        async with user_critical_section(user.id):
            check_caps(user.id)
        return await _handle_stream(
            provider=provider,
            path=upstream_path,
            payload=payload,
            api_key=api_key,
            extra_headers=extra_headers,
            user=user,
            model=model,
            preview=preview,
        )

    async with user_critical_section(user.id) as lock:
        check_caps(user.id)
        status_code, body, usage, upstream_pod = await proxy_service.forward(
            provider=provider,
            path=upstream_path,
            payload=payload,
            api_key=api_key,
            extra_headers=extra_headers,
        )
        accounting = account_usage(
            user=user,
            model=model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            preview=preview,
        )

    return JSONResponse(
        status_code=status_code,
        content=body,
        headers=distributed_headers(upstream_pod, accounting, lock),
    )


async def _handle_stream(
    *,
    provider: str,
    path: str,
    payload: dict,
    api_key: str,
    extra_headers: dict[str, str],
    user: User,
    model: str,
    preview: str,
):
    client, stream_ctx = proxy_service.stream_forward(
        provider=provider,
        path=path,
        payload=payload,
        api_key=api_key,
        extra_headers=extra_headers,
    )

    async def event_stream():
        usage = proxy_service.Usage()
        try:
            async with stream_ctx as upstream:
                async for line in upstream.aiter_lines():
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data and data != "[DONE]":
                            try:
                                usage = proxy_service.merge_stream_usage(
                                    provider, json.loads(data), usage
                                )
                            except json.JSONDecodeError:
                                pass
                    yield f"{line}\n"
        finally:
            await client.aclose()
            account_usage(
                user=user,
                model=model,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                preview=preview,
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "cache-control": "no-cache",
            "x-accel-buffering": "no",
            "x-acg-gateway-pod": settings.pod_name,
        },
    )


@router.post("/chat/completions")
async def openai_chat_completions(
    org_slug: str,
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
):
    """OpenAI-compatible. Routes to Anthropic automatically for `claude-*` models."""
    model = ""
    try:
        model = (await request.json()).get("model", "")
    except Exception:  # noqa: BLE001 - body is re-read and validated in _handle
        pass

    provider = proxy_service.detect_provider(model)
    upstream_path = "messages" if provider == "anthropic" else "chat/completions"

    return await _handle(
        org_slug=org_slug,
        upstream_path=upstream_path,
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
    )


@router.post("/messages")
async def anthropic_messages(
    org_slug: str,
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
):
    """Anthropic Messages API compatible."""
    return await _handle(
        org_slug=org_slug,
        upstream_path="messages",
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        force_provider="anthropic",
    )


@router.get("/models")
async def list_models(
    org_slug: str,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
):
    """Some SDK helpers probe /models on startup; keep them happy."""
    from app.utils.pricing import list_models as priced_models

    authenticate(org_slug, db, authorization, x_api_key)
    return {
        "object": "list",
        "data": [
            {"id": m["model"], "object": "model", "owned_by": m["provider"]}
            for m in priced_models()
        ],
    }
