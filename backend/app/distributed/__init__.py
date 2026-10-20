"""Distributed-systems building blocks shared by the gateway and the workers.

    redis_client  one shared sync + async Redis connection per process
    lamport       Lamport logical clock (Unit III: logical clocks)
    lock          Redis distributed lock (Unit III: mutual exclusion)
    leader        lease-based leader election (Unit III: election algorithms)
    membership    heartbeat registry of live pods (Unit II: names/identifiers)
    events        usage events on a Redis Stream (Unit II: message-oriented communication)
"""
