from app.services.cost_engine import compute_cost_breakdown, finalize_actual_cost
from app.utils.pricing import calculate_cost


def test_compression_and_routing_savings_sum_to_total():
    breakdown = compute_cost_breakdown(
        original_tokens=10_000,
        compressed_tokens=2_000,
        original_model="gpt-4o",
        selected_model="gpt-4o-mini",
    )
    assert round(breakdown.compression_savings_usd + breakdown.routing_savings_usd, 6) == round(
        breakdown.total_savings_usd, 6
    )


def test_no_compression_no_routing_change_means_zero_savings():
    breakdown = compute_cost_breakdown(
        original_tokens=5_000,
        compressed_tokens=5_000,
        original_model="gpt-4o-mini",
        selected_model="gpt-4o-mini",
    )
    assert breakdown.compression_savings_usd == 0.0
    assert breakdown.routing_savings_usd == 0.0
    assert breakdown.total_savings_usd == 0.0
    assert breakdown.total_savings_pct == 0.0


def test_compression_only_savings_isolated_when_model_unchanged():
    breakdown = compute_cost_breakdown(
        original_tokens=10_000,
        compressed_tokens=5_000,
        original_model="gpt-4o",
        selected_model="gpt-4o",
    )
    assert breakdown.compression_savings_usd > 0
    assert breakdown.routing_savings_usd == 0.0
    assert breakdown.total_savings_usd == breakdown.compression_savings_usd


def test_routing_only_savings_isolated_when_tokens_unchanged():
    breakdown = compute_cost_breakdown(
        original_tokens=5_000,
        compressed_tokens=5_000,
        original_model="gpt-4o",
        selected_model="gpt-4o-mini",
    )
    assert breakdown.routing_savings_usd > 0
    assert breakdown.compression_savings_usd == 0.0
    assert breakdown.total_savings_usd == breakdown.routing_savings_usd


def test_baseline_cost_matches_pricing_calculation():
    breakdown = compute_cost_breakdown(
        original_tokens=3_000,
        compressed_tokens=1_000,
        original_model="claude-sonnet-5",
        selected_model="claude-haiku-4-5",
    )
    expected_baseline = calculate_cost(
        "claude-sonnet-5", 3_000, breakdown.assumed_output_tokens
    )
    assert breakdown.original_model_cost_estimate == expected_baseline


def test_zero_original_tokens_no_divide_by_zero():
    # Zero prompt tokens still has a nonzero baseline cost from the assumed
    # output tokens, so a model change alone can legitimately show savings;
    # what must never happen is a ZeroDivisionError.
    breakdown = compute_cost_breakdown(
        original_tokens=0,
        compressed_tokens=0,
        original_model="gpt-4o",
        selected_model="gpt-4o-mini",
    )
    assert breakdown.token_reduction_pct == 0.0


def test_zero_tokens_and_zero_baseline_cost_gives_zero_pct():
    # Free model, zero tokens -> baseline cost is genuinely zero.
    breakdown = compute_cost_breakdown(
        original_tokens=0,
        compressed_tokens=0,
        original_model="gpt-4o-mini",
        selected_model="gpt-4o-mini",
        assumed_output_tokens=0,
    )
    assert breakdown.original_model_cost_estimate == 0.0
    assert breakdown.total_savings_pct == 0.0


def test_is_estimate_true_until_finalized():
    breakdown = compute_cost_breakdown(
        original_tokens=2_000,
        compressed_tokens=1_000,
        original_model="gpt-4o",
        selected_model="gpt-4o-mini",
    )
    assert breakdown.is_estimate is True
    assert breakdown.actual_selected_model_cost is None


def test_finalize_actual_cost_sets_real_completion_cost():
    breakdown = compute_cost_breakdown(
        original_tokens=2_000,
        compressed_tokens=1_000,
        original_model="gpt-4o",
        selected_model="gpt-4o-mini",
    )
    finalize_actual_cost(breakdown, actual_prompt_tokens=1_000, actual_completion_tokens=42)
    assert breakdown.actual_completion_tokens == 42
    assert breakdown.actual_selected_model_cost == calculate_cost("gpt-4o-mini", 1_000, 42)
    # the counterfactual baseline is never "actualized" -- it was never called
    assert breakdown.original_model_cost_estimate > 0
    assert breakdown.is_estimate is True


def test_downgrading_to_cheaper_model_never_shows_negative_savings():
    breakdown = compute_cost_breakdown(
        original_tokens=8_000,
        compressed_tokens=3_000,
        original_model="claude-opus-5",
        selected_model="gpt-4o-mini",
    )
    assert breakdown.total_savings_usd > 0
    assert breakdown.compression_savings_usd >= 0
    assert breakdown.routing_savings_usd >= 0
