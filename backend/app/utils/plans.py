"""Subscription plans and what each one unlocks.

One source of truth for tiers: the backend enforces the limits here, and the
same shape is served to the dashboard so the UI never hardcodes a second copy.
"""

from __future__ import annotations

FREE = "free"
STANDARD = "standard"
PREMIUM = "premium"

# Feature keys used by the gate. Keep these stable — the frontend routes
# reference them by name.
F_DASHBOARD = "dashboard"
F_USER_CAPS = "user_caps"
F_TEAM_CAPS = "team_caps"
F_ALERTS = "alerts"
F_SAVINGS = "savings"
F_OPTIMIZER = "optimizer"
F_CUSTOM_PRICING = "custom_pricing"

PLANS: dict[str, dict] = {
    FREE: {
        "id": FREE,
        "name": "Free",
        "price_monthly": 0,
        "tagline": "See where the money goes.",
        "max_users": 5,
        "history_days": 7,
        "features": [F_DASHBOARD, F_USER_CAPS],
        "highlights": [
            "Real-time spend tracking across OpenAI and Anthropic",
            "Up to 5 tracked developers",
            "Per-user monthly spending caps",
            "7 days of usage history",
        ],
    },
    STANDARD: {
        "id": STANDARD,
        "name": "Standard",
        "price_monthly": 49,
        "tagline": "Control it, team by team.",
        "max_users": 50,
        "history_days": 90,
        "features": [F_DASHBOARD, F_USER_CAPS, F_TEAM_CAPS, F_ALERTS, F_SAVINGS],
        "highlights": [
            "Everything in Free",
            "Up to 50 developers, organised into teams",
            "Daily + monthly caps, per user and per team",
            "Automatic 80% / 90% budget alerts",
            "Savings report with month-end projections",
            "90 days of usage history",
        ],
    },
    PREMIUM: {
        "id": PREMIUM,
        "name": "Premium",
        "price_monthly": 199,
        "tagline": "Spend less for the same work.",
        "max_users": 0,  # 0 = unlimited
        "history_days": 0,  # 0 = unlimited
        "features": [
            F_DASHBOARD,
            F_USER_CAPS,
            F_TEAM_CAPS,
            F_ALERTS,
            F_SAVINGS,
            F_OPTIMIZER,
            F_CUSTOM_PRICING,
        ],
        "highlights": [
            "Everything in Standard",
            "Unlimited developers and full usage history",
            "Cost Optimizer: model right-sizing with dollar estimates",
            "Repeat-prompt detection across every team",
            "Per-team prompt efficiency guidance",
            "Editable pricing table for negotiated provider rates",
        ],
    },
}

PLAN_ORDER = [FREE, STANDARD, PREMIUM]

# Human-readable labels for gate messages.
FEATURE_LABELS = {
    F_DASHBOARD: "Usage dashboard",
    F_USER_CAPS: "Per-user caps",
    F_TEAM_CAPS: "Team caps",
    F_ALERTS: "Budget alerts",
    F_SAVINGS: "Savings report",
    F_OPTIMIZER: "Cost Optimizer",
    F_CUSTOM_PRICING: "Custom pricing table",
}


def get_plan(plan_id: str | None) -> dict:
    return PLANS.get((plan_id or FREE).lower(), PLANS[FREE])


def has_feature(plan_id: str | None, feature: str) -> bool:
    return feature in get_plan(plan_id)["features"]


def required_plan_for(feature: str) -> str:
    """Cheapest plan that includes a feature — drives the upgrade prompt."""
    for plan_id in PLAN_ORDER:
        if feature in PLANS[plan_id]["features"]:
            return plan_id
    return PREMIUM


def public_plans() -> list[dict]:
    return [PLANS[p] for p in PLAN_ORDER]
