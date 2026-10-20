"""Cost engine: separates token savings (compression) from $ savings from
model selection (routing), and produces pre-request cost estimates.

Output tokens are unknown before the request executes, so every figure here
is explicitly an *estimate* (`is_estimate=True`, based on
`ASSUMED_OUTPUT_TOKENS`) until the real response comes back and
`finalize_actual_cost` recomputes the selected model's cost from real
completion tokens. The "original model" baseline stays an estimate forever,
since it's a counterfactual -- that model was never actually called.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.utils.pricing import calculate_cost

ASSUMED_OUTPUT_TOKENS = 500


@dataclass
class CostBreakdown:
    original_input_tokens: int
    compressed_input_tokens: int
    token_reduction_pct: float

    original_model: str
    selected_model: str
    assumed_output_tokens: int

    # Pre-request estimates (output tokens unknown until the LLM responds).
    original_model_cost_estimate: float  # baseline: original model, uncompressed tokens
    selected_model_cost_estimate: float  # what actually gets spent: selected model, compressed tokens

    compression_savings_usd: float  # isolates: same model, fewer tokens
    routing_savings_usd: float  # isolates: same (already-compressed) tokens, cheaper model
    total_savings_usd: float
    total_savings_pct: float

    is_estimate: bool = True
    actual_completion_tokens: int | None = None
    actual_selected_model_cost: float | None = None

    def as_dict(self) -> dict:
        return {
            "original_input_tokens": self.original_input_tokens,
            "compressed_input_tokens": self.compressed_input_tokens,
            "token_reduction_pct": self.token_reduction_pct,
            "original_model": self.original_model,
            "selected_model": self.selected_model,
            "assumed_output_tokens": self.assumed_output_tokens,
            "original_model_cost_estimate_usd": self.original_model_cost_estimate,
            "selected_model_cost_estimate_usd": self.selected_model_cost_estimate,
            "compression_savings_usd": self.compression_savings_usd,
            "routing_savings_usd": self.routing_savings_usd,
            "total_savings_usd": self.total_savings_usd,
            "total_savings_pct": self.total_savings_pct,
            "is_estimate": self.is_estimate,
            "actual_completion_tokens": self.actual_completion_tokens,
            "actual_selected_model_cost_usd": self.actual_selected_model_cost,
        }


def compute_cost_breakdown(
    *,
    original_tokens: int,
    compressed_tokens: int,
    original_model: str,
    selected_model: str,
    assumed_output_tokens: int = ASSUMED_OUTPUT_TOKENS,
) -> CostBreakdown:
    """Pre-request estimate, computed before the LLM call executes."""
    reduction_pct = (
        round(100 * (original_tokens - compressed_tokens) / original_tokens, 2)
        if original_tokens > 0
        else 0.0
    )

    # Baseline: cost of sending the *uncompressed* prompt to the *originally
    # requested* model -- the "do nothing" counterfactual everything else is
    # measured against.
    baseline_cost = calculate_cost(original_model, original_tokens, assumed_output_tokens)

    # Isolates compression's contribution: same model, fewer tokens.
    compressed_on_original_model_cost = calculate_cost(
        original_model, compressed_tokens, assumed_output_tokens
    )
    compression_savings = round(baseline_cost - compressed_on_original_model_cost, 8)

    # What actually gets spent: selected (possibly cheaper) model, compressed tokens.
    selected_cost = calculate_cost(selected_model, compressed_tokens, assumed_output_tokens)

    # Isolates routing's contribution: same (already-compressed) tokens, cheaper model.
    routing_savings = round(compressed_on_original_model_cost - selected_cost, 8)

    total_savings = round(baseline_cost - selected_cost, 8)
    total_savings_pct = round(100 * total_savings / baseline_cost, 2) if baseline_cost > 0 else 0.0

    return CostBreakdown(
        original_input_tokens=original_tokens,
        compressed_input_tokens=compressed_tokens,
        token_reduction_pct=reduction_pct,
        original_model=original_model,
        selected_model=selected_model,
        assumed_output_tokens=assumed_output_tokens,
        original_model_cost_estimate=baseline_cost,
        selected_model_cost_estimate=selected_cost,
        compression_savings_usd=compression_savings,
        routing_savings_usd=routing_savings,
        total_savings_usd=total_savings,
        total_savings_pct=total_savings_pct,
    )


def finalize_actual_cost(
    breakdown: CostBreakdown, actual_prompt_tokens: int, actual_completion_tokens: int
) -> CostBreakdown:
    """Recompute the selected model's cost from the real response, once known.

    The original-model baseline is left untouched -- it was never actually
    called, so it has no "actual" figure to graduate to.
    """
    breakdown.actual_completion_tokens = actual_completion_tokens
    breakdown.actual_selected_model_cost = calculate_cost(
        breakdown.selected_model, actual_prompt_tokens, actual_completion_tokens
    )
    return breakdown
