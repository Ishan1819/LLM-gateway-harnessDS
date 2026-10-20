"""alert-worker: leader-elected scanner that raises 80% / 90% cap alerts.

Runs as 2+ replicas for availability; only the elected leader scans. Followers
keep trying for the lease, so when the leader pod is killed one of them takes
over within LEADER_TTL_MS.

    python -m app.workers.alert_worker
"""

from __future__ import annotations

import logging
import os
import time

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal, init_db
from app.distributed import membership
from app.distributed.leader import LeaderElector
from app.models import User
from app.services import alert_service
from app.workers.runtime import Shutdown, setup_logging, wait_for_redis

logger = logging.getLogger("alert-worker")

stats = {"scans": 0, "alerts_created": 0}


def scan_once() -> int:
    """Evaluate every active user's caps once. Alerts are debounced per day."""
    created = 0
    db = SessionLocal()
    try:
        users = db.execute(select(User).where(User.is_active.is_(True))).scalars().all()
        for user in users:
            created += len(alert_service.evaluate_thresholds(db, user))
    finally:
        db.close()
    return created


def run() -> None:
    setup_logging()
    shutdown = Shutdown()
    redis = wait_for_redis(shutdown)
    init_db()

    pod = settings.pod_name
    elector = LeaderElector(redis, pod, ttl_ms=settings.LEADER_TTL_MS)
    tick = settings.LEADER_TTL_MS / 1000 / 3
    last_scan = 0.0
    was_leader = False
    # A fresh process sits out one lease period before campaigning. When a
    # crashed leader is restarted in place (same pod name), this lets the
    # surviving follower take over instead of the old leader racing back.
    campaign_at = time.monotonic() + settings.LEADER_TTL_MS / 1000

    while not shutdown.requested:
        try:
            if membership.consume_stop(redis, pod):
                # Simulated crash from the Cluster page: exit without resigning
                # or leaving, so failover happens only through lease expiry.
                logger.warning("stop requested from dashboard; crashing now")
                os._exit(1)

            is_leader = elector.tick() if time.monotonic() >= campaign_at else False
            if is_leader != was_leader:
                logger.info(
                    "%s leader (term %s)", "became" if is_leader else "lost", elector.term
                )
                was_leader = is_leader

            if is_leader and time.time() - last_scan >= settings.ALERT_SCAN_INTERVAL_S:
                created = scan_once()
                stats["scans"] += 1
                stats["alerts_created"] += created
                last_scan = time.time()
                if created:
                    logger.info("scan raised %d alert(s)", created)

            membership.heartbeat(
                redis, pod=pod, role="alert-worker", ttl_s=settings.HEARTBEAT_TTL_S,
                is_leader=str(is_leader).lower(), term=elector.term, **stats,
            )
        except Exception:  # noqa: BLE001
            logger.exception("alert loop error; retrying")
        time.sleep(tick)

    elector.resign()
    membership.leave(redis, pod)
    logger.info("stopped")


if __name__ == "__main__":
    run()
