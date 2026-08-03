"""Organization registration and admin login."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AdminUser, Organization
from app.schemas import (
    AdminOut,
    LoginRequest,
    OrganizationOut,
    RegisterRequest,
    TokenResponse,
)
from app.services.auth_service import (
    create_access_token,
    get_current_admin,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def proxy_base_url(request: Request, slug: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/v1/org/{slug}"


def org_payload(request: Request, org: Organization) -> OrganizationOut:
    return OrganizationOut(
        id=org.id,
        name=org.name,
        slug=org.slug,
        monthly_budget=org.monthly_budget,
        proxy_base_url=proxy_base_url(request, org.slug),
        has_openai_key=bool(org.openai_api_key_encrypted),
        has_anthropic_key=bool(org.anthropic_api_key_encrypted),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    if db.execute(
        select(Organization).where(Organization.slug == body.org_slug)
    ).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "That organization slug is already taken.")

    if db.execute(
        select(AdminUser).where(AdminUser.email == body.admin_email)
    ).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists.")

    org = Organization(
        name=body.org_name, slug=body.org_slug, monthly_budget=body.monthly_budget
    )
    db.add(org)
    db.flush()

    admin = AdminUser(
        org_id=org.id,
        name=body.admin_name,
        email=body.admin_email,
        password_hash=hash_password(body.password),
    )
    db.add(admin)
    db.commit()
    db.refresh(org)
    db.refresh(admin)

    return TokenResponse(
        access_token=create_access_token(admin),
        admin=AdminOut.model_validate(admin),
        organization=org_payload(request, org),
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    admin = db.execute(
        select(AdminUser).where(AdminUser.email == body.email)
    ).scalar_one_or_none()

    if admin is None or not verify_password(body.password, admin.password_hash):
        # Same message either way — don't leak which emails exist.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")

    org = db.get(Organization, admin.org_id)
    return TokenResponse(
        access_token=create_access_token(admin),
        admin=AdminOut.model_validate(admin),
        organization=org_payload(request, org),
    )


@router.get("/me", response_model=TokenResponse)
def me(request: Request, admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    org = db.get(Organization, admin.org_id)
    return TokenResponse(
        access_token=create_access_token(admin),
        admin=AdminOut.model_validate(admin),
        organization=org_payload(request, org),
    )
