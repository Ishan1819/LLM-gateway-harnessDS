"""Usage events on a Redis Stream (message-oriented communication).

The gateway does not write usage to Postgres on the request path any more. It
publishes an event and returns; usage-workers in a consumer group persist it.
That decouples request latency from database latency, and lets the workers be
scaled, stopped and restarted independently -- events wait in the stream.

Between publish and persist, the event's cost is not yet visible in the DB, so
the gateway also adds it to `pending spend` counters that the cap check reads.
The worker subtracts it once the row is committed.
"""

from __future__ import annotations

import json
import uuid

PENDING_PREFIX = "acg:pending:"
RECENT_KEY = "acg:recent-events"
RECENT_LIMIT = 40
PENDING_TTL_S = 86_400  # self-heal if a counter is ever orphaned


def pending_keys(*, user_id: int, team_id: int | None, org_id: int) -> list[str]:
    keys = [f"{PENDING_PREFIX}user:{user_id}", f"{PENDING_PREFIX}org:{org_id}"]
    if team_id is not None:
        keys.append(f"{PENDING_PREFIX}team:{team_id}")
    return keys


def encode(event: dict) -> dict[str, str]:
    """Stream fields are flat strings; nested values go through JSON."""
    return {k: json.dumps(v) for k, v in event.items()}


def decode(fields: dict[str, str]) -> dict:
    return {k: json.loads(v) for k, v in fields.items()}


def publish_usage(redis, stream: str, event: dict) -> str:
    """XADD the event and reserve its cost as pending spend, atomically."""
    event = {"event_id": uuid.uuid4().hex, **event}
    keys = pending_keys(user_id=event["user_id"], team_id=event.get("team_id"), org_id=event["org_id"])
    pipe = redis.pipeline(transaction=True)
    pipe.xadd(stream, encode(event), maxlen=100_000, approximate=True)
    for key in keys:
        pipe.incrbyfloat(key, event["cost_usd"])
        pipe.expire(key, PENDING_TTL_S)
    message_id = pipe.execute()[0]
    return message_id


def release_pending(redis, event: dict) -> None:
    keys = pending_keys(user_id=event["user_id"], team_id=event.get("team_id"), org_id=event["org_id"])
    pipe = redis.pipeline()
    for key in keys:
        pipe.incrbyfloat(key, -float(event["cost_usd"]))
    pipe.execute()


def pending_spend(redis, *, user_id: int, team_id: int | None, org_id: int) -> dict[str, float]:
    keys = pending_keys(user_id=user_id, team_id=team_id, org_id=org_id)
    values = redis.mget(keys)
    out = {"user": 0.0, "org": 0.0, "team": 0.0}
    for key, value in zip(keys, values):
        scope = key[len(PENDING_PREFIX):].split(":")[0]
        out[scope] = max(0.0, float(value or 0.0))
    return out


def remember_recent(redis, summary: dict) -> None:
    """Small rolling log for the admin Cluster page."""
    pipe = redis.pipeline()
    pipe.lpush(RECENT_KEY, json.dumps(summary))
    pipe.ltrim(RECENT_KEY, 0, RECENT_LIMIT - 1)
    pipe.execute()


def recent_events(redis) -> list[dict]:
    rows = [json.loads(r) for r in redis.lrange(RECENT_KEY, 0, RECENT_LIMIT - 1)]
    # Lamport order, pod name as tie-breaker -> one consistent total order.
    return sorted(rows, key=lambda r: (r.get("lamport_ts", 0), r.get("origin_pod", "")), reverse=True)
