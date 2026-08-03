"""Budget enforcement.

Checked before a request is forwarded upstream, so an over-budget user never
spends the client's money. A cap of 0 means "no cap".
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Team, User
from app.services import usage_service


@dataclass
class CapDecision:
    allowed: bool
    reason: str | None = None
    scope: str | None = None  # user_daily | user_monthly | team_daily | team_monthly | org_monthly


ALLOWED = CapDecision(allowed=True)


def check(db: Session, user: User) -> CapDecision:
    if not user.is_active:
        return CapDecision(
            allowed=False,
            reason="This account has been deactivated. Contact your admin.",
            scope="inactive",
        )

    checks: list[tuple[str, float, float]] = []

    if user.daily_cap:
        checks.append(("user_daily", usage_service.user_spend(db, user.id, "day"), user.daily_cap))
    if user.monthly_cap:
        checks.append(
            ("user_monthly", usage_service.user_spend(db, user.id, "month"), user.monthly_cap)
        )

    team: Team | None = user.team
    if team:
        if team.daily_cap:
            checks.append(
                ("team_daily", usage_service.team_spend(db, team.id, "day"), team.daily_cap)
            )
        if team.monthly_cap:
            checks.append(
                ("team_monthly", usage_service.team_spend(db, team.id, "month"), team.monthly_cap)
            )

    org = user.organization
    if org and org.monthly_budget:
        checks.append(
            ("org_monthly", usage_service.org_spend(db, org.id, "month"), org.monthly_budget)
        )

    for scope, spent, cap in checks:
        if spent >= cap:
            return CapDecision(
                allowed=False,
                reason="Budget limit reached. Contact your admin.",
                scope=scope,
            )

    return ALLOWED


def utilization(db: Session, user: User) -> dict[str, float]:
    """Fraction of each applicable cap consumed. Used to fire threshold alerts."""
    result: dict[str, float] = {}

    if user.daily_cap:
        result["user_daily"] = usage_service.user_spend(db, user.id, "day") / user.daily_cap
    if user.monthly_cap:
        result["user_monthly"] = usage_service.user_spend(db, user.id, "month") / user.monthly_cap

    team = user.team
    if team:
        if team.daily_cap:
            result["team_daily"] = usage_service.team_spend(db, team.id, "day") / team.daily_cap
        if team.monthly_cap:
            result["team_monthly"] = (
                usage_service.team_spend(db, team.id, "month") / team.monthly_cap
            )

    return result
