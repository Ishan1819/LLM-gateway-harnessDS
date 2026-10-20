"""Governed proxy endpoint: compression -> complexity scoring -> model
recommendation -> routing -> LLM -> cost/savings accounting, in one request.

Sits alongside the byte-faithful `/chat/completions` / `/messages`
passthrough (routes/proxy.py) and shares its distributed request flow: the
same per-user lock, cap check, RPC retries and stream-based accounting.

Non-streaming only for this MVP; the plain proxy still handles streaming.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.routes.proxy import (
    authenticate,
    check_caps,
    distributed_headers,
    rate_limit,
    release_connection,
    served,
    user_critical_section,
)
from app.services import proxy_service
from app.services.accounting import account_usage
from app.services.cost_engine import finalize_actual_cost
from app.services.governance_service import run_governance

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/org/{org_slug}/governed", tags=["governed-proxy"])


@router.post("/chat/completions")
async def governed_chat_completions(
    org_slug: str,
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
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
            detail={
                "error": {
                    "message": "Request body must be valid JSON.",
                    "type": "invalid_request_error",
                }
            },
        ) from None

    if payload.get("stream"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "message": "Streaming isn't supported on the governed endpoint yet; "
                    "use /chat/completions for streaming.",
                    "type": "invalid_request_error",
                }
            },
        )

    requested_model = payload.get("model") or ""
    result = run_governance(payload, requested_model)

    routed_model = result.routing.recommended_model
    provider = result.routing.recommended_provider
    upstream_path = "messages" if provider == "anthropic" else "chat/completions"

    try:
        api_key = proxy_service.resolve_api_key(org, provider)
    except proxy_service.UpstreamKeyMissing as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"message": str(exc), "type": "configuration_error"}},
        ) from exc

    routed_payload = dict(payload)
    routed_payload["model"] = routed_model
    extra_headers = proxy_service.passthrough_headers(dict(request.headers), provider)
    preview = proxy_service.prompt_preview(payload)

    async with user_critical_section(user.id) as lock:
        check_caps(user.id)
        status_code, body, usage, upstream_pod = await proxy_service.forward(
            provider=provider,
            path=upstream_path,
            payload=routed_payload,
            api_key=api_key,
            extra_headers=extra_headers,
        )

        accounting = {"mode": "skipped"}
        if usage.total > 0:
            finalize_actual_cost(result.cost, usage.prompt_tokens, usage.completion_tokens)
            accounting = account_usage(
                user=user,
                model=routed_model,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                preview=preview,
                governed={
                    "requested_model": requested_model,
                    "original_tokens": result.compression.original_tokens,
                    "compressed_tokens": result.compression.compressed_tokens,
                    "token_reduction_pct": result.compression.reduction_pct,
                    "complexity_score": result.complexity.score,
                    "complexity_tier": result.complexity.tier,
                    "compression_savings_usd": result.cost.compression_savings_usd,
                    "routing_savings_usd": result.cost.routing_savings_usd,
                    "total_savings_usd": result.cost.total_savings_usd,
                    "techniques_applied": result.compression.techniques_applied,
                },
            )

    response = JSONResponse(
        status_code=status_code,
        content=body,
        headers=distributed_headers(upstream_pod, accounting, lock),
    )
    response.headers["x-governance-requested-model"] = requested_model
    response.headers["x-governance-routed-model"] = routed_model
    response.headers["x-governance-original-tokens"] = str(result.compression.original_tokens)
    response.headers["x-governance-compressed-tokens"] = str(result.compression.compressed_tokens)
    response.headers["x-governance-token-reduction-pct"] = str(result.compression.reduction_pct)
    response.headers["x-governance-complexity-tier"] = str(result.complexity.tier)
    response.headers["x-governance-estimated-savings-usd"] = str(result.cost.total_savings_usd)
    response.headers["x-governance-estimated-savings-pct"] = str(result.cost.total_savings_pct)
    return response
