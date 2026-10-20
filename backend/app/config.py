"""Application configuration, loaded entirely from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- Core ---
    APP_NAME: str = "AI Cost Governor"
    ENVIRONMENT: str = "development"

    # --- Database ---
    # Render/Supabase hand out postgres:// URLs; normalized in database.py
    DATABASE_URL: str = "sqlite:///./ai_cost_governor.db"

    # --- Redis (Upstash) ---
    # Optional. If unset, rate limiting degrades gracefully to a no-op.
    REDIS_URL: str | None = None

    # --- Auth ---
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 12

    # --- Encryption ---
    # Fernet key (44-char urlsafe base64). Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ENCRYPTION_KEY: str = ""

    # --- CORS ---
    # Comma-separated list of allowed origins (your Vercel domain, localhost, ...)
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # --- Upstream LLM providers ---
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com/v1"
    ANTHROPIC_VERSION: str = "2023-06-01"
    UPSTREAM_TIMEOUT_SECONDS: float = 600.0

    UPSTREAM_RETRIES: int = 2  # extra attempts on connect errors / 5xx

    # --- Governance ---
    ALERT_THRESHOLDS: str = "0.8,0.9"

    # --- Distributed runtime ---
    # Identity of this process in the cluster. Kubernetes injects the pod name
    # through the downward API; locally it falls back to the hostname.
    POD_NAME: str = ""
    # "sync" writes usage straight to the DB (single process, tests).
    # "stream" publishes a usage event to Redis for usage-workers to persist.
    USAGE_MODE: str = "sync"
    RATE_LIMIT_PER_MIN: int = 600  # per proxy key, enforced cluster-wide
    USAGE_STREAM: str = "acg:usage-events"
    USAGE_GROUP: str = "usage-workers"
    # Distributed lock around cap check -> forward -> pending-spend update.
    LOCK_TTL_MS: int = 30_000
    LOCK_WAIT_MS: int = 15_000
    # Alert-worker leader lease.
    LEADER_TTL_MS: int = 6_000
    ALERT_SCAN_INTERVAL_S: float = 10.0
    # Cluster membership heartbeats.
    HEARTBEAT_TTL_S: int = 10
    # Where the admin Employee Simulator sends traffic so it is load-balanced
    # across gateway pods (a Kubernetes Service name in the cluster).
    GATEWAY_INTERNAL_URL: str = "http://127.0.0.1:8000"

    @property
    def pod_name(self) -> str:
        import socket

        return self.POD_NAME or socket.gethostname()

    @property
    def stream_mode(self) -> bool:
        return self.USAGE_MODE.lower() == "stream" and bool(self.REDIS_URL)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def alert_threshold_list(self) -> list[float]:
        return [float(t) for t in self.ALERT_THRESHOLDS.split(",") if t.strip()]

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
