"""AI Cost Governor — FastAPI entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routes import admin, auth, proxy
from app.routes import settings as settings_routes

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "A governance proxy between your developers and the LLM APIs. "
        "Clients bring their own provider keys; this layer adds tracking, "
        "budget caps, and analytics."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(settings_routes.router)
app.include_router(proxy.router)


@app.get("/", tags=["meta"])
def root():
    return {
        "name": settings.APP_NAME,
        "status": "ok",
        "docs": "/docs",
        "proxy": "/v1/org/{org_slug}/chat/completions",
    }


@app.get("/health", tags=["meta"])
def health():
    return {"status": "healthy"}
