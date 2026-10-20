"""Cheapest-capable model recommendation.

Given a required capability tier (from `complexity_scorer.analyze_complexity`)
and an estimated input token count, picks the lowest-estimated-cost model
whose capability tier is high enough for the task -- never blindly the
globally cheapest model, and never an unnecessarily expensive one.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.utils.model_catalog import TIER_NAMES, models_at_or_above_tier
from app.utils.pricing import calculate_cost

# Output tokens are unknown before the request executes. This assumption is
# used only to *rank* candidate models against each other consistently; the
# real cost is computed after the response using actual completion tokens.
ASSUMED_OUTPUT_TOKENS_FOR_RANKING = 500


@dataclass
class ModelCandidate:
    provider: str
    model: str
    tier: int
    estimated_cost_usd: float


@dataclass
class RoutingDecision:
    recommended_provider: str
    recommended_model: str
    required_tier: int
    required_tier_name: str
    estimated_cost_usd: float
    candidates_considered: list[ModelCandidate]

    def as_dict(self) -> dict:
        return {
            "recommended_provider": self.recommended_provider,
            "recommended_model": self.recommended_model,
            "required_tier": self.required_tier,
            "required_tier_name": self.required_tier_name,
            "estimated_cost_usd": self.estimated_cost_usd,
            "candidates_considered": [
                {
                    "provider": c.provider,
                    "model": c.model,
                    "tier": c.tier,
                    "estimated_cost_usd": c.estimated_cost_usd,
                }
                for c in self.candidates_considered
            ],
        }


def recommend_model(required_tier: int, estimated_input_tokens: int) -> RoutingDecision:
    """Recommend the cheapest model capable of handling `required_tier` work."""
    pool = models_at_or_above_tier(required_tier)
    if not pool:
        raise ValueError(f"No models configured at or above tier {required_tier}")

    candidates = [
        ModelCandidate(
            provider=provider,
            model=model,
            tier=tier,
            estimated_cost_usd=calculate_cost(
                model, estimated_input_tokens, ASSUMED_OUTPUT_TOKENS_FOR_RANKING
            ),
        )
        for provider, model, tier in pool
    ]
    candidates.sort(key=lambda c: (c.estimated_cost_usd, c.tier))
    best = candidates[0]

    return RoutingDecision(
        recommended_provider=best.provider,
        recommended_model=best.model,
        required_tier=required_tier,
        required_tier_name=TIER_NAMES[required_tier],
        estimated_cost_usd=best.estimated_cost_usd,
        candidates_considered=sorted(candidates, key=lambda c: c.estimated_cost_usd),
    )
