"""Lease-based leader election.

The alert-worker runs as several replicas for availability, but alert scanning
must happen exactly once per cycle -- two scanners would race on the same
debounce check and double-alert. So the replicas elect a leader:

  * a candidate becomes leader with SET leader <id> NX PX <ttl>
    (at most one SET can win while the key exists)
  * the leader renews the lease every ttl/3, but only if the key still holds
    its own id (WATCH/MULTI compare-and-set)
  * if the leader dies, its lease expires and the next candidate to try wins;
    a new `term` number is issued on every change of leadership

This is the lease variant of election used by Kubernetes, etcd and ZooKeeper
recipes -- simpler than Bully/Ring because Redis provides the atomic step.
"""

from __future__ import annotations

import json
import time

LEADER_KEY = "acg:leader:alert-worker"
TERM_KEY = "acg:leader:alert-worker:term"
HISTORY_KEY = "acg:leader:alert-worker:history"


class LeaderElector:
    def __init__(self, redis, identity: str, *, ttl_ms: int = 6_000, key: str = LEADER_KEY) -> None:
        self._redis = redis
        self.identity = identity
        self._ttl_ms = ttl_ms
        self._key = key
        self.is_leader = False
        self.term: int | None = None

    def _renew(self) -> bool:
        with self._redis.pipeline(transaction=True) as pipe:
            pipe.watch(self._key)
            if pipe.get(self._key) != self.identity:
                pipe.unwatch()
                return False
            pipe.multi()
            pipe.pexpire(self._key, self._ttl_ms)
            pipe.execute()
            return True

    def tick(self) -> bool:
        """Try to become (or stay) leader. Call every ttl/3. Returns is_leader."""
        if self.is_leader:
            if self._renew():
                return True
            self.is_leader = False  # lost the lease (e.g. paused longer than ttl)
            self.term = None

        if self._redis.set(self._key, self.identity, nx=True, px=self._ttl_ms):
            self.is_leader = True
            self.term = int(self._redis.incr(TERM_KEY))
            self._redis.lpush(
                HISTORY_KEY,
                json.dumps({"leader": self.identity, "term": self.term, "at": time.time()}),
            )
            self._redis.ltrim(HISTORY_KEY, 0, 9)
        return self.is_leader

    def resign(self) -> None:
        """Step down on shutdown so a follower takes over immediately."""
        if self.is_leader and self._renew():
            self._redis.delete(self._key)
        self.is_leader = False
        self.term = None


def current_leader(redis) -> dict:
    holder = redis.get(LEADER_KEY)
    return {
        "leader": holder,
        "ttl_ms": redis.pttl(LEADER_KEY) if holder else None,
        "term": int(redis.get(TERM_KEY) or 0),
        "history": [json.loads(h) for h in redis.lrange(HISTORY_KEY, 0, 9)],
    }
