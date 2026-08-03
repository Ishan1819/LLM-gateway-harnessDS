"""Plan enforcement.

Gating lives here rather than in each route so a feature's tier is defined
once, in plans.py, and enforced identically everywhere.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AdminUser, Organization
from app.services.auth_service import get_current_admin
from app.utils import plans


def org_plan(db: Session, org_id: int) -> str:
    org = db.get(Organization, org_id)
    return (org.plan if org else plans.FREE) or plans.FREE


def require_feature(feature: str):
    """FastAPI dependency factory — 402 when the org's plan lacks the feature."""

    def dependency(
        admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)
    ) -> AdminUser:
        plan_id = org_plan(db, admin.org_id)
        if not plans.has_feature(plan_id, feature):
            needed = plans.required_plan_for(feature)
            raise HTTPException(
                # 402 Payment Required: the request is valid, the plan isn't.
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "upgrade_required",
                    "feature": feature,
                    "feature_label": plans.FEATURE_LABELS.get(feature, feature),
                    "current_plan": plan_id,
                    "required_plan": needed,
                    "message": (
                        f"{plans.FEATURE_LABELS.get(feature, feature)} is available on the "
                        f"{plans.get_plan(needed)['name']} plan."
                    ),
                },
            )
        return admin

    return dependency


def enforce_user_limit(db: Session, org_id: int, current_count: int) -> None:
    plan = plans.get_plan(org_plan(db, org_id))
    limit = plan["max_users"]
    if limit and current_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "upgrade_required",
                "current_plan": plan["id"],
                "required_plan": plans.STANDARD
                if plan["id"] == plans.FREE
                else plans.PREMIUM,
                "message": (
                    f"The {plan['name']} plan tracks up to {limit} users. "
                    "Upgrade to add more."
                ),
            },
        )


def history_window(db: Session, org_id: int, requested_days: int) -> int:
    """Clamp a history request to what the plan allows (0 = unlimited)."""
    allowed = plans.get_plan(org_plan(db, org_id))["history_days"]
    return requested_days if not allowed else min(requested_days, allowed)
