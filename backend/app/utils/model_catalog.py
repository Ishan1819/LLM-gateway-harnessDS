"""Deterministic capability tiers for models in the pricing table.

Tier 1 = "simple": fast/cheap models -- fine for lookups, formatting,
    short summaries, low-reasoning tasks.
Tier 2 = "capable": solid general-purpose models -- fine for most coding,
    multi-step reasoning, and moderately sized context.
Tier 3 = "frontier": the strongest available models -- reserved for hard
    reasoning, non-trivial coding/architecture, or very large context.

Kept in its own file (separate from `pricing.py`) so the $ rate card and
the capability judgment can be edited independently, but both stay
centralized/config-driven rather than scattered through router logic.
"""

from __future__ import annotations

TIER_NAMES = {1: "simple", 2: "capable", 3: "frontier"}

# provider -> model id -> capability tier
MODEL_TIERS: dict[str, dict[str, int]] = {
    "openai": {
        "gpt-3.5-turbo": 1,
        "gpt-4o-mini": 1,
        "gpt-4.1-mini": 1,
        "o3-mini": 2,
        "gpt-4.1": 2,
        "gpt-4o": 3,
        "gpt-4-turbo": 3,
    },
    "anthropic": {
        "claude-haiku-4-5": 1,
        "claude-sonnet-4-5": 2,
        "claude-sonnet-4-6": 2,
        "claude-sonnet-5": 2,
        "claude-opus-4-6": 3,
        "claude-opus-4-7": 3,
        "claude-opus-4-8": 3,
        "claude-opus-5": 3,
        "claude-fable-5": 3,
    },
}

# Unknown models are assumed mid-capability -- not auto-trusted as cheap
# enough for tier 1, not silently treated as frontier-grade either.
DEFAULT_TIER = 2


def get_tier(model: str) -> int:
    for table in MODEL_TIERS.values():
        if model in table:
            return table[model]
        for known in sorted(table, key=len, reverse=True):
            if model.startswith(known):
                return table[known]
    return DEFAULT_TIER


def models_at_or_above_tier(min_tier: int) -> list[tuple[str, str, int]]:
    """Return (provider, model, tier) triples with capability tier >= min_tier."""
    out: list[tuple[str, str, int]] = []
    for provider, table in MODEL_TIERS.items():
        for model, tier in table.items():
            if tier >= min_tier:
                out.append((provider, model, tier))
    return out
