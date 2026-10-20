from app.services.compression.dedup import dedup_turns
from app.services.compression.tokenizer import count_tokens


def test_single_block_unchanged():
    blocks = ["only one message here, nothing to dedup against"]
    assert dedup_turns(blocks) == blocks


def test_no_overlap_unchanged():
    blocks = [
        "The quick brown fox jumps over the lazy dog near the river bank.",
        "Completely different content about databases and indexing strategies.",
    ]
    out = dedup_turns(blocks)
    assert out == blocks


def test_exact_repeat_block_replaced_with_pointer():
    shared = "\n".join(f"data row {i}: value={i * 7}" for i in range(20))
    blocks = [f"Tool output:\n{shared}", f"Follow-up tool output:\n{shared}"]
    out = dedup_turns(blocks)
    assert out[0] == blocks[0]  # first occurrence untouched
    assert "identical to message 1" in out[1]
    assert "data row 5" not in out[1]  # the repeated span got pointerized


def test_dedup_actually_reduces_tokens():
    shared = "\n".join(f"log line {i} with some realistic content here" for i in range(30))
    blocks = [f"first fetch:\n{shared}", f"second fetch:\n{shared}"]
    out = dedup_turns(blocks)
    original_tokens = count_tokens("\n\n".join(blocks))
    deduped_tokens = count_tokens("\n\n".join(out))
    assert deduped_tokens < original_tokens


def test_short_matches_below_char_threshold_not_pointerized():
    # 3 short lines that together are under MIN_MATCH_CHARS should be left alone
    blocks = ["a\nb\nc", "a\nb\nc"]
    out = dedup_turns(blocks)
    assert "identical to message" not in out[1]


def test_partial_overlap_only_replaces_matching_span():
    shared = "\n".join(f"shared context line number {i} with enough length" for i in range(10))
    blocks = [
        f"intro\n{shared}\noutro",
        f"different intro\n{shared}\ndifferent outro",
    ]
    out = dedup_turns(blocks)
    assert "different intro" in out[1]
    assert "different outro" in out[1]
    assert "identical to message 1" in out[1]
