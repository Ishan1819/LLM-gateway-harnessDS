"""Technique 3: log / tool-output importance scoring + truncation.

Inspired by the general idea in Headroom's `log_compressor.py` (score each
line by how much signal it carries — errors and summaries matter, routine
INFO/DEBUG noise doesn't — then keep only a token budget's worth of the
highest-signal lines, in original order, with an "N lines omitted" marker
for the rest). Reimplemented from scratch here with a small fixed-weight
regex scorer; no adaptive sizing or Rust involved.

Good for: large JSON/tool-output dumps, CI/build logs, stack traces — text
that is mostly low-information noise punctuated by a few important lines.
"""

from __future__ import annotations

import re

_ERROR_RE = re.compile(r"\b(error|fail(?:ed)?|exception|traceback|critical)\b", re.IGNORECASE)
_WARN_RE = re.compile(r"\b(warn(?:ing)?|deprecated)\b", re.IGNORECASE)
_SUMMARY_RE = re.compile(r"^(=+.*=+|-{5,}.*|\d+ (passed|failed|error|warning)s?\b.*)$", re.IGNORECASE)
_STACK_FRAME_RE = re.compile(r'^\s*(at |File "|  File )')
_NORMALIZE_RE = re.compile(r"[0-9a-fA-F]{6,}|\d+")

# `collapse.py` (technique 1) emits pointer lines like "... (repeats 3 lines
# identical to lines 5-7)" wherever it removed a real duplicate. Those
# pointers are themselves near-identical to each other, which would make
# already-deduplicated text look artificially repetitive to the log-likeness
# check below -- excluded so a second compression pass doesn't get triggered
# by the first pass's own bookkeeping.
_COMPRESSION_MARKER_PREFIX = "... ("

MIN_KEEP_LINES = 10
DEFAULT_KEEP_RATIO = 0.25
LOG_LIKE_UNIQUENESS_THRESHOLD = 0.5


def _score_line(line: str) -> float:
    stripped = line.strip()
    if not stripped:
        return 0.0
    score = 0.05
    if _ERROR_RE.search(stripped):
        score = 1.0
    elif _WARN_RE.search(stripped):
        score = 0.5
    if _SUMMARY_RE.match(stripped):
        score = max(score, 0.8)
    if _STACK_FRAME_RE.match(line):
        score += 0.3
    return score


def _normalize(line: str) -> str:
    return _NORMALIZE_RE.sub("#", line.strip())


def _is_log_like(lines: list[str]) -> bool:
    """Only text with a templated/repetitive structure (typical of logs and
    tool output, e.g. the same message shape repeated with different
    timestamps/ids) should be truncated by this technique. Genuinely unique
    long-form text -- most lines distinct even after stripping digits/hex --
    is left untouched so we don't silently drop real content.
    """
    non_empty = [
        line
        for line in lines
        if line.strip() and not line.strip().startswith(_COMPRESSION_MARKER_PREFIX)
    ]
    if not non_empty:
        return False
    normalized = {_normalize(line) for line in non_empty}
    uniqueness_ratio = len(normalized) / len(non_empty)
    return uniqueness_ratio < LOG_LIKE_UNIQUENESS_THRESHOLD


def compress_log(text: str, keep_ratio: float = DEFAULT_KEEP_RATIO, min_keep: int = MIN_KEEP_LINES) -> str:
    """Keep only the highest-signal lines (errors, warnings, summaries),
    always preserving the first and last line, dropping low-score /
    near-duplicate noise, in a fixed token/line budget.

    Only applies to text that looks log-shaped (see `_is_log_like`); other
    long text is returned unchanged, since aggressive truncation would
    destroy real content rather than remove noise.
    """
    lines = text.split("\n")
    n = len(lines)
    if n <= min_keep:
        return text
    if not _is_log_like(lines):
        return text

    budget = max(min_keep, int(n * keep_ratio))
    always_keep = {0, n - 1}
    scored = [(i, _score_line(line)) for i, line in enumerate(lines) if i not in always_keep]
    ranked = sorted(scored, key=lambda t: t[1], reverse=True)

    kept: set[int] = set(always_keep)
    seen_normalized: set[str] = set()
    for i, score in ranked:
        if len(kept) >= budget:
            break
        if score <= 0.05:
            continue
        norm = _normalize(lines[i])
        if score < 0.8 and norm in seen_normalized:
            continue  # collapse near-identical warnings/noise
        seen_normalized.add(norm)
        kept.add(i)

    kept_sorted = sorted(kept)
    out: list[str] = []
    prev = -1
    for i in kept_sorted:
        if i != prev + 1:
            omitted = i - prev - 1
            out.append(f"... [{omitted} line{'s' if omitted != 1 else ''} omitted] ...")
        out.append(lines[i])
        prev = i
    if prev != n - 1:
        omitted = n - 1 - prev
        out.append(f"... [{omitted} line{'s' if omitted != 1 else ''} omitted] ...")

    return "\n".join(out)
