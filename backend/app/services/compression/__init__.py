"""Headroom-inspired context compression pipeline.

Combines three deterministic, non-ML compression techniques (see
`dedup.py`, `collapse.py`, `log_scorer.py`) and measures real token savings
with tiktoken. Each technique is a from-scratch reimplementation of an
algorithmic idea found in the Headroom project (Apache-2.0); no Headroom
source was copied.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .collapse import collapse
from .dedup import dedup_turns
from .log_scorer import compress_log
from .tokenizer import count_tokens

TECHNIQUES = ["cross_turn_dedup", "repeated_block_collapse", "log_importance_scoring"]
# Cheap pre-filter so trivially short blocks skip log-scoring entirely; the
# real correctness gate is `_is_log_like()` inside `compress_log` itself.
# Kept close to log_scorer.MIN_KEEP_LINES (10) rather than a large arbitrary
# number, so realistically-sized log excerpts (e.g. a ~30-line trace) still
# get evaluated instead of silently skipping technique 3.
LOG_SCORING_LINE_THRESHOLD = 15
BLOCK_SEPARATOR = "\n\n---\n\n"


@dataclass
class CompressionResult:
    original_text: str
    compressed_text: str
    original_tokens: int
    compressed_tokens: int
    techniques_applied: list[str] = field(default_factory=lambda: list(TECHNIQUES))

    @property
    def tokens_saved(self) -> int:
        return max(0, self.original_tokens - self.compressed_tokens)

    @property
    def reduction_pct(self) -> float:
        if self.original_tokens == 0:
            return 0.0
        return round(100 * self.tokens_saved / self.original_tokens, 2)

    def as_dict(self) -> dict:
        return {
            "original_tokens": self.original_tokens,
            "compressed_tokens": self.compressed_tokens,
            "tokens_saved": self.tokens_saved,
            "reduction_pct": self.reduction_pct,
            "techniques_applied": self.techniques_applied,
        }


def compress_conversation(blocks: list[str]) -> CompressionResult:
    """Compress an ordered list of message/turn texts, applying all three
    techniques: cross-turn dedup first (needs multiple blocks), then
    repeated-block collapse, then log importance scoring for long blocks.
    """
    original_text = BLOCK_SEPARATOR.join(blocks)
    original_tokens = count_tokens(original_text)

    deduped = dedup_turns(blocks) if len(blocks) > 1 else list(blocks)
    collapsed = [collapse(b) for b in deduped]
    scored = [
        compress_log(b) if b.count("\n") + 1 > LOG_SCORING_LINE_THRESHOLD else b
        for b in collapsed
    ]

    compressed_text = BLOCK_SEPARATOR.join(scored)
    compressed_tokens = count_tokens(compressed_text)

    return CompressionResult(
        original_text=original_text,
        compressed_text=compressed_text,
        original_tokens=original_tokens,
        compressed_tokens=compressed_tokens,
    )


def compress_text(text: str) -> CompressionResult:
    """Compress a single blob of text (e.g. one large tool-output payload).
    Cross-turn dedup is skipped since there is only one turn.
    """
    return compress_conversation([text])
