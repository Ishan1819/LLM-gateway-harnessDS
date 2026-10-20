from app.services.compression.collapse import (
    collapse,
    collapse_repeated_blocks,
    collapse_repeated_lines,
)


def test_empty_string_unchanged():
    assert collapse("") == ""


def test_no_repeats_unchanged():
    text = "line one\nline two\nline three"
    assert collapse_repeated_lines(text) == text
    assert collapse_repeated_blocks(text) == text


def test_repeated_single_line_collapsed():
    text = "\n".join(["same line"] * 5)
    out = collapse_repeated_lines(text)
    assert out.count("same line") == 1
    assert "repeated 4 more times" in out


def test_repeated_single_line_singular_wording():
    text = "\n".join(["x"] * 2)
    out = collapse_repeated_lines(text)
    assert "repeated 1 more time" in out
    assert "1 more times" not in out


def test_repeated_block_replaced_with_pointer():
    block = ["alpha", "beta", "gamma", "delta"]
    text = "\n".join(block + ["unrelated"] + block)
    out = collapse_repeated_blocks(text)
    # first occurrence preserved verbatim, second replaced
    assert out.count("alpha") == 1
    assert "repeats 4 lines" in out


def test_short_block_below_min_not_collapsed():
    # MIN_BLOCK_LINES is 3; a 2-line repeat should not trigger block collapse
    block = ["a", "b"]
    text = "\n".join(block + ["x"] + block)
    out = collapse_repeated_blocks(text)
    assert "repeats" not in out


def test_combined_collapse_reduces_length():
    noisy = "\n".join(["Waiting for pods to become ready (0/3)..."] * 15
                       + ["Waiting for pods to become ready (3/3)..."] * 3
                       + ["Deployment ready."])
    out = collapse(noisy)
    assert len(out) < len(noisy)
    assert "Deployment ready." in out


def test_collapse_never_raises_on_single_line():
    assert collapse("just one line") == "just one line"
