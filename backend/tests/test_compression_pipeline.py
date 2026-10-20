from app.services.compression import (
    LOG_SCORING_LINE_THRESHOLD,
    CompressionResult,
    compress_conversation,
    compress_text,
)


def test_compression_result_math_is_consistent():
    result = CompressionResult(
        original_text="x",
        compressed_text="y",
        original_tokens=1000,
        compressed_tokens=250,
    )
    assert result.tokens_saved == 750
    assert result.reduction_pct == 75.0


def test_reduction_pct_zero_tokens_no_divide_by_zero():
    result = CompressionResult(
        original_text="",
        compressed_text="",
        original_tokens=0,
        compressed_tokens=0,
    )
    assert result.reduction_pct == 0.0


def test_single_short_message_roundtrips_unchanged():
    result = compress_text("What's the capital of France?")
    assert result.compressed_text == result.original_text
    assert result.tokens_saved == 0


def test_compressed_never_exceeds_original_on_repetitive_input():
    blocks = [
        "Tool output:\n" + "\n".join([f"same status line {n % 3}" for n in range(100)]),
        "Tool output:\n" + "\n".join([f"same status line {n % 3}" for n in range(100)]),
    ]
    result = compress_conversation(blocks)
    assert result.compressed_tokens <= result.original_tokens
    assert result.tokens_saved > 0


def test_demo_transcript_hits_meaningful_reduction():
    # end-to-end sanity check mirroring scripts/compression_demo.py
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.compression_demo import build_transcript

    blocks = build_transcript()
    result = compress_conversation(blocks)
    assert result.original_tokens > 0
    assert result.compressed_tokens < result.original_tokens
    assert result.reduction_pct > 50.0  # measured ~85% at time of writing


def test_long_unique_nonlog_text_is_not_destructively_truncated():
    """Guards against the log-scoring technique firing on ordinary long-form
    conversation text (>40 lines) that has no repetition and no log-like
    signal words. It should not be treated as noisy log output and silently
    lose most of its content -- only genuinely low-signal/log-shaped text
    should be aggressively truncated.

    Note: lines must vary in more than just a trailing number, since digit
    stripping is part of the log-likeness/normalization check -- a template
    like "sentence {i}" would itself look log-like once digits are removed.
    """
    subjects = [
        "The engineering team", "Our data pipeline", "The billing subsystem",
        "Customer support", "The onboarding flow", "The search ranking model",
        "Payment reconciliation", "The mobile app", "The analytics dashboard",
        "The deployment pipeline",
    ]
    actions = [
        "needs a review of", "recently changed", "will migrate away from",
        "documented an issue with", "proposed an alternative to", "benchmarked",
    ]
    objects = [
        "the caching layer", "the authentication flow", "the retry policy",
        "the rate limiter", "the notification service", "the schema migration process",
        "the onboarding survey", "the fraud detection heuristics",
    ]
    paragraph_sentences = [
        f"{subjects[i % len(subjects)]} {actions[(i * 3 + 1) % len(actions)]} "
        f"{objects[(i * 5 + 2) % len(objects)]} this quarter."
        for i in range(60)
    ]
    text = "\n".join(paragraph_sentences)
    result = compress_text(text)
    # Losing more than half of a genuinely unique, non-log conversation is a
    # correctness problem for a "compression that preserves meaning" demo.
    assert result.reduction_pct < 50.0


def test_collapse_markers_never_trigger_a_destructive_second_pass():
    """Regression test for a real bug found in manual testing: a business
    narrative with genuine repeated sentences (which `collapse()` correctly
    deduplicates into pointer markers like "... (repeats 3 lines...)")  was
    then getting run through `compress_log()` a second time. Those pointer
    markers are themselves near-identical to each other, which fooled the
    log-likeness heuristic into thinking the (already-deduplicated) text was
    still noisy log output, and it discarded everything except the first and
    last line -- including all 5 distinct customer IDs/dates and every
    substantive sentence needed to actually answer the question asked.
    """
    text = (
        "Customer support investigation for Q2 churn.\n\n"
        + "\n\n".join(
            f"Tool output:\nCustomer ID: {1001 + i}\nPlan: Premium\nRegion: India\n"
            f"Status: Active\nLast Login: 2026-08-{10 - i:02d}\nReason: Price"
            for i in range(5)
        )
        + "\n\n"
        + "\n\n".join(
            ["The customer support team reported that many customers complained about pricing."]
            + ["Customer support team reported that many customers complained about pricing."] * 4
        )
        + "\n\n"
        + "\n\n".join(
            [
                "Previous analysis:\nQ2 churn increased by 18%.\n"
                "The main complaints were pricing, lack of features, and slow support."
            ]
            * 5
        )
        + "\n\nAdditional investigation:\n"
        + "\n".join(["The support team reviewed 500 customer conversations."] * 5)
        + "\n\nAnalyze the available information and determine the most likely reasons for customer churn."
    )

    result = compress_text(text)

    # The real, load-bearing facts must survive: every distinct customer ID,
    # the churn figure, and the actual question being asked.
    for customer_id in range(1001, 1006):
        assert str(customer_id) in result.compressed_text
    assert "18%" in result.compressed_text
    assert "pricing" in result.compressed_text
    assert "Analyze the available information" in result.compressed_text
    # Losing almost everything (as the bug did) is worse than barely
    # compressing -- correctness comes before a big percentage.
    assert result.reduction_pct < 50.0


def test_realistically_sized_log_excerpt_still_gets_compressed():
    """Regression test: a genuinely log-shaped excerpt at a realistic size
    (a ~30-line trace, not a synthetic 200+ line stress test) was falling
    just under the old line-count pre-filter (40), so technique 3 never even
    ran on it despite being exactly what it's designed for.
    """
    lines = [
        f"2026-08-12 10:01:{i:02d} INFO Request received endpoint=/api/search"
        if i % 2 == 0
        else f"2026-08-12 10:01:{i:02d} INFO Request completed status=200 latency={120 + i}ms"
        for i in range(20)
    ]
    text = (
        "Analyze the following production logs and identify the cause of the API latency spike.\n\n"
        + "\n".join(lines)
        + "\n\n2026-08-12 10:01:21 WARN Database connection pool utilization=95%\n"
        "2026-08-12 10:01:22 WARN Database connection pool utilization=97%\n"
        "2026-08-12 10:01:23 WARN Database connection pool utilization=99%\n"
        "2026-08-12 10:01:24 ERROR Database connection timeout\n"
        "2026-08-12 10:01:25 ERROR Request failed status=500\n\n"
        "Determine the most likely cause of the latency and errors."
    )
    assert text.count("\n") + 1 < 40  # smaller than the old (too high) threshold
    assert text.count("\n") + 1 > LOG_SCORING_LINE_THRESHOLD

    result = compress_text(text)
    assert result.reduction_pct > 30.0
    # the actual signal -- that pool utilization was climbing and connections
    # started failing -- must survive (near-duplicate WARN lines are allowed
    # to collapse to one representative occurrence; the ERROR lines must not)
    assert "pool utilization=" in result.compressed_text
    assert "Database connection timeout" in result.compressed_text
    assert "Request failed status=500" in result.compressed_text
