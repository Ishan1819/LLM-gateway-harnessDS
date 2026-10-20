"""Usage recording and the aggregation queries behind the dashboard."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Team, UsageLog, User
from app.utils.pricing import calculate_cost


def day_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def month_start(now: datetime | None = None) -> datetime:
    return day_start(now).replace(day=1)


def week_start(now: datetime | None = None) -> datetime:
    start = day_start(now)
    return start - timedelta(days=start.weekday())


def period_start(period: str) -> datetime:
    return {"day": day_start, "week": week_start, "month": month_start}.get(
        period, month_start
    )()


def record_usage(
    db: Session,
    *,
    user: User,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    request_summary: str | None = None,
    # --- AI Cost Governance extensions (optional; only set by the governed
    # proxy pipeline in routes/governed.py) ---
    requested_model: str | None = None,
    original_tokens: int | None = None,
    compressed_tokens: int | None = None,
    token_reduction_pct: float | None = None,
    complexity_score: float | None = None,
    complexity_tier: int | None = None,
    compression_savings_usd: float | None = None,
    routing_savings_usd: float | None = None,
    total_savings_usd: float | None = None,
    techniques_applied: list[str] | None = None,
    # --- Distributed pipeline provenance (set by the usage-worker) ---
    lamport_ts: int | None = None,
    origin_pod: str | None = None,
    processed_by: str | None = None,
    event_id: str | None = None,
) -> UsageLog:
    cost = calculate_cost(model, prompt_tokens, completion_tokens)
    log = UsageLog(
        org_id=user.org_id,
        team_id=user.team_id,
        user_id=user.id,
        model_used=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        cost_usd=cost,
        request_summary=(request_summary or "")[:100] or None,
        requested_model=requested_model,
        original_tokens=original_tokens,
        compressed_tokens=compressed_tokens,
        token_reduction_pct=token_reduction_pct,
        complexity_score=complexity_score,
        complexity_tier=complexity_tier,
        compression_savings_usd=compression_savings_usd,
        routing_savings_usd=routing_savings_usd,
        total_savings_usd=total_savings_usd,
        techniques_applied=",".join(techniques_applied) if techniques_applied else None,
        lamport_ts=lamport_ts,
        origin_pod=origin_pod,
        processed_by=processed_by,
        event_id=event_id,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def _sum_cost(db: Session, *, since: datetime, **filters) -> float:
    stmt = select(func.coalesce(func.sum(UsageLog.cost_usd), 0.0)).where(
        UsageLog.timestamp >= since
    )
    for column, value in filters.items():
        stmt = stmt.where(getattr(UsageLog, column) == value)
    return float(db.execute(stmt).scalar_one())


def user_spend(db: Session, user_id: int, period: str = "month") -> float:
    return _sum_cost(db, since=period_start(period), user_id=user_id)


def team_spend(db: Session, team_id: int, period: str = "month") -> float:
    return _sum_cost(db, since=period_start(period), team_id=team_id)


def org_spend(db: Session, org_id: int, period: str = "month") -> float:
    return _sum_cost(db, since=period_start(period), org_id=org_id)


def org_spend_between(db: Session, org_id: int, start: datetime, end: datetime) -> float:
    stmt = (
        select(func.coalesce(func.sum(UsageLog.cost_usd), 0.0))
        .where(UsageLog.org_id == org_id)
        .where(UsageLog.timestamp >= start, UsageLog.timestamp < end)
    )
    return float(db.execute(stmt).scalar_one())


def org_request_count(db: Session, org_id: int, period: str = "month") -> int:
    stmt = (
        select(func.count(UsageLog.id))
        .where(UsageLog.org_id == org_id)
        .where(UsageLog.timestamp >= period_start(period))
    )
    return int(db.execute(stmt).scalar_one())


def cost_trend(db: Session, org_id: int, days: int = 30) -> list[dict]:
    """Daily spend series, zero-filled so the chart has no gaps."""
    since = day_start() - timedelta(days=days - 1)
    rows = db.execute(
        select(
            func.date(UsageLog.timestamp).label("day"),
            func.sum(UsageLog.cost_usd).label("cost"),
            func.count(UsageLog.id).label("requests"),
            func.sum(UsageLog.total_tokens).label("tokens"),
        )
        .where(UsageLog.org_id == org_id, UsageLog.timestamp >= since)
        .group_by(func.date(UsageLog.timestamp))
    ).all()

    by_day = {
        (r.day if isinstance(r.day, date) else date.fromisoformat(str(r.day))): r
        for r in rows
    }

    series = []
    for offset in range(days):
        d = (since + timedelta(days=offset)).date()
        row = by_day.get(d)
        series.append(
            {
                "date": d.isoformat(),
                "cost": round(float(row.cost), 4) if row else 0.0,
                "requests": int(row.requests) if row else 0,
                "tokens": int(row.tokens) if row else 0,
            }
        )
    return series


def month_pace_multiplier(now: datetime | None = None) -> float:
    """Scale month-to-date spend to a full-month run rate."""
    days_elapsed = max(1, day_start(now).day)
    return 30.0 / days_elapsed


def breakdown_by_user(db: Session, org_id: int, period: str = "month") -> list[dict]:
    since = period_start(period)
    today = day_start()
    pace = month_pace_multiplier()

    month_rows = dict(
        db.execute(
            select(UsageLog.user_id, func.sum(UsageLog.cost_usd))
            .where(UsageLog.org_id == org_id, UsageLog.timestamp >= since)
            .group_by(UsageLog.user_id)
        ).all()
    )
    today_rows = dict(
        db.execute(
            select(UsageLog.user_id, func.sum(UsageLog.cost_usd))
            .where(UsageLog.org_id == org_id, UsageLog.timestamp >= today)
            .group_by(UsageLog.user_id)
        ).all()
    )
    token_rows = dict(
        db.execute(
            select(UsageLog.user_id, func.sum(UsageLog.total_tokens))
            .where(UsageLog.org_id == org_id, UsageLog.timestamp >= since)
            .group_by(UsageLog.user_id)
        ).all()
    )
    request_rows = dict(
        db.execute(
            select(UsageLog.user_id, func.count(UsageLog.id))
            .where(UsageLog.org_id == org_id, UsageLog.timestamp >= today)
            .group_by(UsageLog.user_id)
        ).all()
    )

    users = db.execute(select(User).where(User.org_id == org_id)).scalars().all()
    teams = {t.id: t.name for t in db.execute(select(Team).where(Team.org_id == org_id)).scalars()}

    out = []
    for u in users:
        spend = round(float(month_rows.get(u.id, 0.0)), 4)
        pct = (spend / u.monthly_cap * 100) if u.monthly_cap else 0.0
        projected = spend * pace
        out.append(
            {
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "team": teams.get(u.team_id, "Unassigned"),
                "team_id": u.team_id,
                "is_active": u.is_active,
                "requests_today": int(request_rows.get(u.id, 0)),
                "tokens": int(token_rows.get(u.id, 0)),
                "spend_today": round(float(today_rows.get(u.id, 0.0)), 4),
                "spend": spend,
                "monthly_cap": u.monthly_cap,
                "daily_cap": u.daily_cap,
                "pct_of_cap": round(pct, 1),
                "projected": round(projected, 2),
                # What the cap will look like if this pace holds — the number
                # that actually tells an admin whether to intervene.
                "pace_pct_of_cap": round(
                    (projected / u.monthly_cap * 100) if u.monthly_cap else 0.0, 1
                ),
            }
        )
    return sorted(out, key=lambda r: r["spend"], reverse=True)


def breakdown_by_team(db: Session, org_id: int, period: str = "month") -> list[dict]:
    since = period_start(period)
    spend_rows = dict(
        db.execute(
            select(UsageLog.team_id, func.sum(UsageLog.cost_usd))
            .where(UsageLog.org_id == org_id, UsageLog.timestamp >= since)
            .group_by(UsageLog.team_id)
        ).all()
    )
    token_rows = dict(
        db.execute(
            select(UsageLog.team_id, func.sum(UsageLog.total_tokens))
            .where(UsageLog.org_id == org_id, UsageLog.timestamp >= since)
            .group_by(UsageLog.team_id)
        ).all()
    )
    request_rows = dict(
        db.execute(
            select(UsageLog.team_id, func.count(UsageLog.id))
            .where(UsageLog.org_id == org_id, UsageLog.timestamp >= since)
            .group_by(UsageLog.team_id)
        ).all()
    )

    pace = month_pace_multiplier()
    teams = db.execute(select(Team).where(Team.org_id == org_id)).scalars().all()
    member_counts = dict(
        db.execute(
            select(User.team_id, func.count(User.id))
            .where(User.org_id == org_id)
            .group_by(User.team_id)
        ).all()
    )

    out = []
    for t in teams:
        spend = round(float(spend_rows.get(t.id, 0.0)), 4)
        pct = (spend / t.monthly_cap * 100) if t.monthly_cap else 0.0
        out.append(
            {
                "id": t.id,
                "name": t.name,
                "members": int(member_counts.get(t.id, 0)),
                "requests": int(request_rows.get(t.id, 0)),
                "tokens": int(token_rows.get(t.id, 0)),
                "spend": spend,
                "monthly_cap": t.monthly_cap,
                "daily_cap": t.daily_cap,
                "pct_of_cap": round(pct, 1),
                "projected": round(spend * pace, 2),
                "pace_pct_of_cap": round(
                    (spend * pace / t.monthly_cap * 100) if t.monthly_cap else 0.0, 1
                ),
                "over_budget": bool(t.monthly_cap and spend * pace > t.monthly_cap),
            }
        )
    return sorted(out, key=lambda r: r["spend"], reverse=True)


def governance_summary(db: Session, org_id: int, period: str = "month") -> dict:
    """Aggregate metrics for requests that went through the governed pipeline
    (compression + complexity scoring + routing) -- see routes/governed.py.
    Rows from the plain passthrough proxy have `original_tokens IS NULL` and
    are excluded, since they were never compressed or re-routed.
    """
    since = period_start(period)
    rows = (
        db.execute(
            select(UsageLog).where(
                UsageLog.org_id == org_id,
                UsageLog.timestamp >= since,
                UsageLog.original_tokens.is_not(None),
            )
        )
        .scalars()
        .all()
    )

    if not rows:
        return {
            "total_requests": 0,
            "original_tokens": 0,
            "compressed_tokens": 0,
            "token_reduction_pct": 0.0,
            "model_distribution": [],
            "original_estimated_cost_usd": 0.0,
            "optimized_cost_usd": 0.0,
            "total_saved_usd": 0.0,
            "total_saved_pct": 0.0,
        }

    original_tokens = sum(r.original_tokens or 0 for r in rows)
    compressed_tokens = sum(r.compressed_tokens or 0 for r in rows)
    total_saved = sum(r.total_savings_usd or 0.0 for r in rows)
    optimized_cost = sum(r.cost_usd or 0.0 for r in rows)
    # The counterfactual "as if governance were off" cost = what was actually
    # spent plus what governance is estimated to have saved.
    original_estimated_cost = optimized_cost + total_saved

    model_counts: dict[str, int] = {}
    for r in rows:
        model_counts[r.model_used] = model_counts.get(r.model_used, 0) + 1
    model_distribution = sorted(
        ({"model": m, "requests": c} for m, c in model_counts.items()),
        key=lambda x: x["requests"],
        reverse=True,
    )

    return {
        "total_requests": len(rows),
        "original_tokens": original_tokens,
        "compressed_tokens": compressed_tokens,
        "token_reduction_pct": round(
            100 * (original_tokens - compressed_tokens) / original_tokens, 2
        )
        if original_tokens
        else 0.0,
        "model_distribution": model_distribution,
        "original_estimated_cost_usd": round(original_estimated_cost, 4),
        "optimized_cost_usd": round(optimized_cost, 4),
        "total_saved_usd": round(total_saved, 4),
        "total_saved_pct": round(100 * total_saved / original_estimated_cost, 2)
        if original_estimated_cost
        else 0.0,
    }


def breakdown_by_model(db: Session, org_id: int, period: str = "month") -> list[dict]:
    rows = db.execute(
        select(
            UsageLog.model_used,
            func.sum(UsageLog.cost_usd),
            func.sum(UsageLog.total_tokens),
            func.count(UsageLog.id),
        )
        .where(UsageLog.org_id == org_id, UsageLog.timestamp >= period_start(period))
        .group_by(UsageLog.model_used)
    ).all()
    return sorted(
        [
            {
                "model": r[0],
                "spend": round(float(r[1]), 4),
                "tokens": int(r[2]),
                "requests": int(r[3]),
            }
            for r in rows
        ],
        key=lambda r: r["spend"],
        reverse=True,
    )
