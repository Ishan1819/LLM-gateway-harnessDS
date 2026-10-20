"""Technique 2: cross-turn verbatim dedup.

Inspired by the general idea in Headroom's `cross_turn_dedup.py` (detect when
a later turn repeats a verbatim chunk of an earlier turn — e.g. a file that
gets re-read, or a RAG chunk that gets shown again — and replace the repeat
with a short pointer instead of paying for the tokens twice). Reimplemented
from scratch here using stdlib `difflib.SequenceMatcher`, which is a good
fit for finding the longest matching contiguous line runs between two turns.

Good for: agent transcripts where the same tool output / file / context
chunk shows up more than once across the conversation.
"""

from __future__ import annotations

import difflib

MIN_MATCH_LINES = 3
MIN_MATCH_CHARS = 40


def dedup_turns(blocks: list[str]) -> list[str]:
    """Replace verbatim repeats of earlier blocks' lines with pointers.

    `blocks` is an ordered list of message/turn texts. For each block after
    the first, any contiguous run of lines that already appeared in an
    earlier block is replaced with a short pointer back to it.
    """
    line_lists = [b.split("\n") for b in blocks]
    out: list[str] = []

    for idx, cur_lines in enumerate(line_lists):
        if idx == 0:
            out.append(blocks[0])
            continue

        working = list(cur_lines)
        for earlier_idx in range(idx):
            earlier_lines = line_lists[earlier_idx]
            matcher = difflib.SequenceMatcher(None, earlier_lines, working, autojunk=False)
            matches = [m for m in matcher.get_matching_blocks() if m.size >= MIN_MATCH_LINES]
            if not matches:
                continue

            # Apply replacements back-to-front so earlier indices stay valid.
            for m in sorted(matches, key=lambda m: m.b, reverse=True):
                span = working[m.b : m.b + m.size]
                span_text = "\n".join(span)
                if len(span_text) < MIN_MATCH_CHARS:
                    continue
                preview = span[0].strip()[:60]
                pointer = (
                    f"[... {m.size} lines identical to message {earlier_idx + 1}, "
                    f"starting: {preview!r} ...]"
                )
                working[m.b : m.b + m.size] = [pointer]

        out.append("\n".join(working))

    return out
