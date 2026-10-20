"""Lamport logical clock.

Pods have no shared physical clock we can trust for ordering, so every usage
event is stamped with a Lamport timestamp instead:

  * local event / send:  C = C + 1, stamp the message with C
  * receive message(t):  C = max(C, t) + 1

If event a happened-before event b, then L(a) < L(b). The usage-worker merges
the timestamps it receives from all gateway pods, and the admin Cluster page
orders recent events by (lamport_ts, origin_pod) -- a consistent total order
across the whole cluster.
"""

from __future__ import annotations

import threading


class LamportClock:
    def __init__(self, start: int = 0) -> None:
        self._value = start
        self._mutex = threading.Lock()

    @property
    def value(self) -> int:
        return self._value

    def tick(self) -> int:
        """Local event or message send."""
        with self._mutex:
            self._value += 1
            return self._value

    def update(self, received: int) -> int:
        """Message receive: jump past the sender's clock."""
        with self._mutex:
            self._value = max(self._value, int(received)) + 1
            return self._value


# One clock per process (per pod).
clock = LamportClock()
