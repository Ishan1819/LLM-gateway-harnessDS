import pytest

from app.services.model_router import ASSUMED_OUTPUT_TOKENS_FOR_RANKING, recommend_model
from app.utils.model_catalog import get_tier
from app.utils.pricing import calculate_cost


def test_tier_1_recommendation_is_actually_tier_1_or_above():
    decision = recommend_model(required_tier=1, estimated_input_tokens=2000)
    assert get_tier(decision.recommended_model) >= 1


def test_tier_3_recommendation_excludes_cheaper_low_tier_models():
    decision = recommend_model(required_tier=3, estimated_input_tokens=2000)
    assert get_tier(decision.recommended_model) == 3
    # sanity: a tier-1 model must not have been selected for tier-3 work
    assert decision.recommended_model not in ("gpt-4o-mini", "claude-haiku-4-5", "gpt-3.5-turbo")


def test_recommendation_is_the_cheapest_among_eligible_candidates():
    decision = recommend_model(required_tier=2, estimated_input_tokens=3000)
    costs = [c.estimated_cost_usd for c in decision.candidates_considered]
    assert decision.estimated_cost_usd == min(costs)
    assert all(c.tier >= 2 for c in decision.candidates_considered)


def test_estimated_cost_matches_pricing_calculation():
    decision = recommend_model(required_tier=1, estimated_input_tokens=1500)
    expected = calculate_cost(
        decision.recommended_model, 1500, ASSUMED_OUTPUT_TOKENS_FOR_RANKING
    )
    assert decision.estimated_cost_usd == expected


def test_higher_tier_requirement_never_produces_cheaper_recommendation():
    tier1 = recommend_model(required_tier=1, estimated_input_tokens=2000)
    tier3 = recommend_model(required_tier=3, estimated_input_tokens=2000)
    assert tier3.estimated_cost_usd >= tier1.estimated_cost_usd


def test_invalid_tier_raises():
    with pytest.raises(ValueError):
        recommend_model(required_tier=99, estimated_input_tokens=1000)


def test_candidates_considered_sorted_ascending_by_cost():
    decision = recommend_model(required_tier=1, estimated_input_tokens=5000)
    costs = [c.estimated_cost_usd for c in decision.candidates_considered]
    assert costs == sorted(costs)
