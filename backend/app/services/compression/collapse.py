"""Technique 1: repeated-line / repeated-block run-length collapse.

Inspired by the general idea in Headroom's `lossless_compaction.py` (collapse
consecutive duplicate lines and repeated multi-line blocks). Reimplemented
here from scratch as a small, self-contained algorithm: no code was copied
from the Headroom source, only the algorithmic concept.

Good for: noisy tool/CI output, polling loops, repeated conversation history
where the same block of text (e.g. a status message, a re-printed table)
shows up several times verbatim.
"""

from __future__ import annotations

MIN_BLOCK_LINES = 3
MAX_BLOCK_LINES = 64


def collapse_repeated_lines(text: str) -> str:
    """Collapse runs of >=2 identical consecutive lines into one + a marker."""
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        j = i + 1
        while j < n and lines[j] == line:
            j += 1
        run_len = j - i
        out.append(line)
        if run_len >= 2:
            out.append(f"... (previous line repeated {run_len - 1} more time{'s' if run_len - 1 != 1 else ''})")
        i = j
    return "\n".join(out)


def collapse_repeated_blocks(text: str) -> str:
    """Replace later occurrences of an earlier multi-line block with a marker.

    Indexes every MIN_BLOCK_LINES-line window by its first occurrence, and
    when a later window matches one seen before, greedily extends the match
    line-by-line (up to MAX_BLOCK_LINES) so multi-line repeats longer than
    the minimum window are still collapsed in full rather than in
    MIN_BLOCK_LINES-sized pieces.
    """
    lines = text.split("\n")
    n = len(lines)
    seen: dict[tuple[str, ...], int] = {}
    out: list[str] = []
    i = 0
    while i < n:
        matched = False
        if i + MIN_BLOCK_LINES <= n:
            key = tuple(lines[i : i + MIN_BLOCK_LINES])
            start = seen.get(key)
            if start is not None:
                match_len = MIN_BLOCK_LINES
                max_len = min(MAX_BLOCK_LINES, n - i, i - start)
                while match_len < max_len and lines[start + match_len] == lines[i + match_len]:
                    match_len += 1
                out.append(
                    f"... (repeats {match_len} lines identical to lines "
                    f"{start + 1}-{start + match_len})"
                )
                i += match_len
                matched = True
        if not matched:
            if i + MIN_BLOCK_LINES <= n:
                key = tuple(lines[i : i + MIN_BLOCK_LINES])
                if key not in seen:
                    seen[key] = i
            out.append(lines[i])
            i += 1
    return "\n".join(out)


def collapse(text: str) -> str:
    """Apply block collapse first (coarser), then line collapse (finer)."""
    return collapse_repeated_lines(collapse_repeated_blocks(text))
