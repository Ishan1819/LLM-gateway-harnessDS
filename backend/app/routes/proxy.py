"""OpenAI- and Anthropic-compatible proxy endpoints.

A developer changes nothing but `base_url`:

    OpenAI(base_url="https://<host>/v1/org/demo", api_key="<proxy key>")
    Anthropic(base_url="https://<host>/v1/org/demo", api_key="<proxy key>")
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.middleware.rate_limiter import check_rate_limit
from app.models import Organization, User
from app.services import alert_service, cap_service, proxy_service, usage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/org/{org_slug}", tags=["proxy"])


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


def _enforce(db: Session, user: User) -> None:
    allowed, _remaining = check_rate_limit(user.proxy_api_key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": {"message": "Rate limit exceeded. Slow down and retry shortly.",
                              "type": "rate_limit_error"}},
        )

    decision = cap_service.check(db, user)
    if not decision.allowed:
        alert_service.record_limit_reached(db, user, decision.scope or "unknown")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": {"message": decision.reason, "type": "budget_exceeded"}},
        )


def _record(user_id: int, model: str, usage: proxy_service.Usage, preview: str) -> None:
    """Write the usage row on its own session so it survives a streamed response."""
    if usage.total <= 0:
        return
    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user is None:
            return
        usage_service.record_usage(
            db,
            user=user,
            model=model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            request_summary=preview,
        )
        alert_service.evaluate_thresholds(db, user)
    except Exception:  # noqa: BLE001 - accounting must never break the response
        logger.exception("Failed to record usage for user %s", user_id)
    finally:
        db.close()


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
    _enforce(db, user)

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
    user_id = user.id

    if payload.get("stream"):
        return await _handle_stream(
            provider=provider,
            path=upstream_path,
            payload=payload,
            api_key=api_key,
            extra_headers=extra_headers,
            user_id=user_id,
            model=model,
            preview=preview,
        )

    status_code, body, usage = await proxy_service.forward(
        provider=provider,
        path=upstream_path,
        payload=payload,
        api_key=api_key,
        extra_headers=extra_headers,
    )
    _record(user_id, model, usage, preview)
    return JSONResponse(status_code=status_code, content=body)


async def _handle_stream(
    *,
    provider: str,
    path: str,
    payload: dict,
    api_key: str,
    extra_headers: dict[str, str],
    user_id: int,
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
            _record(user_id, model, usage, preview)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
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
