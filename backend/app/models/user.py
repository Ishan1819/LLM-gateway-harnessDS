import enum
import secrets
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

PROXY_KEY_PREFIX = "acg-"


def generate_proxy_api_key() -> str:
    """Per-user proxy key. Looks and behaves like any other bearer key to the SDK."""
    return f"{PROXY_KEY_PREFIX}{secrets.token_urlsafe(32)}"


class UserRole(str, enum.Enum):
    admin = "admin"
    member = "member"


class User(Base):
    """A developer whose LLM traffic flows through the proxy."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), index=True, nullable=True
    )

    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default=UserRole.member.value, nullable=False)

    proxy_api_key: Mapped[str] = mapped_column(
        String(80), unique=True, index=True, default=generate_proxy_api_key, nullable=False
    )

    monthly_cap: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    daily_cap: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    organization = relationship("Organization", back_populates="users")
    team = relationship("Team", back_populates="users")


class AdminUser(Base):
    """Dashboard login. Separate from `User`, which is a proxy identity."""

    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    organization = relationship("Organization", back_populates="admins")
