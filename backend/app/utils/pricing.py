"""Model pricing table.

Prices are USD per 1,000,000 tokens. Edit this file when a provider changes
its rate card — nothing else in the codebase hardcodes a price.

Anthropic rates below are the current first-party API rates (verified against
Anthropic's published pricing). Note these differ from some older figures that
circulate: Claude Opus 5 is $5/$25 (not $15/$75), and Claude Haiku 4.5 is
$1/$5 (not $0.25/$1.25).
"""

from __future__ import annotations

# provider -> model id -> (input $/1M, output $/1M)
PRICING: dict[str, dict[str, tuple[float, float]]] = {
    "openai": {
        "gpt-4o": (2.50, 10.00),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4-turbo": (10.00, 30.00),
        "gpt-4.1": (2.00, 8.00),
        "gpt-4.1-mini": (0.40, 1.60),
        "gpt-3.5-turbo": (0.50, 1.50),
        "o3-mini": (1.10, 4.40),
    },
    "anthropic": {
        "claude-fable-5": (10.00, 50.00),
        "claude-opus-5": (5.00, 25.00),
        "claude-opus-4-8": (5.00, 25.00),
        "claude-opus-4-7": (5.00, 25.00),
        "claude-opus-4-6": (5.00, 25.00),
        "claude-sonnet-5": (3.00, 15.00),
        "claude-sonnet-4-6": (3.00, 15.00),
        "claude-sonnet-4-5": (3.00, 15.00),
        "claude-haiku-4-5": (1.00, 5.00),
    },
}

# Charged when a model isn't in the table, so unknown models still get costed
# rather than silently recorded as free.
FALLBACK_PRICE: tuple[float, float] = (3.00, 15.00)

# Substring routing: which provider owns a given model name.
ANTHROPIC_MODEL_MARKERS = ("claude", "anthropic")


def detect_provider(model: str) -> str:
    """Route by model name so a single proxy endpoint can serve both providers."""
    lowered = (model or "").lower()
    if any(marker in lowered for marker in ANTHROPIC_MODEL_MARKERS):
        return "anthropic"
    return "openai"


def get_rate(model: str) -> tuple[float, float]:
    provider = detect_provider(model)
    table = PRICING.get(provider, {})
    if model in table:
        return table[model]
    # Tolerate dated snapshots and suffixed variants (e.g. gpt-4o-2024-11-20).
    # Longest prefix wins, so gpt-4o-mini-2024-07-18 is priced as gpt-4o-mini
    # rather than gpt-4o.
    for known in sorted(table, key=len, reverse=True):
        if model.startswith(known):
            return table[known]
    return FALLBACK_PRICE


def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Cost in USD for one request, rounded to sub-cent precision."""
    input_rate, output_rate = get_rate(model)
    cost = (prompt_tokens / 1_000_000) * input_rate + (
        completion_tokens / 1_000_000
    ) * output_rate
    return round(cost, 8)


def list_models() -> list[dict]:
    return [
        {
            "provider": provider,
            "model": model,
            "input_per_1m": rate[0],
            "output_per_1m": rate[1],
        }
        for provider, table in PRICING.items()
        for model, rate in table.items()
    ]
