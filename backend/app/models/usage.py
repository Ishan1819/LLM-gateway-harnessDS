from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UsageLog(Base):
    """One row per proxied request. Prompt content is never stored in full."""

    __tablename__ = "usage_logs"
    # Every cap check sums spend for one user/team/org since a period start;
    # these make that a range scan instead of a scan of the owner's history.
    __table_args__ = (
        Index("ix_usage_user_ts", "user_id", "timestamp"),
        Index("ix_usage_team_ts", "team_id", "timestamp"),
        Index("ix_usage_org_ts", "org_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), index=True, nullable=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    model_used: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Privacy first: first 100 characters of the prompt, nothing more.
    request_summary: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # --- AI Cost Governance extensions ---
    # Nullable: only populated for requests that went through the governed
    # pipeline (compression + complexity scoring + routing), not plain
    # byte-faithful proxying via /chat/completions or /messages.
    requested_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    original_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compressed_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_reduction_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    complexity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    complexity_tier: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compression_savings_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    routing_savings_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_savings_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    techniques_applied: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # --- Distributed pipeline provenance ---
    # Null for rows written synchronously (single-process mode, seed data).
    lamport_ts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    origin_pod: Mapped[str | None] = mapped_column(String(120), nullable=True)  # gateway that served it
    processed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)  # worker that persisted it
    # Idempotency key: a redelivered stream message must not create a second row.
    event_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )
