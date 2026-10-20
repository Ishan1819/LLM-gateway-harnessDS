"""Distributed mutual exclusion on Redis.

Several gateway pods serve the same employee at once. Without coordination,
two pods can both read "spent $0.99 of a $1.00 cap", both allow the request,
and the cap is overshot. A per-user lock makes check -> forward -> reserve
spend a critical section that only one pod at a time can be in.

Algorithm (single-Redis lock, as used by Redlock's building block):
  acquire:  SET lock:<name> <random token> NX PX <ttl>   (retry until wait expires)
  release:  delete the key only if it still holds *our* token
            (WATCH/MULTI, so a lock that expired and was taken by another pod
            is never released by us)
The TTL is the fault-tolerance part: if the holder pod crashes mid-section, the
lock frees itself instead of blocking that employee forever.
"""

from __future__ import annotations

import asyncio
import secrets
import time

LOCK_PREFIX = "acg:lock:"
STATS_KEY = "acg:stats:lock"


class LockTimeout(Exception):
    """Could not enter the critical section within the wait budget."""


class DistributedLock:
    def __init__(self, redis, name: str, *, ttl_ms: int = 30_000, wait_ms: int = 15_000,
                 retry_ms: int = 25) -> None:
        self._redis = redis
        self.key = LOCK_PREFIX + name
        self._ttl_ms = ttl_ms
        self._wait_ms = wait_ms
        self._retry_ms = retry_ms
        self._token = secrets.token_hex(16)
        self.acquired = False
        self.waited_ms = 0.0

    async def acquire(self) -> bool:
        started = time.monotonic()
        deadline = started + self._wait_ms / 1000
        contended = False
        while True:
            if await self._redis.set(self.key, self._token, nx=True, px=self._ttl_ms):
                self.acquired = True
                self.waited_ms = (time.monotonic() - started) * 1000
                await self._redis.hincrby(STATS_KEY, "acquired", 1)
                if contended:
                    await self._redis.hincrby(STATS_KEY, "contended", 1)
                return True
            contended = True
            if time.monotonic() >= deadline:
                await self._redis.hincrby(STATS_KEY, "timeouts", 1)
                return False
            await asyncio.sleep(self._retry_ms / 1000)

    async def release(self) -> bool:
        if not self.acquired:
            return False
        self.acquired = False
        async with self._redis.pipeline(transaction=True) as pipe:
            await pipe.watch(self.key)
            if await pipe.get(self.key) != self._token:
                await pipe.unwatch()
                return False  # expired and re-taken by someone else: not ours to free
            pipe.multi()
            pipe.delete(self.key)
            await pipe.execute()
            return True

    async def __aenter__(self) -> "DistributedLock":
        if not await self.acquire():
            raise LockTimeout(self.key)
        return self

    async def __aexit__(self, *exc) -> None:
        await self.release()
