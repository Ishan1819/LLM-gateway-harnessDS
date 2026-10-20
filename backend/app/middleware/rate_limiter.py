"""Per-proxy-key rate limiting, shared by every gateway pod through Redis.

Because the counter lives in Redis rather than in process memory, the limit
holds across the whole cluster: three gateway replicas do not triple an
employee's allowance. Without REDIS_URL the limiter is a no-op.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.distributed.redis_client import get_redis

logger = logging.getLogger(__name__)

DEFAULT_WINDOW = 60  # seconds


def check_rate_limit(
    key: str, limit: int | None = None, window: int = DEFAULT_WINDOW
) -> tuple[bool, int]:
    """Fixed-window counter. Returns (allowed, remaining)."""
    limit = limit or settings.RATE_LIMIT_PER_MIN
    client = get_redis()
    if client is None:
        return True, limit

    redis_key = f"acg:ratelimit:{key}"
    try:
        count = client.incr(redis_key)
        if count == 1:
            client.expire(redis_key, window)
    except Exception as exc:  # noqa: BLE001 - never fail a request on limiter issues
        logger.warning("Rate limit check failed, allowing request: %s", exc)
        return True, limit

    return count <= limit, max(0, limit - count)
