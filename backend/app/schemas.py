"""Request/response models for the admin API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# --- Auth ---
class RegisterRequest(BaseModel):
    org_name: str = Field(min_length=2, max_length=200)
    org_slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*$")
    admin_name: str = Field(min_length=1, max_length=200)
    admin_email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    monthly_budget: float = Field(default=0.0, ge=0)
    # Self-serve signup is Free-only; paid tiers go through sales.
    plan: str = Field(default="free", pattern=r"^(free|standard|premium)$")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    admin: "AdminOut"
    organization: "OrganizationOut"


class AdminOut(BaseModel):
    id: int
    name: str
    email: str

    class Config:
        from_attributes = True


class OrganizationOut(BaseModel):
    id: int
    name: str
    slug: str
    monthly_budget: float
    proxy_base_url: str | None = None
    has_openai_key: bool = False
    has_anthropic_key: bool = False
    plan: str = "free"
    plan_name: str = "Free"
    features: list[str] = []
    max_users: int = 0
    history_days: int = 0

    class Config:
        from_attributes = True


# --- Teams ---
class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    monthly_cap: float = Field(default=0.0, ge=0)
    daily_cap: float = Field(default=0.0, ge=0)


class TeamOut(BaseModel):
    id: int
    name: str
    monthly_cap: float
    daily_cap: float

    class Config:
        from_attributes = True


# --- Users ---
class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    team_id: int | None = None
    role: str = "member"
    monthly_cap: float = Field(default=0.0, ge=0)
    daily_cap: float = Field(default=0.0, ge=0)


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    team_id: int | None
    role: str
    monthly_cap: float
    daily_cap: float
    is_active: bool
    proxy_api_key: str

    class Config:
        from_attributes = True


class CapUpdate(BaseModel):
    monthly_cap: float | None = Field(default=None, ge=0)
    daily_cap: float | None = Field(default=None, ge=0)
    is_active: bool | None = None


class BulkCapUpdate(BaseModel):
    user_ids: list[int]
    monthly_cap: float | None = Field(default=None, ge=0)
    daily_cap: float | None = Field(default=None, ge=0)
    is_active: bool | None = None


# --- Settings ---
class KeysUpdate(BaseModel):
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    monthly_budget: float | None = Field(default=None, ge=0)


class KeysStatus(BaseModel):
    openai: str | None = None
    anthropic: str | None = None
    monthly_budget: float
    proxy_base_url: str


# --- Alerts ---
class AlertOut(BaseModel):
    id: int
    type: str
    message: str
    is_read: bool
    created_at: datetime
    user_id: int | None
    team_id: int | None

    class Config:
        from_attributes = True


TokenResponse.model_rebuild()
