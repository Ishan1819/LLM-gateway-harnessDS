"""Orchestrates compression -> complexity scoring -> model recommendation
-> cost accounting into a single pipeline, ready to wire into a proxy
endpoint (see `routes/governed.py`).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.complexity_scorer import ComplexityResult, analyze_complexity
from app.services.compression import CompressionResult, compress_conversation
from app.services.cost_engine import CostBreakdown, compute_cost_breakdown
from app.services.model_router import RoutingDecision, recommend_model


@dataclass
class GovernanceResult:
    compression: CompressionResult
    complexity: ComplexityResult
    routing: RoutingDecision
    cost: CostBreakdown

    def as_dict(self) -> dict:
        return {
            "compression": self.compression.as_dict(),
            "complexity": self.complexity.as_dict(),
            "routing": self.routing.as_dict(),
            "cost": self.cost.as_dict(),
        }


def extract_message_blocks(payload: dict) -> list[str]:
    """Pull text blocks (system prompt + each message) out of an OpenAI- or
    Anthropic-style chat payload, for the compression pipeline to operate on.
    """
    blocks: list[str] = []

    system = payload.get("system")
    if isinstance(system, str) and system.strip():
        blocks.append(system)
    elif isinstance(system, list):
        for b in system:
            if isinstance(b, dict) and b.get("text"):
                blocks.append(b["text"])

    for message in payload.get("messages", []) or []:
        content = message.get("content")
        if isinstance(content, str):
            if content.strip():
                blocks.append(content)
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and block.get("text"):
                    blocks.append(block["text"])
                elif block.get("type") == "tool_result":
                    result = block.get("content")
                    if isinstance(result, str):
                        blocks.append(result)
                    elif isinstance(result, list):
                        for rb in result:
                            if isinstance(rb, dict) and rb.get("text"):
                                blocks.append(rb["text"])

    return blocks


def run_governance(payload: dict, requested_model: str) -> GovernanceResult:
    """Run the full compress -> score -> route -> cost pipeline for one request."""
    blocks = extract_message_blocks(payload) or [""]

    compression = compress_conversation(blocks)

    # Complexity is scored from the most recent message (most predictive of
    # what the model actually needs to do) plus the compressed context size.
    focus_text = blocks[-1]
    complexity = analyze_complexity(focus_text, context_tokens=compression.compressed_tokens)

    routing = recommend_model(complexity.tier, compression.compressed_tokens)

    cost = compute_cost_breakdown(
        original_tokens=compression.original_tokens,
        compressed_tokens=compression.compressed_tokens,
        original_model=requested_model or routing.recommended_model,
        selected_model=routing.recommended_model,
    )

    return GovernanceResult(compression=compression, complexity=complexity, routing=routing, cost=cost)
