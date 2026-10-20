"""usage-worker: persists usage events from the Redis Stream into Postgres.

Every replica joins the same consumer group, so Redis hands each event to
exactly one worker (load sharing). Delivery is at-least-once:

  * an event is acknowledged (XACK) only after its row is committed;
  * if a worker dies holding unacknowledged events, another worker reclaims
    them after RECLAIM_IDLE_MS with XAUTOCLAIM (fault tolerance);
  * a redelivered event is detected by its `event_id` and not inserted twice
    (idempotent consumer -> exactly-once effect in the database).

Each received event's Lamport timestamp is merged into this worker's clock.

    python -m app.workers.usage_worker
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal, init_db
from app.distributed import events, membership
from app.distributed.lamport import clock
from app.models import UsageLog, User
from app.services import usage_service
from app.workers.runtime import Shutdown, setup_logging, wait_for_redis

logger = logging.getLogger("usage-worker")

RECLAIM_IDLE_MS = 30_000
BATCH = 50
BLOCK_MS = 2_000

stats = {"processed": 0, "duplicates": 0, "reclaimed": 0}


def ensure_group(redis) -> None:
    try:
        redis.xgroup_create(settings.USAGE_STREAM, settings.USAGE_GROUP, id="0", mkstream=True)
        logger.info("created consumer group %s", settings.USAGE_GROUP)
    except Exception as exc:  # noqa: BLE001
        if "BUSYGROUP" not in str(exc):
            raise


def process_event(redis, message_id: str, fields: dict, consumer: str) -> str:
    """Persist one event and ack it. Returns 'stored' | 'duplicate' | 'orphan'."""
    event = events.decode(fields)
    clock.update(event.get("lamport_ts", 0))  # receive event

    outcome = "stored"
    db = SessionLocal()
    try:
        exists = db.execute(
            select(UsageLog.id).where(UsageLog.event_id == event["event_id"]).limit(1)
        ).first()
        user = db.get(User, event["user_id"])
        if exists:
            outcome = "duplicate"
        elif user is None:
            outcome = "orphan"  # user deleted while the event was queued
        else:
            usage_service.record_usage(
                db,
                user=user,
                model=event["model"],
                prompt_tokens=event["prompt_tokens"],
                completion_tokens=event["completion_tokens"],
                request_summary=event.get("request_summary"),
                lamport_ts=event.get("lamport_ts"),
                origin_pod=event.get("origin_pod"),
                processed_by=consumer,
                event_id=event["event_id"],
                **(event.get("governed") or {}),
            )
    finally:
        db.close()

    # Release the reservation exactly once: duplicates already released it.
    if outcome != "duplicate":
        events.release_pending(redis, event)
    redis.xack(settings.USAGE_STREAM, settings.USAGE_GROUP, message_id)

    if outcome == "stored":
        events.remember_recent(
            redis,
            {
                "event_id": event["event_id"],
                "lamport_ts": event.get("lamport_ts"),
                "origin_pod": event.get("origin_pod"),
                "processed_by": consumer,
                "user_id": event["user_id"],
                "model": event["model"],
                "cost_usd": event["cost_usd"],
                "tokens": event["prompt_tokens"] + event["completion_tokens"],
                "persisted_at": time.time(),
            },
        )
    return outcome


def _handle(redis, entries, consumer: str) -> None:
    for message_id, fields in entries:
        try:
            outcome = process_event(redis, message_id, fields, consumer)
        except Exception:  # noqa: BLE001 - leave unacked; it will be reclaimed and retried
            logger.exception("failed to process %s", message_id)
            continue
        if outcome == "duplicate":
            stats["duplicates"] += 1
        else:
            stats["processed"] += 1


def reclaim_stale(redis, consumer: str) -> int:
    """Take over events a crashed worker left unacknowledged."""
    result = redis.xautoclaim(
        settings.USAGE_STREAM, settings.USAGE_GROUP, consumer,
        min_idle_time=RECLAIM_IDLE_MS, start_id="0-0", count=BATCH,
    )
    claimed = result[1] if len(result) > 1 else []
    claimed = [(mid, fields) for mid, fields in claimed if fields]
    if claimed:
        logger.info("reclaimed %d stale event(s)", len(claimed))
        stats["reclaimed"] += len(claimed)
        _handle(redis, claimed, consumer)
    return len(claimed)


def run() -> None:
    setup_logging()
    shutdown = Shutdown()
    redis = wait_for_redis(shutdown)
    init_db()
    ensure_group(redis)

    consumer = settings.pod_name
    logger.info("usage-worker %s consuming %s", consumer, settings.USAGE_STREAM)
    last_beat = last_reclaim = 0.0

    while not shutdown.requested:
        now = time.time()
        try:
            if now - last_beat >= settings.HEARTBEAT_TTL_S / 3:
                membership.heartbeat(
                    redis, pod=consumer, role="usage-worker", ttl_s=settings.HEARTBEAT_TTL_S,
                    lamport=clock.value, **stats,
                )
                last_beat = now
            if now - last_reclaim >= RECLAIM_IDLE_MS / 1000 / 2:
                reclaim_stale(redis, consumer)
                last_reclaim = now

            response = redis.xreadgroup(
                settings.USAGE_GROUP, consumer, {settings.USAGE_STREAM: ">"},
                count=BATCH, block=BLOCK_MS,
            )
            for _stream, entries in response or []:
                _handle(redis, entries, consumer)
        except Exception:  # noqa: BLE001 - keep the worker alive through Redis/DB blips
            logger.exception("worker loop error; retrying")
            time.sleep(2)

    membership.leave(redis, consumer)
    logger.info("stopped")


if __name__ == "__main__":
    run()
