"""Real token counting for the compression demo, backed by tiktoken.

Uses OpenAI's cl100k_base encoding as a stable, model-agnostic byte-pair
encoding for measuring token counts before/after compression. This mirrors
Headroom's own approach of counting real tokens rather than estimating from
character/word counts.
"""

from __future__ import annotations

import tiktoken

_ENCODING_NAME = "cl100k_base"
_encoding: tiktoken.Encoding | None = None


def _get_encoding() -> tiktoken.Encoding:
    global _encoding
    if _encoding is None:
        _encoding = tiktoken.get_encoding(_ENCODING_NAME)
    return _encoding


def count_tokens(text: str) -> int:
    """Return the exact tiktoken token count for `text`."""
    if not text:
        return 0
    return len(_get_encoding().encode(text))
