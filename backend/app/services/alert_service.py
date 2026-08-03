"""Threshold alerts at 80% / 90% of cap, plus limit-reached events."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Alert, AlertType, User
from app.services import cap_service, usage_service

SCOPE_LABELS = {
    "user_daily": "daily cap",
    "user_monthly": "monthly cap",
    "team_daily": "team daily cap",
    "team_monthly": "team monthly cap",
    "org_monthly": "organization monthly budget",
    "inactive": "account status",
}


def _already_alerted(db: Session, *, org_id: int, user_id: int | None, type_: str) -> bool:
    """Debounce so one over-budget user doesn't generate an alert per request."""
    since = usage_service.day_start() - timedelta(days=0)
    stmt = (
        select(Alert.id)
        .where(
            Alert.org_id == org_id,
            Alert.user_id == user_id,
            Alert.type == type_,
            Alert.created_at >= since,
        )
        .limit(1)
    )
    return db.execute(stmt).first() is not None


def _create(
    db: Session, *, org_id: int, user_id: int | None, team_id: int | None, type_: str, message: str
) -> Alert | None:
    if _already_alerted(db, org_id=org_id, user_id=user_id, type_=type_):
        return None
    alert = Alert(
        org_id=org_id, user_id=user_id, team_id=team_id, type=type_, message=message
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def evaluate_thresholds(db: Session, user: User) -> list[Alert]:
    """Called after each recorded request. Fires 80%/90% warnings once per day."""
    thresholds = sorted(settings.alert_threshold_list, reverse=True)
    created: list[Alert] = []

    for scope, ratio in cap_service.utilization(db, user).items():
        for threshold in thresholds:
            if ratio < threshold:
                continue
            pct = int(round(threshold * 100))
            type_ = (
                AlertType.warning_90pct.value if pct >= 90 else AlertType.warning_80pct.value
            )
            alert = _create(
                db,
                org_id=user.org_id,
                user_id=user.id,
                team_id=user.team_id,
                type_=type_,
                message=(
                    f"{user.name} has used {int(ratio * 100)}% of their "
                    f"{SCOPE_LABELS.get(scope, scope)}."
                ),
            )
            if alert:
                created.append(alert)
            break  # only the highest crossed threshold matters

    return created


def record_limit_reached(db: Session, user: User, scope: str) -> Alert | None:
    return _create(
        db,
        org_id=user.org_id,
        user_id=user.id,
        team_id=user.team_id,
        type_=AlertType.limit_reached.value,
        message=(
            f"{user.name} was blocked — {SCOPE_LABELS.get(scope, scope)} reached. "
            "Requests are being rejected with HTTP 429."
        ),
    )
