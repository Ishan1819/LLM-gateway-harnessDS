"""Where a finished request's usage goes.

  sync mode   -> written straight to Postgres on its own session, alerts
                 evaluated inline (single process, tests, local dev).
  stream mode -> published to the Redis Stream with a Lamport timestamp and
                 reserved as pending spend; a usage-worker persists it and the
                 elected alert-worker leader evaluates alerts.

If Redis fails mid-publish the usage is written synchronously instead, so a
coordination outage costs latency, never lost billing data.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.distributed import events
from app.distributed.lamport import clock
from app.distributed.redis_client import get_redis
from app.models import User
from app.services import alert_service, usage_service
from app.utils.pricing import calculate_cost

logger = logging.getLogger(__name__)


def _write_sync(user_id: int, model: str, prompt_tokens: int, completion_tokens: int,
                preview: str, governed: dict) -> None:
    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user is None:
            return
        usage_service.record_usage(
            db,
            user=user,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            request_summary=preview,
            origin_pod=settings.pod_name,
            **governed,
        )
        alert_service.evaluate_thresholds(db, user)
    except Exception:  # noqa: BLE001 - accounting must never break the response
        logger.exception("Failed to record usage for user %s", user_id)
    finally:
        db.close()


def account_usage(
    *,
    user: User,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    preview: str,
    governed: dict | None = None,
) -> dict:
    """Record one request's usage. Returns provenance for response headers."""
    governed = governed or {}
    if prompt_tokens + completion_tokens <= 0:
        return {"mode": "skipped"}

    redis = get_redis() if settings.stream_mode else None
    if redis is not None:
        lamport_ts = clock.tick()  # send event
        event = {
            "user_id": user.id,
            "team_id": user.team_id,
            "org_id": user.org_id,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": calculate_cost(model, prompt_tokens, completion_tokens),
            "request_summary": preview,
            "governed": governed,
            "lamport_ts": lamport_ts,
            "origin_pod": settings.pod_name,
        }
        try:
            message_id = events.publish_usage(redis, settings.USAGE_STREAM, event)
            return {"mode": "stream", "lamport_ts": lamport_ts, "message_id": message_id}
        except Exception:  # noqa: BLE001
            logger.exception("Redis publish failed; falling back to a synchronous write")

    _write_sync(user.id, model, prompt_tokens, completion_tokens, preview, governed)
    return {"mode": "sync", "lamport_ts": clock.tick()}
