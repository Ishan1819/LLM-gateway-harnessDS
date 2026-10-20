"""Shared Redis clients.

Redis is the coordination layer of the cluster: message queue, locks, leader
lease, heartbeats and rate limits all live there. It is optional for a single
process -- without REDIS_URL every caller gets `None` and falls back to the
non-distributed behaviour, which is how the unit tests and plain local dev run.

Clients are created lazily and never cached as "unavailable": in Kubernetes the
gateway may start before Redis is ready, and it should start working as soon as
Redis does rather than staying degraded until a restart.
"""

from __future__ import annotations

from app.config import settings

_sync = None
_async = None


def get_redis():
    """Synchronous client (workers, admin status, cap checks)."""
    global _sync
    if _sync is None and settings.REDIS_URL:
        import redis

        _sync = redis.from_url(
            settings.REDIS_URL, decode_responses=True, socket_timeout=5, socket_connect_timeout=3
        )
    return _sync


def get_async_redis():
    """Asyncio client for the request path, so waiting on a lock never blocks
    the gateway's event loop."""
    global _async
    if _async is None and settings.REDIS_URL:
        import redis.asyncio as aioredis

        _async = aioredis.from_url(
            settings.REDIS_URL, decode_responses=True, socket_timeout=5, socket_connect_timeout=3
        )
    return _async


def set_clients(sync=None, async_=None) -> None:
    """Inject clients (tests use fakeredis)."""
    global _sync, _async
    _sync = sync
    _async = async_
