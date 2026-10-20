"""AI Cost Governor — gateway service entrypoint (FastAPI).

The same image also runs the workers (see app/workers); this module is the
gateway: proxy data plane + admin API. Several replicas run behind a
Kubernetes Service, and each announces itself through Redis heartbeats.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import engine, init_db
from app.distributed import membership
from app.distributed.lamport import clock
from app.distributed.redis_client import get_redis
from app.routes import admin, auth, cluster, governed, proxy
from app.routes import settings as settings_routes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _heartbeat_loop() -> None:
    """Announce this gateway pod in the cluster membership view."""
    interval = max(1.0, settings.HEARTBEAT_TTL_S / 3)
    while True:
        redis = get_redis()
        if redis is not None:
            try:
                await asyncio.to_thread(
                    membership.heartbeat,
                    redis,
                    pod=settings.pod_name,
                    role="gateway",
                    ttl_s=settings.HEARTBEAT_TTL_S,
                    lamport=clock.value,
                    requests=proxy.served["requests"],
                    usage_mode="stream" if settings.stream_mode else "sync",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("heartbeat failed: %s", exc)
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    # Opt-in, idempotent demo seeding. In Kubernetes the seed Job does this
    # instead, so only one process ever seeds.
    if os.environ.get("SEED_DEMO_ON_STARTUP", "").lower() == "true":
        try:
            from seed_data import seed_if_missing

            seed_if_missing()
        except Exception:
            logger.exception("Demo seed on startup failed")

    task = asyncio.create_task(_heartbeat_loop())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    redis = get_redis()
    if redis is not None:
        with suppress(Exception):
            membership.leave(redis, settings.pod_name)


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "A distributed governance proxy between your developers and the LLM APIs: "
        "per-user tracking, cluster-wide budget caps, and analytics."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Custom response headers must be listed or cross-origin JS can't read them.
    expose_headers=[
        "x-governance-requested-model",
        "x-governance-routed-model",
        "x-governance-original-tokens",
        "x-governance-compressed-tokens",
        "x-governance-token-reduction-pct",
        "x-governance-complexity-tier",
        "x-governance-estimated-savings-usd",
        "x-governance-estimated-savings-pct",
        "x-acg-gateway-pod",
        "x-acg-upstream-pod",
        "x-acg-lamport",
        "x-acg-usage-mode",
        "x-acg-lock-wait-ms",
    ],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(cluster.router)
app.include_router(settings_routes.router)
app.include_router(proxy.router)
app.include_router(governed.router)


@app.get("/", tags=["meta"])
def root():
    return {
        "name": settings.APP_NAME,
        "status": "ok",
        "pod": settings.pod_name,
        "docs": "/docs",
        "proxy": "/v1/org/{org_slug}/chat/completions",
    }


@app.get("/health", tags=["meta"])
def health():
    """Liveness probe: the process is up."""
    return {"status": "healthy", "pod": settings.pod_name}


@app.get("/ready", tags=["meta"])
def ready():
    """Readiness probe: only receive traffic once DB (and Redis, if used) answer."""
    checks = {}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc}"
    redis = get_redis()
    if redis is not None:
        try:
            redis.ping()
            checks["redis"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["redis"] = f"error: {exc}"
    ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ready" if ok else "not_ready", "pod": settings.pod_name, **checks},
    )
