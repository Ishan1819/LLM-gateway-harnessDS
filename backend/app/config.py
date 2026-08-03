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

    # --- Governance ---
    ALERT_THRESHOLDS: str = "0.8,0.9"

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
