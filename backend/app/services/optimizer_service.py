"""Cost Optimizer — the Premium analysis layer.

Everything here is derived from usage already recorded by the proxy. No prompt
bodies are read: only token counts, models, and the 100-character request label
already stored for the usage log. Findings are *estimates* — the API reports
them as such, because the right call on a model downgrade always needs a human.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Team, UsageLog, User
from app.utils.pricing import calculate_cost, detect_provider

# Where a workload could plausibly run one tier down. Deliberately conservative:
# each hop stays inside the same provider and skips only one capability step.
CHEAPER_ALTERNATIVE: dict[str, str] = {
    "gpt-4-turbo": "gpt-4o",
    "gpt-4o": "gpt-4o-mini",
    "claude-fable-5": "claude-opus-5",
    "claude-opus-5": "claude-sonnet-4-6",
    "claude-opus-4-8": "claude-sonnet-4-6",
    "claude-sonnet-4-6": "claude-haiku-4-5",
    "claude-sonnet-5": "claude-haiku-4-5",
}

# A prompt label seen this many times from one user starts to look like a loop.
REPEAT_THRESHOLD = 3


def _logs_since(db: Session, org_id: int, since: datetime) -> list[UsageLog]:
    return (
        db.execute(
            select(UsageLog).where(UsageLog.org_id == org_id, UsageLog.timestamp >= since)
        )
        .scalars()
        .all()
    )


def model_rightsizing(logs: list[UsageLog]) -> list[dict]:
    """Estimate savings from moving the *simpler half* of a model's traffic down a tier.

    "Simpler" is measured against how that model is normally used in this org —
    requests below its own median prompt size — rather than an absolute cutoff,
    so a team with genuinely large contexts isn't told to downgrade everything.
    """
    by_model: dict[str, list[UsageLog]] = defaultdict(list)
    for log in logs:
        if log.model_used in CHEAPER_ALTERNATIVE:
            by_model[log.model_used].append(log)

    findings = []
    for model, model_logs in by_model.items():
        if len(model_logs) < 10:
            continue  # too little traffic to say anything meaningful

        alternative = CHEAPER_ALTERNATIVE[model]
        median_prompt = statistics.median(log.prompt_tokens for log in model_logs)
        candidates = [log for log in model_logs if log.prompt_tokens <= median_prompt]
        if not candidates:
            continue

        current = sum(log.cost_usd for log in candidates)
        projected = sum(
            calculate_cost(alternative, log.prompt_tokens, log.completion_tokens)
            for log in candidates
        )
        saving = current - projected
        if saving <= 0:
            continue

        findings.append(
            {
                "model": model,
                "alternative": alternative,
                "provider": detect_provider(model),
                "candidate_requests": len(candidates),
                "total_requests": len(model_logs),
                "median_prompt_tokens": int(median_prompt),
                "current_cost": round(current, 2),
                "projected_cost": round(projected, 2),
                "estimated_saving": round(saving, 2),
                "saving_pct": round((saving / current * 100) if current else 0, 1),
            }
        )

    return sorted(findings, key=lambda f: f["estimated_saving"], reverse=True)


def repeated_prompts(db: Session, logs: list[UsageLog], org_id: int) -> list[dict]:
    """Same prompt label, same person, over and over — usually a retry loop."""
    groups: dict[tuple[int, str], list[UsageLog]] = defaultdict(list)
    for log in logs:
        if log.request_summary:
            groups[(log.user_id, log.request_summary)].append(log)

    names = {
        u.id: u.name
        for u in db.execute(select(User).where(User.org_id == org_id)).scalars()
    }

    findings = []
    for (user_id, summary), group in groups.items():
        if len(group) < REPEAT_THRESHOLD:
            continue
        spend = sum(log.cost_usd for log in group)
        # Everything after the first run is what deduplication or caching could avoid.
        avoidable = spend - (spend / len(group))
        findings.append(
            {
                "user": names.get(user_id, f"User {user_id}"),
                "user_id": user_id,
                "prompt_preview": summary,
                "repeats": len(group),
                "total_cost": round(spend, 2),
                "avoidable": round(avoidable, 2),
                "models": sorted({log.model_used for log in group}),
            }
        )

    return sorted(findings, key=lambda f: f["avoidable"], reverse=True)[:15]


def team_efficiency(db: Session, logs: list[UsageLog], org_id: int) -> list[dict]:
    """Per-team prompt hygiene: context size and how often work gets repeated."""
    teams = {
        t.id: t.name
        for t in db.execute(select(Team).where(Team.org_id == org_id)).scalars()
    }

    by_team: dict[int | None, list[UsageLog]] = defaultdict(list)
    for log in logs:
        by_team[log.team_id].append(log)

    org_avg_prompt = (
        statistics.mean(log.prompt_tokens for log in logs) if logs else 0
    )

    rows = []
    for team_id, team_logs in by_team.items():
        if not team_logs:
            continue

        avg_prompt = statistics.mean(log.prompt_tokens for log in team_logs)
        avg_completion = statistics.mean(log.completion_tokens for log in team_logs)
        spend = sum(log.cost_usd for log in team_logs)

        labels = defaultdict(int)
        for log in team_logs:
            if log.request_summary:
                labels[log.request_summary] += 1
        repeated = sum(count - 1 for count in labels.values() if count > 1)
        repeat_rate = (repeated / len(team_logs) * 100) if team_logs else 0

        guidance = []
        if org_avg_prompt and avg_prompt > org_avg_prompt * 1.3:
            guidance.append(
                "Prompts carry more context than the org average — trim history or "
                "retrieve only the passages a task needs."
            )
        if repeat_rate > 25:
            guidance.append(
                "High share of repeated prompts — cache identical calls, or fix the "
                "retry loop generating them."
            )
        if avg_completion > 3000:
            guidance.append(
                "Long completions — set a tighter max_tokens, or ask for the answer "
                "before the explanation."
            )
        if not guidance:
            guidance.append("Prompt sizing and repeat rate both look healthy.")

        rows.append(
            {
                "team": teams.get(team_id, "Unassigned"),
                "team_id": team_id,
                "requests": len(team_logs),
                "spend": round(spend, 2),
                "avg_prompt_tokens": int(avg_prompt),
                "avg_completion_tokens": int(avg_completion),
                "repeat_rate_pct": round(repeat_rate, 1),
                "cost_per_request": round(spend / len(team_logs), 4),
                "guidance": guidance,
            }
        )

    return sorted(rows, key=lambda r: r["spend"], reverse=True)


def build_report(db: Session, org_id: int, since: datetime) -> dict:
    logs = _logs_since(db, org_id, since)

    rightsizing = model_rightsizing(logs)
    repeats = repeated_prompts(db, logs, org_id)
    teams = team_efficiency(db, logs, org_id)

    total_spend = sum(log.cost_usd for log in logs)
    rightsizing_saving = sum(f["estimated_saving"] for f in rightsizing)
    repeat_saving = sum(f["avoidable"] for f in repeats)

    return {
        "window_start": since.isoformat(),
        "total_requests": len(logs),
        "total_spend": round(total_spend, 2),
        "opportunity": {
            "model_rightsizing": round(rightsizing_saving, 2),
            "repeated_prompts": round(repeat_saving, 2),
            "total": round(rightsizing_saving + repeat_saving, 2),
            "pct_of_spend": round(
                ((rightsizing_saving + repeat_saving) / total_spend * 100)
                if total_spend
                else 0,
                1,
            ),
        },
        "model_rightsizing": rightsizing,
        "repeated_prompts": repeats,
        "team_efficiency": teams,
    }
