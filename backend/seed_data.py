"""Seed a demo organization with 30 days of realistic usage.

    python seed_data.py            # wipe + reseed
    python seed_data.py --keep     # only seed if the demo org is missing

Demo login: admin@test.com / demo123

Caps are derived from each user's generated month-end run rate rather than
hardcoded, so the demo shows meaningful utilization no matter which day of the
month the seed is run on. Most users track comfortably under cap, several sit
near it, and a few are on pace to blow through — which is what makes the alerts
and savings views worth looking at.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.models import Alert, AlertType, Organization, Team, UsageLog, User
from app.models.user import AdminUser, generate_proxy_api_key
from app.services.auth_service import hash_password
from app.services.encryption_service import encrypt
from app.services.usage_service import month_start
from app.utils import plans
from app.utils.pricing import calculate_cost

random.seed(7)  # reproducible demos

ORG_SLUG = "demo"
DAYS = 30

# Prompt templates plus a varying subject, so healthy traffic looks like real
# work — mostly distinct prompts. Without this variety every request would
# collapse onto a handful of labels and the optimizer's repeat-rate metric
# would read ~100% for everyone, flagging normal usage as waste.
PROMPT_TEMPLATES = [
    "Refactor {module} to use async database sessions",
    "Write unit tests for {module}",
    "Summarize the findings in the {quarter} {subject} dataset",
    "Explain why the {module} migration is locking the users table",
    "Generate TypeScript types from the {module} OpenAPI schema",
    "Draft release notes for version {version}",
    "Review PR #{ticket} in {module} for security issues",
    "Convert the {module} pandas pipeline to Polars",
    "Debug the {error} raised by {module}",
    "Build a feature importance chart for the {subject} model",
    "Add retry handling to the {module} client",
    "Document the public API surface of {module}",
    "Profile the slow query in {module} and propose an index",
    "Port {module} from callbacks to async/await",
]

MODULES = [
    "the billing service", "the auth middleware", "the ingestion worker",
    "the search indexer", "the webhook dispatcher", "the report generator",
    "the notification queue", "the pricing engine", "the audit logger",
    "the session store", "the export pipeline", "the rate limiter",
]
SUBJECTS = ["churn", "activation", "retention", "fraud", "forecast", "attribution"]
ERRORS = [
    "IntegrityError", "TimeoutError", "KeyError", "ConnectionReset",
    "ValidationError", "DeadlockDetected",
]
QUARTERS = ["Q1", "Q2", "Q3", "Q4"]


SOURCE_FILES = [
    "api/routes.py", "core/session.py", "workers/consumer.py", "db/models.py",
    "lib/client.ts", "services/dispatch.go", "utils/retry.py", "web/handlers.rs",
]


def realistic_prompt() -> str:
    """A distinct prompt per call.

    Genuine engineering prompts almost never repeat verbatim — they name a
    different file, ticket, or error each time. Anchoring each one to a
    concrete location keeps healthy traffic near-unique, so the optimizer's
    repeat detection surfaces only the deliberate retry loops.
    """
    base = random.choice(PROMPT_TEMPLATES).format(
        module=random.choice(MODULES),
        subject=random.choice(SUBJECTS),
        error=random.choice(ERRORS),
        quarter=random.choice(QUARTERS),
        version=f"{random.randint(1, 4)}.{random.randint(0, 9)}",
        ticket=random.randint(1000, 9999),
    )
    return f"{base} ({random.choice(SOURCE_FILES)}:{random.randint(12, 940)})"


# The repetitive prompts our worst offenders keep re-sending, verbatim.
WASTEFUL_PROMPTS = [
    "fix this",
    "why doesn't this work",
    "try again",
    "still broken, try again",
]

TEAMS = [
    ("Backend", 8),
    ("Frontend", 5),
    ("Data Science", 7),
]

NAMES = [
    "Priya Sharma", "Marcus Webb", "Elena Duarte", "Tom Okafor", "Sana Malik",
    "Jonas Lindqvist", "Ruth Adeyemi", "Diego Moreno", "Chloe Bennett", "Arjun Rao",
    "Nadia Hassan", "Felix Braun", "Ivy Chen", "Omar Haddad", "Greta Nilsson",
    "Leo Fontaine", "Maya Krishnan", "Daniel Osei", "Hana Sato", "Victor Ilie",
]

# Per-team model mix: (model, weight)
TEAM_MODEL_MIX = {
    "Backend": [
        ("gpt-4o", 0.35),
        ("gpt-4o-mini", 0.35),
        ("claude-sonnet-4-6", 0.25),
        ("claude-opus-5", 0.05),
    ],
    "Frontend": [
        ("gpt-4o-mini", 0.75),
        ("gpt-4o", 0.20),
        ("claude-haiku-4-5", 0.05),
    ],
    "Data Science": [
        ("gpt-4-turbo", 0.30),
        ("gpt-4o", 0.30),
        ("claude-opus-5", 0.30),
        ("claude-sonnet-4-6", 0.10),
    ],
}

# requests/day range and token scale — Data Science burns, Frontend sips.
TEAM_INTENSITY = {
    "Backend": (10, 26, 1.0),
    "Frontend": (5, 14, 0.55),
    "Data Science": (18, 40, 1.7),
}

# Long-context agentic coding traffic: large prompts, modest completions.
BASE_PROMPT_TOKENS = 26_000
BASE_COMPLETION_TOKENS = 2_400


def weighted_model(team_name: str) -> str:
    mix = TEAM_MODEL_MIX[team_name]
    return random.choices([m for m, _ in mix], weights=[w for _, w in mix])[0]


def wipe(db) -> None:
    org = db.execute(
        select(Organization).where(Organization.slug == ORG_SLUG)
    ).scalar_one_or_none()
    if org is None:
        return
    for model in (UsageLog, Alert):
        for row in db.execute(select(model).where(model.org_id == org.id)).scalars().all():
            db.delete(row)
    for model in (User, AdminUser, Team):
        for row in db.execute(select(model).where(model.org_id == org.id)).scalars().all():
            db.delete(row)
    db.delete(org)
    db.commit()
    print("Removed existing demo org.")


def seed() -> None:
    db = SessionLocal()
    try:
        # The demo org runs on Premium so every tier's features are visible in
        # the showcase. Self-serve signups start on Free and see the gates.
        # Placeholder provider keys: requests go to the mock-llm service, which
        # ignores them, so the demo runs end to end without paying anyone.
        org = Organization(
            name="Demo Organization",
            slug=ORG_SLUG,
            monthly_budget=0.0,
            plan=plans.PREMIUM,
            openai_api_key_encrypted=encrypt("sk-demo-openai-not-a-real-key"),
            anthropic_api_key_encrypted=encrypt("sk-ant-demo-not-a-real-key"),
        )
        db.add(org)
        db.flush()

        db.add(
            AdminUser(
                org_id=org.id,
                name="Dana Whitfield",
                email="admin@test.com",
                password_hash=hash_password("demo123"),
            )
        )

        name_pool = iter(NAMES)
        users: list[tuple[User, str]] = []
        teams: dict[str, Team] = {}

        for team_name, headcount in TEAMS:
            team = Team(org_id=org.id, name=team_name, monthly_cap=0.0, daily_cap=0.0)
            db.add(team)
            db.flush()
            teams[team_name] = team

            for index in range(headcount):
                full_name = next(name_pool)
                handle = full_name.lower().replace(" ", ".")
                user = User(
                    org_id=org.id,
                    team_id=team.id,
                    name=full_name,
                    email=f"{handle}@test.com",
                    role="admin" if index == 0 else "member",
                    proxy_api_key=generate_proxy_api_key(),
                    monthly_cap=0.0,
                    daily_cap=0.0,
                    is_active=True,
                )
                db.add(user)
                users.append((user, team_name))

        db.flush()

        # Two Data Science wasters plus one on Backend: high volume, short
        # repetitive prompts — the pattern the Savings report should surface.
        ds_users = [u for u, t in users if t == "Data Science"]
        be_users = [u for u, t in users if t == "Backend"]
        wasters = {ds_users[0].id, ds_users[1].id, be_users[0].id}

        now = datetime.now(timezone.utc)
        current_month_start = month_start(now)
        logs: list[UsageLog] = []

        for day_offset in range(DAYS - 1, -1, -1):
            day = now - timedelta(days=day_offset)
            weekend = day.weekday() >= 5

            for user, team_name in users:
                low, high, token_scale = TEAM_INTENSITY[team_name]
                requests = random.randint(low, high)
                if weekend:
                    requests = int(requests * 0.25)
                if user.id in wasters:
                    requests = int(requests * 2.4)

                for _ in range(requests):
                    model = weighted_model(team_name)
                    is_waste = user.id in wasters and random.random() < 0.55
                    # Wasteful turns are short and cheap individually — the cost
                    # comes from how many of them there are.
                    waste_factor = 0.3 if is_waste else 1.0

                    prompt_tokens = max(
                        200,
                        int(
                            random.gauss(BASE_PROMPT_TOKENS, BASE_PROMPT_TOKENS * 0.35)
                            * token_scale
                            * waste_factor
                        ),
                    )
                    completion_tokens = max(
                        40,
                        int(
                            random.gauss(BASE_COMPLETION_TOKENS, BASE_COMPLETION_TOKENS * 0.4)
                            * token_scale
                            * waste_factor
                        ),
                    )

                    summary = (
                        random.choice(WASTEFUL_PROMPTS) if is_waste else realistic_prompt()
                    )

                    timestamp = day.replace(
                        hour=random.randint(8, 19),
                        minute=random.randint(0, 59),
                        second=random.randint(0, 59),
                        microsecond=0,
                    )

                    logs.append(
                        UsageLog(
                            org_id=org.id,
                            team_id=user.team_id,
                            user_id=user.id,
                            model_used=model,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            total_tokens=prompt_tokens + completion_tokens,
                            cost_usd=calculate_cost(model, prompt_tokens, completion_tokens),
                            request_summary=summary[:100],
                            timestamp=timestamp,
                        )
                    )

        db.bulk_save_objects(logs)
        db.commit()
        print(f"Wrote {len(logs):,} usage rows across {DAYS} days.")

        # ------------------------------------------------------------------
        # Derive caps from each user's month-end run rate, so a monthly cap
        # means what it says regardless of which day the seed runs. The
        # dashboard's "pace" column is then the number that shows tension:
        # a few users are on track to blow through their cap.
        # ------------------------------------------------------------------
        mtd_by_user: dict[int, float] = {}
        for log in logs:
            if log.timestamp >= current_month_start:
                mtd_by_user[log.user_id] = mtd_by_user.get(log.user_id, 0.0) + log.cost_usd

        days_elapsed = max(1, now.day)
        pace = 30.0 / days_elapsed

        # Target month-end utilization: mostly healthy, a few near cap, a few over.
        ratio_cycle = [0.35, 0.52, 0.68, 0.44, 0.83, 0.61, 0.92, 1.14, 0.47, 0.75]
        mtd_total = sum(mtd_by_user.values()) or 1.0
        projected_total = mtd_total * pace

        for index, (user, team_name) in enumerate(users):
            projected = mtd_by_user.get(user.id, 0.0) * pace
            # Wasters are deliberately on track to exceed their cap.
            target = 1.18 if user.id in wasters else ratio_cycle[index % len(ratio_cycle)]
            cap = max(25.0, round(projected / target, -1)) if projected else 100.0
            user.monthly_cap = cap
            user.daily_cap = round(cap / 20, 2)

        # Team caps sit slightly below the sum of member caps, so a team can be
        # over budget even when most of its members individually are not.
        for team_name, team in teams.items():
            member_caps = sum(u.monthly_cap for u, t in users if t == team_name)
            team.monthly_cap = round(member_caps * 0.9, 0)
            team.daily_cap = round(team.monthly_cap / 20, 2)

        # Org budget: tight enough that the projection runs hot.
        org.monthly_budget = round(projected_total * 0.92, -1)
        db.commit()

        # --- Alert history ---
        # Backdated to when each threshold would actually have been crossed,
        # using the user's month-end pace as the basis.
        alerts: list[Alert] = []
        for user, _team in users:
            projected = mtd_by_user.get(user.id, 0.0) * pace
            if not user.monthly_cap:
                continue
            ratio = projected / user.monthly_cap

            if ratio >= 1.0:
                alerts.append(
                    Alert(
                        org_id=org.id,
                        user_id=user.id,
                        team_id=user.team_id,
                        type=AlertType.limit_reached.value,
                        message=(
                            f"{user.name} is on pace to exceed their monthly cap "
                            f"(${projected:,.0f} projected against ${user.monthly_cap:,.0f})."
                        ),
                        created_at=now - timedelta(hours=random.randint(1, 40)),
                    )
                )
            if ratio >= 0.9:
                alerts.append(
                    Alert(
                        org_id=org.id,
                        user_id=user.id,
                        team_id=user.team_id,
                        type=AlertType.warning_90pct.value,
                        message=f"{user.name} is tracking at 90% of their monthly cap.",
                        created_at=now - timedelta(days=random.randint(1, 4)),
                    )
                )
            if ratio >= 0.8:
                alerts.append(
                    Alert(
                        org_id=org.id,
                        user_id=user.id,
                        team_id=user.team_id,
                        type=AlertType.warning_80pct.value,
                        message=f"{user.name} is tracking at 80% of their monthly cap.",
                        created_at=now - timedelta(days=random.randint(3, 9)),
                        is_read=random.random() < 0.4,
                    )
                )

        # A couple of team-level events so the Alerts page isn't all one shape.
        for team_name, team in teams.items():
            team_spend = sum(
                mtd_by_user.get(u.id, 0.0) * pace for u, t in users if t == team_name
            )
            if team.monthly_cap and team_spend >= team.monthly_cap * 0.8:
                team_ratio = team_spend / team.monthly_cap
                if team_ratio >= 1.0:
                    team_alert_type = AlertType.limit_reached.value
                elif team_ratio >= 0.9:
                    team_alert_type = AlertType.warning_90pct.value
                else:
                    team_alert_type = AlertType.warning_80pct.value
                alerts.append(
                    Alert(
                        org_id=org.id,
                        user_id=None,
                        team_id=team.id,
                        type=team_alert_type,
                        message=(
                            f"Team {team_name} is at {team_spend / team.monthly_cap:.0%} "
                            f"of its ${team.monthly_cap:,.0f} monthly cap."
                        ),
                        created_at=now - timedelta(hours=random.randint(2, 60)),
                    )
                )

        db.bulk_save_objects(alerts)
        db.commit()

        total_30d = sum(log.cost_usd for log in logs)
        over = sum(
            1
            for u, _ in users
            if u.monthly_cap and mtd_by_user.get(u.id, 0.0) * pace >= u.monthly_cap
        )

        print(f"Wrote {len(alerts)} alerts.")
        print(f"\nDemo org ready: {org.name} (slug: {org.slug})")
        print("  Login:             admin@test.com / demo123")
        print(f"  Users:             {len(users)} across {len(TEAMS)} teams")
        print(f"  Spend (30 days):   ${total_30d:,.2f}")
        print(f"  Spend (month-to-date): ${mtd_total:,.2f} "
              f"against a ${org.monthly_budget:,.0f} budget")
        print(f"  Users on pace to exceed cap: {over}")
        print(f"  Proxy base URL:    <your-host>/v1/org/{org.slug}")
        sample = users[0][0]
        print(f"  Sample proxy key:  {sample.proxy_api_key}  ({sample.name})")
    finally:
        db.close()


def demo_org_exists() -> bool:
    db = SessionLocal()
    try:
        return (
            db.execute(
                select(Organization).where(Organization.slug == ORG_SLUG)
            ).scalar_one_or_none()
            is not None
        )
    finally:
        db.close()


def seed_if_missing() -> None:
    """Idempotent entry point safe to call from app startup.

    Never wipes existing data — only seeds when the demo org doesn't exist yet,
    so repeated calls (e.g. every cold start on a free-tier host) are harmless.
    """
    init_db()
    if demo_org_exists():
        print("Demo org already present; skipping seed.")
        return
    seed()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the AI Cost Governor demo data.")
    parser.add_argument(
        "--keep", action="store_true", help="skip seeding if the demo org already exists"
    )
    args = parser.parse_args()

    init_db()
    exists = demo_org_exists()

    if exists and args.keep:
        print("Demo org already present; nothing to do.")
        return 0

    db = SessionLocal()
    try:
        wipe(db)
    finally:
        db.close()

    seed()
    return 0


if __name__ == "__main__":
    sys.exit(main())
