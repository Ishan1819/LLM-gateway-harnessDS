"""Dashboard API: analytics, users, teams, caps, alerts, savings."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AdminUser, Alert, Organization, Team, User
from app.schemas import (
    AlertOut,
    BulkCapUpdate,
    CapUpdate,
    TeamCreate,
    TeamOut,
    UserCreate,
    UserOut,
)
from app.services import usage_service
from app.services.auth_service import get_current_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


# --------------------------------------------------------------------------
# Overview
# --------------------------------------------------------------------------
@router.get("/dashboard")
def dashboard(
    admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)
):
    org: Organization = db.get(Organization, admin.org_id)

    spend_today = usage_service.org_spend(db, org.id, "day")
    spend_week = usage_service.org_spend(db, org.id, "week")
    spend_month = usage_service.org_spend(db, org.id, "month")

    active_users = db.execute(
        select(User).where(User.org_id == org.id, User.is_active.is_(True))
    ).scalars().all()

    users = usage_service.breakdown_by_user(db, org.id, "month")
    teams = usage_service.breakdown_by_team(db, org.id, "month")

    trend = usage_service.cost_trend(db, org.id, days=30)
    days_elapsed = max(1, usage_service.day_start().day)
    projected = spend_month / days_elapsed * 30

    # "Saved" = spend the caps are set to prevent. For every user whose current
    # run rate would carry them past their cap, count the overshoot the cap
    # stops. This is an estimate of avoided spend, not billed spend.
    saved = round(
        sum(
            max(0.0, u["projected"] - u["monthly_cap"])
            for u in users
            if u["monthly_cap"]
        ),
        2,
    )

    return {
        "org": {"name": org.name, "slug": org.slug, "monthly_budget": org.monthly_budget},
        "spend": {
            "today": round(spend_today, 4),
            "week": round(spend_week, 4),
            "month": round(spend_month, 4),
            "projected_month": round(projected, 2),
        },
        "counts": {
            "active_users": len(active_users),
            "total_users": len(users),
            "teams": len(teams),
            "requests_today": usage_service.org_request_count(db, org.id, "day"),
            "requests_month": usage_service.org_request_count(db, org.id, "month"),
        },
        "saved_this_month": saved,
        "budget_used_pct": round(
            (spend_month / org.monthly_budget * 100) if org.monthly_budget else 0.0, 1
        ),
        "trend": trend,
        "top_users": users[:5],
        "teams": teams,
        "models": usage_service.breakdown_by_model(db, org.id, "month"),
        "unread_alerts": len(
            db.execute(
                select(Alert).where(Alert.org_id == org.id, Alert.is_read.is_(False))
            ).scalars().all()
        ),
    }


@router.get("/usage")
def usage(
    group_by: str = Query("user", pattern="^(user|team|model)$"),
    period: str = Query("month", pattern="^(day|week|month)$"),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    fn = {
        "user": usage_service.breakdown_by_user,
        "team": usage_service.breakdown_by_team,
        "model": usage_service.breakdown_by_model,
    }[group_by]
    return {"group_by": group_by, "period": period, "rows": fn(db, admin.org_id, period)}


# --------------------------------------------------------------------------
# Users
# --------------------------------------------------------------------------
@router.get("/users")
def list_users(
    admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)
):
    return usage_service.breakdown_by_user(db, admin.org_id, "month")


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    existing = db.execute(
        select(User).where(User.org_id == admin.org_id, User.email == body.email)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "That user already exists.")

    if body.team_id is not None:
        team = db.execute(
            select(Team).where(Team.id == body.team_id, Team.org_id == admin.org_id)
        ).scalar_one_or_none()
        if team is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found.")

    user = User(
        org_id=admin.org_id,
        team_id=body.team_id,
        name=body.name,
        email=body.email,
        role=body.role,
        monthly_cap=body.monthly_cap,
        daily_cap=body.daily_cap,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users/{user_id}/key", response_model=UserOut)
def reveal_key(
    user_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.execute(
        select(User).where(User.id == user_id, User.org_id == admin.org_id)
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.execute(
        select(User).where(User.id == user_id, User.org_id == admin.org_id)
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    db.delete(user)
    db.commit()


# --------------------------------------------------------------------------
# Teams
# --------------------------------------------------------------------------
@router.get("/teams")
def list_teams(
    admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)
):
    return usage_service.breakdown_by_team(db, admin.org_id, "month")


@router.post("/teams", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
def create_team(
    body: TeamCreate,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    team = Team(
        org_id=admin.org_id,
        name=body.name,
        monthly_cap=body.monthly_cap,
        daily_cap=body.daily_cap,
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


# --------------------------------------------------------------------------
# Caps
# --------------------------------------------------------------------------
# Declared before /caps/{user_id}: FastAPI matches routes in definition order,
# so the parameterized route would otherwise swallow "bulk" as a user_id.
@router.put("/caps/bulk")
def bulk_update_caps(
    body: BulkCapUpdate,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    users = db.execute(
        select(User).where(User.id.in_(body.user_ids), User.org_id == admin.org_id)
    ).scalars().all()

    updates = body.model_dump(exclude_unset=True, exclude={"user_ids"})
    for user in users:
        for field, value in updates.items():
            setattr(user, field, value)
    db.commit()
    return {"updated": len(users)}


@router.put("/caps/{user_id}", response_model=UserOut)
def update_user_caps(
    user_id: int,
    body: CapUpdate,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.execute(
        select(User).where(User.id == user_id, User.org_id == admin.org_id)
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.put("/caps/team/{team_id}", response_model=TeamOut)
def update_team_caps(
    team_id: int,
    body: CapUpdate,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    team = db.execute(
        select(Team).where(Team.id == team_id, Team.org_id == admin.org_id)
    ).scalar_one_or_none()
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found.")

    updates = body.model_dump(exclude_unset=True)
    updates.pop("is_active", None)  # teams have no active flag
    for field, value in updates.items():
        setattr(team, field, value)
    db.commit()
    db.refresh(team)
    return team


# --------------------------------------------------------------------------
# Alerts
# --------------------------------------------------------------------------
@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    limit: int = Query(100, le=500),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return (
        db.execute(
            select(Alert)
            .where(Alert.org_id == admin.org_id)
            .order_by(Alert.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )


@router.put("/alerts/{alert_id}/read", response_model=AlertOut)
def mark_alert_read(
    alert_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    alert = db.execute(
        select(Alert).where(Alert.id == alert_id, Alert.org_id == admin.org_id)
    ).scalar_one_or_none()
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found.")
    alert.is_read = True
    db.commit()
    db.refresh(alert)
    return alert


# --------------------------------------------------------------------------
# Savings
# --------------------------------------------------------------------------
@router.get("/savings")
def savings(
    admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)
):
    org: Organization = db.get(Organization, admin.org_id)

    this_month = usage_service.org_spend(db, org.id, "month")
    month_start = usage_service.month_start()
    prev_start = (month_start - timedelta(days=1)).replace(day=1)

    days_elapsed = max(1, usage_service.day_start().day)
    projected = this_month / days_elapsed * 30

    last_month_full = usage_service.org_spend_between(db, org.id, prev_start, month_start)
    # Compare like for like: the same number of elapsed days last month, so a
    # month-to-date figure isn't measured against a completed month.
    last_month_same_window = usage_service.org_spend_between(
        db, org.id, prev_start, prev_start + timedelta(days=days_elapsed)
    )

    users = usage_service.breakdown_by_user(db, org.id, "month")
    teams = usage_service.breakdown_by_team(db, org.id, "month")
    models = usage_service.breakdown_by_model(db, org.id, "month")

    # Waste heuristic: high spend concentrated on premium models. Flags the
    # accounts worth a conversation, not a definitive verdict.
    premium = {m["model"] for m in models if m["spend"] > 0 and "mini" not in m["model"]}
    flagged = [
        {
            "user": u["name"],
            "team": u["team"],
            "spend": u["spend"],
            "tokens": u["tokens"],
            "reason": "Spend well above team median on premium models",
        }
        for u in users
        if u["spend"] > 0
        and users
        and u["spend"] > 2.5 * (sorted(x["spend"] for x in users)[len(users) // 2] or 0.01)
    ][:6]

    return {
        "budget": org.monthly_budget,
        "spend_this_month": round(this_month, 2),
        "spend_last_month": round(last_month_full, 2),
        "spend_last_month_same_window": round(last_month_same_window, 2),
        "days_elapsed": days_elapsed,
        "projected_month": round(projected, 2),
        "month_over_month_pct": round(
            ((this_month - last_month_same_window) / last_month_same_window * 100)
            if last_month_same_window > 0
            else 0.0,
            1,
        ),
        "remaining": round(max(0.0, org.monthly_budget - this_month), 2),
        "over_budget": bool(org.monthly_budget and projected > org.monthly_budget),
        "premium_models": sorted(premium),
        "flagged_waste": flagged,
        "teams": teams,
        "models": models,
        "trend": usage_service.cost_trend(db, org.id, days=30),
    }
