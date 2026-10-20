"""Live end-to-end test of the governed proxy pipeline.

Sends several deliberately-crafted requests to
POST /v1/org/{slug}/governed/chat/completions and prints, for each one:
  - the requested model vs the model it actually got routed to
  - the complexity tier and why
  - token counts before/after compression
  - estimated savings

Requires the backend running locally (uvicorn) and a real provider key
configured for the demo org, since this makes an actual upstream LLM call.
Point PROXY_KEY at any acg-... key from `python seed_data.py` output, or
create one via the dashboard's Users page.

Run with (from backend/):
    python scripts/test_governance_live.py
"""

from __future__ import annotations

import os

import httpx

BASE_URL = os.environ.get("ACG_GOVERNED_URL", "http://127.0.0.1:8000/v1/org/demo/governed")
PROXY_KEY = os.environ.get("ACG_PROXY_KEY", "")  # an acg-... key from the Users page

# Reused across the cross-turn-dedup example: a big chunk that gets "re-pasted"
# verbatim in a later message, the way an agent re-reading a file would.
_FILE_CONTENT = """def calculate_discount(price, customer_tier):
    if customer_tier == "gold":
        return price * 0.8
    elif customer_tier == "silver":
        return price * 0.9
    else:
        return price

def apply_tax(price, region):
    rates = {"CA": 0.0725, "NY": 0.08875, "TX": 0.0625}
    return price * (1 + rates.get(region, 0.05))"""

_REPEATED_LOG = "\n".join(
    [f"[{i:03d}] health check OK: latency=42ms" for i in range(40)]
)

EXAMPLES: list[dict] = [
    {
        "label": "1. Simple lookup -> Tier 1, cheap model, minimal compression",
        "requested_model": "gpt-4o",
        "messages": [
            {"role": "user", "content": "What is the capital of France?"}
        ],
    },
    {
        "label": "2. Reasoning + code -> Tier 3, capable model required",
        "requested_model": "gpt-4o-mini",
        "messages": [
            {
                "role": "user",
                "content": (
                    "Explain step-by-step why this function has a bug, analyze "
                    "the trade-offs of two possible fixes, and debug the root cause:\n\n"
                    "```python\n" + _FILE_CONTENT + "\n```"
                ),
            }
        ],
    },
    {
        "label": "3. Structured output request -> Tier 2",
        "requested_model": "gpt-4o",
        "messages": [
            {
                "role": "user",
                "content": (
                    "Return only structured output: format the top 3 planets by "
                    "size as a JSON array with fields name and diameter_km."
                ),
            }
        ],
    },
    {
        "label": "4. Cross-turn dedup -> same file content pasted twice",
        "requested_model": "gpt-4o",
        "messages": [
            {
                "role": "user",
                "content": "Here's the file:\n\n" + _FILE_CONTENT + "\n\nWhat does calculate_discount do?",
            },
            {
                "role": "assistant",
                "content": "It applies a tier-based discount: 20% off for gold, 10% off for silver.",
            },
            {
                "role": "user",
                "content": (
                    "Now re-reading the same file to check the tax logic:\n\n"
                    + _FILE_CONTENT
                    + "\n\nIs apply_tax correct for a customer in NY?"
                ),
            },
        ],
    },
    {
        "label": "5. Repeated-block collapse -> noisy repetitive log dump",
        "requested_model": "gpt-4o",
        "messages": [
            {
                "role": "user",
                "content": (
                    "Here are the last 40 health check results, tell me if "
                    "anything looks wrong:\n\n" + _REPEATED_LOG
                ),
            }
        ],
    },
    {
        "label": "6. Large context -> pushes complexity via context size alone",
        "requested_model": "claude-opus-5",
        "messages": [
            {
                "role": "user",
                "content": "Summarize this:\n\n" + (_FILE_CONTENT + "\n\n") * 120,
            }
        ],
    },
]


def run_example(client: httpx.Client, example: dict) -> None:
    print("=" * 78)
    print(example["label"])
    print("-" * 78)

    resp = client.post(
        "/chat/completions",
        headers={"Authorization": f"Bearer {PROXY_KEY}"},
        json={"model": example["requested_model"], "messages": example["messages"]},
    )

    if resp.status_code >= 400:
        print(f"  HTTP {resp.status_code}: {resp.text[:300]}")
        return

    h = resp.headers
    requested = h.get("x-governance-requested-model")
    routed = h.get("x-governance-routed-model")
    orig_tok = h.get("x-governance-original-tokens")
    comp_tok = h.get("x-governance-compressed-tokens")
    reduction = h.get("x-governance-token-reduction-pct")
    tier = h.get("x-governance-complexity-tier")
    savings_usd = h.get("x-governance-estimated-savings-usd")
    savings_pct = h.get("x-governance-estimated-savings-pct")

    print(f"  Requested model:     {requested}")
    print(f"  Routed model:        {routed}"
          + ("  <-- downgraded/upgraded" if requested != routed else "  (unchanged)"))
    print(f"  Complexity tier:     {tier}")
    print(f"  Tokens:              {orig_tok} -> {comp_tok}  ({reduction}% reduction)")
    print(f"  Estimated savings:   ${savings_usd}  ({savings_pct}%)")


def main() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=60.0) as client:
        for example in EXAMPLES:
            run_example(client, example)
    print("=" * 78)


if __name__ == "__main__":
    main()
