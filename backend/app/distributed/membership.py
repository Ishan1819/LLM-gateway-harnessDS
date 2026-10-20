"""Cluster membership via heartbeats.

Each pod (gateway, usage-worker, alert-worker) periodically writes a small
hash `acg:node:<pod name>` with a TTL. A pod is "alive" while its key exists;
when a pod crashes it simply stops renewing and drops out of the view after
HEARTBEAT_TTL_S -- the same failure-detector idea as gossip/heartbeat
protocols. Pods are named by their Kubernetes pod name (a location-independent
identifier), never by IP.
"""

from __future__ import annotations

import time

NODES_SET = "acg:nodes"
NODE_PREFIX = "acg:node:"

# Wall-clock started_at per process, reported for display only.
_started_at = time.time()


def heartbeat(redis, *, pod: str, role: str, ttl_s: int, **fields) -> None:
    key = NODE_PREFIX + pod
    data = {"pod": pod, "role": role, "started_at": _started_at, "last_seen": time.time()}
    data.update({k: v for k, v in fields.items() if v is not None})
    pipe = redis.pipeline()
    pipe.hset(key, mapping={k: str(v) for k, v in data.items()})
    pipe.expire(key, ttl_s)
    pipe.sadd(NODES_SET, pod)
    pipe.execute()


def list_nodes(redis) -> list[dict]:
    nodes = []
    for pod in sorted(redis.smembers(NODES_SET)):
        data = redis.hgetall(NODE_PREFIX + pod)
        if not data:
            redis.srem(NODES_SET, pod)  # heartbeat expired: pod is gone
            continue
        nodes.append(data)
    return nodes


def leave(redis, pod: str) -> None:
    redis.delete(NODE_PREFIX + pod)
    redis.srem(NODES_SET, pod)


# Failure injection for the viva: the dashboard asks a pod to crash, and the
# pod polls for the request on its next loop. The key expires on its own if
# the pod is already gone.
STOP_PREFIX = "acg:stop:"


def request_stop(redis, pod: str, ttl_s: int = 30) -> None:
    redis.set(STOP_PREFIX + pod, "1", ex=ttl_s)


def consume_stop(redis, pod: str) -> bool:
    """True once if a stop was requested for this pod (DEL is atomic)."""
    return redis.delete(STOP_PREFIX + pod) == 1
