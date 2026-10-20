"""Deterministic task-complexity scorer.

No LLM calls involved: purpose-built regex/heuristic signals over the
request text plus context size, mapped to a capability tier. Kept
deterministic on purpose -- spending an expensive LLM call just to decide
which LLM should handle a request would defeat the point of cost
governance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_CODE_RE = re.compile(
    r"```|\bdef\s+\w+\(|\bclass\s+\w+\b|\bfunction\s+\w+\(|\bimport\s+\w+|"
    r"\bSELECT\b.+\bFROM\b|</?\w+>|=>|\$\{|\bconsole\.log\(",
    re.IGNORECASE,
)
_REASONING_RE = re.compile(
    r"\b(why|explain (the|your) reasoning|step[- ]by[- ]step|prove|derive|"
    r"analyz(e|ing)|compare and contrast|trade-?offs?|root cause|debug|"
    r"optimi[sz]e|design a|architect|plan (a|an|the)|figure out)\b",
    re.IGNORECASE,
)
_STRUCTURED_RE = re.compile(
    r"\b(json|yaml|xml|csv|schema|table format|return only|structured output|"
    r"format (it |your (response|answer) )?as)\b",
    re.IGNORECASE,
)
_SIMPLE_RE = re.compile(
    r"\b(summarize|what is|define|translate|rewrite|shorten|list the|"
    r"give me a|tl;?dr)\b",
    re.IGNORECASE,
)

# Composite 0-100 score thresholds mapping to a required capability tier.
# Any single strong signal (reasoning language = 25, code = 25, large
# context = 30) should be enough on its own to justify a "capable" model --
# a threshold of 30 would mean a reasoning-only request under ~1000 tokens
# (the single most common shape of a real analytical prompt) could never
# cross out of tier 1 no matter how demanding the reasoning actually is.
TIER_2_THRESHOLD = 20
TIER_3_THRESHOLD = 65


@dataclass
class ComplexityResult:
    score: float
    tier: int
    context_tokens: int
    has_code: bool
    reasoning_required: bool
    structured_output_required: bool
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "tier": self.tier,
            "context_tokens": self.context_tokens,
            "has_code": self.has_code,
            "reasoning_required": self.reasoning_required,
            "structured_output_required": self.structured_output_required,
            "reasons": self.reasons,
        }


def _context_size_score(context_tokens: int) -> tuple[float, str | None]:
    if context_tokens > 16_000:
        return 30.0, f"large context ({context_tokens:,} tokens)"
    if context_tokens > 4_000:
        return 20.0, f"moderate context ({context_tokens:,} tokens)"
    if context_tokens > 1_000:
        return 10.0, None
    return 0.0, None


def analyze_complexity(text: str, context_tokens: int) -> ComplexityResult:
    """Score a request deterministically from text signals + context size."""
    reasons: list[str] = []
    score = 0.0

    size_score, size_reason = _context_size_score(context_tokens)
    score += size_score
    if size_reason:
        reasons.append(size_reason)

    has_code = bool(_CODE_RE.search(text))
    if has_code:
        score += 25.0
        reasons.append("contains code")

    reasoning_required = bool(_REASONING_RE.search(text))
    if reasoning_required:
        score += 25.0
        reasons.append("multi-step reasoning language detected")

    structured_output_required = bool(_STRUCTURED_RE.search(text))
    if structured_output_required:
        score += 15.0
        reasons.append("structured output requested")

    if _SIMPLE_RE.search(text) and not (has_code or reasoning_required):
        score -= 10.0
        reasons.append("simple lookup/formatting phrasing")

    score = max(0.0, min(100.0, score))

    if score >= TIER_3_THRESHOLD:
        tier = 3
    elif score >= TIER_2_THRESHOLD:
        tier = 2
    else:
        tier = 1

    return ComplexityResult(
        score=round(score, 1),
        tier=tier,
        context_tokens=context_tokens,
        has_code=has_code,
        reasoning_required=reasoning_required,
        structured_output_required=structured_output_required,
        reasons=reasons,
    )
