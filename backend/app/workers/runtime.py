"""Shared plumbing for worker processes: logging, Redis, graceful shutdown."""

from __future__ import annotations

import logging
import signal
import sys
import time

from app.config import settings
from app.distributed.redis_client import get_redis

logger = logging.getLogger("worker")


class Shutdown:
    """Flips to True on SIGTERM/SIGINT -- Kubernetes sends SIGTERM before
    killing a pod, so workers can finish the current batch and hand over."""

    def __init__(self) -> None:
        self.requested = False
        signal.signal(signal.SIGTERM, self._handle)
        signal.signal(signal.SIGINT, self._handle)

    def _handle(self, signum, _frame) -> None:
        logger.info("received signal %s, shutting down", signum)
        self.requested = True


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s [{settings.pod_name}] %(levelname)s %(message)s",
        stream=sys.stdout,
    )


def wait_for_redis(shutdown: Shutdown):
    """Block until Redis answers; pods may start before Redis is ready."""
    if not settings.REDIS_URL:
        logger.error("REDIS_URL is not set; workers need Redis")
        sys.exit(1)
    redis = get_redis()
    while not shutdown.requested:
        try:
            redis.ping()
            return redis
        except Exception as exc:  # noqa: BLE001
            logger.warning("waiting for redis: %s", exc)
            time.sleep(2)
    sys.exit(0)
