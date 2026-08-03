"""Per-proxy-key rate limiting backed by Upstash Redis.

Redis is optional: without REDIS_URL the limiter is a no-op so local dev and
first deploys work before Upstash is wired up.
"""

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 120  # requests
DEFAULT_WINDOW = 60  # seconds

_redis = None
_unavailable = False


def _get_redis():
    global _redis, _unavailable
    if _unavailable or not settings.REDIS_URL:
        return None
    if _redis is None:
        try:
            import redis

            _redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
            _redis.ping()
        except Exception as exc:  # noqa: BLE001 - never fail a request on limiter issues
            logger.warning("Redis unavailable, rate limiting disabled: %s", exc)
            _unavailable = True
            return None
    return _redis


def check_rate_limit(
    key: str, limit: int = DEFAULT_LIMIT, window: int = DEFAULT_WINDOW
) -> tuple[bool, int]:
    """Fixed-window counter. Returns (allowed, remaining)."""
    client = _get_redis()
    if client is None:
        return True, limit

    redis_key = f"acg:ratelimit:{key}"
    try:
        count = client.incr(redis_key)
        if count == 1:
            client.expire(redis_key, window)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Rate limit check failed, allowing request: %s", exc)
        return True, limit

    return count <= limit, max(0, limit - count)
