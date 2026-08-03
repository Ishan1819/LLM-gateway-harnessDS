"""Organization settings — provider API keys and budget."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AdminUser, Organization
from app.schemas import KeysStatus, KeysUpdate
from app.services.auth_service import get_current_admin
from app.services.encryption_service import decrypt, encrypt, mask
from app.utils.pricing import list_models

router = APIRouter(prefix="/api/admin/settings", tags=["settings"])


def _proxy_base_url(request: Request, slug: str) -> str:
    return f"{str(request.base_url).rstrip('/')}/v1/org/{slug}"


def _masked(encrypted: str | None) -> str | None:
    if not encrypted:
        return None
    try:
        return mask(decrypt(encrypted))
    except ValueError:
        return "unreadable — re-enter key"


@router.get("/keys", response_model=KeysStatus)
def get_keys(
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Returns masked keys only. Plaintext never leaves the proxy path."""
    org: Organization = db.get(Organization, admin.org_id)
    return KeysStatus(
        openai=_masked(org.openai_api_key_encrypted),
        anthropic=_masked(org.anthropic_api_key_encrypted),
        monthly_budget=org.monthly_budget,
        proxy_base_url=_proxy_base_url(request, org.slug),
    )


@router.put("/keys", response_model=KeysStatus)
def update_keys(
    body: KeysUpdate,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    org: Organization = db.get(Organization, admin.org_id)

    try:
        if body.openai_api_key is not None:
            org.openai_api_key_encrypted = (
                encrypt(body.openai_api_key.strip()) if body.openai_api_key.strip() else None
            )
        if body.anthropic_api_key is not None:
            org.anthropic_api_key_encrypted = (
                encrypt(body.anthropic_api_key.strip())
                if body.anthropic_api_key.strip()
                else None
            )
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc)) from exc

    if body.monthly_budget is not None:
        org.monthly_budget = body.monthly_budget

    db.commit()
    db.refresh(org)

    return KeysStatus(
        openai=_masked(org.openai_api_key_encrypted),
        anthropic=_masked(org.anthropic_api_key_encrypted),
        monthly_budget=org.monthly_budget,
        proxy_base_url=_proxy_base_url(request, org.slug),
    )


@router.get("/pricing")
def get_pricing(admin: AdminUser = Depends(get_current_admin)):
    """The rate card the cost engine uses. Edit app/utils/pricing.py to change it."""
    return {"unit": "USD per 1M tokens", "models": list_models()}
