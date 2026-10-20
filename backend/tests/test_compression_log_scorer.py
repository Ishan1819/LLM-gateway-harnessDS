from app.services.compression.log_scorer import _is_log_like, compress_log
from app.services.compression.tokenizer import count_tokens


def test_short_text_below_min_keep_unchanged():
    text = "\n".join(f"line {i}" for i in range(5))
    assert compress_log(text) == text


def test_errors_always_retained():
    lines = [f"INFO routine status update number {i}" for i in range(100)]
    lines[50] = "ERROR database connection lost, retrying"
    text = "\n".join(lines)
    out = compress_log(text)
    assert "ERROR database connection lost" in out
    assert count_tokens(out) < count_tokens(text)


def test_first_and_last_line_always_kept():
    lines = [f"INFO noise line {i}" for i in range(100)]
    lines[0] = "START marker unique first line"
    lines[-1] = "END marker unique last line"
    text = "\n".join(lines)
    out = compress_log(text)
    assert out.splitlines()[0] == "START marker unique first line"
    assert out.splitlines()[-1] == "END marker unique last line"


def test_summary_line_retained():
    lines = [f"INFO check {i} passed" for i in range(80)]
    lines.append("=== 80 passed, 0 failed ===")
    text = "\n".join(lines)
    out = compress_log(text)
    assert "=== 80 passed, 0 failed ===" in out


def test_near_duplicate_warnings_deduped_but_not_all_dropped():
    lines = [f"WARN slow response {i}ms exceeds threshold" for i in range(60)]
    text = "\n".join(lines)
    out = compress_log(text)
    # normalization collapses near-identical warnings (only digits differ),
    # so far fewer than 60 WARN lines should survive
    assert out.count("WARN") < 60
    assert out.count("WARN") >= 1


def test_omitted_marker_present_when_lines_dropped():
    lines = [f"INFO heartbeat {i}" for i in range(200)]
    text = "\n".join(lines)
    out = compress_log(text)
    assert "omitted" in out
    assert count_tokens(out) < count_tokens(text)


def test_output_never_longer_in_lines_than_input():
    lines = [f"INFO event {i} occurred normally" for i in range(150)]
    text = "\n".join(lines)
    out = compress_log(text)
    # kept lines + omission markers should still be far fewer lines than original
    assert len(out.splitlines()) < len(lines)


def test_collapse_pointer_markers_excluded_from_log_likeness_check():
    """Regression test: collapse.py's own "... (repeats N lines...)" pointer
    markers are near-identical to each other and must not make already-
    deduplicated, genuinely-unique business content look log-like -- that
    was causing a second, destructive compression pass (see
    test_compression_pipeline.py::test_collapse_markers_never_trigger_a_destructive_second_pass).
    """
    unique_content_lines = [
        "Customer ID: 1001, region India, reason: price",
        "Customer ID: 1002, region India, reason: price",
        "Customer ID: 1003, region India, reason: price",
        "Q2 churn increased by 18% due to pricing complaints",
        "The support team reviewed 500 customer conversations",
    ]
    marker_lines = [
        "... (repeats 3 lines identical to lines 5-7)",
        "... (repeats 4 lines identical to lines 12-15)",
        "... (repeats 8 lines identical to lines 20-27)",
        "... (previous line repeated 4 more times)",
    ]
    # With markers included, non-log content should still not be judged log-like.
    assert _is_log_like(unique_content_lines + marker_lines) is False
    # And the markers alone (all near-identical after normalization) would be
    # judged log-like if not excluded -- confirming the exclusion is load-bearing.
    assert _is_log_like(marker_lines * 5) is False  # excluded -> no non-empty lines left
