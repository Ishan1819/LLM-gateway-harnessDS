from app.services.complexity_scorer import analyze_complexity


def test_trivial_lookup_is_tier_1():
    result = analyze_complexity("What is the capital of France?", context_tokens=50)
    assert result.tier == 1
    assert result.has_code is False
    assert result.reasoning_required is False


def test_summarize_short_text_is_tier_1():
    result = analyze_complexity("Summarize this paragraph in one sentence.", context_tokens=300)
    assert result.tier == 1


def test_code_debugging_request_is_higher_tier():
    text = (
        "Here's my Python function:\n```python\ndef process(items):\n    return [x for x in items]\n```\n"
        "Can you debug why this raises a KeyError and optimize it?"
    )
    result = analyze_complexity(text, context_tokens=800)
    assert result.has_code is True
    assert result.reasoning_required is True
    assert result.tier >= 2


def test_large_context_plus_code_plus_reasoning_is_tier_3():
    text = (
        "```python\ndef process(items):\n    return [x for x in items]\n```\n"
        "Analyze the root cause of this outage, debug the function above, and "
        "design a trade-off comparison of mitigation strategies."
    )
    result = analyze_complexity(text, context_tokens=20_000)
    assert result.tier == 3


def test_large_context_alone_is_not_automatically_tier_3():
    # Size alone (no code/reasoning/structured-output signal) shouldn't force
    # the most expensive tier -- that would defeat "cheapest capable model".
    result = analyze_complexity("Please just repeat the last sentence back to me.", context_tokens=20_000)
    assert result.tier < 3


def test_structured_output_request_bumps_tier():
    plain = analyze_complexity("Tell me about your day.", context_tokens=100)
    structured = analyze_complexity(
        "Return the result as structured JSON matching this schema.", context_tokens=100
    )
    assert structured.score > plain.score


def test_score_is_clamped_between_0_and_100():
    text = (
        "```code``` debug optimize architect design a analyze root cause step by step "
        "prove derive trade-offs json schema structured output"
    )
    result = analyze_complexity(text, context_tokens=50_000)
    assert 0.0 <= result.score <= 100.0


def test_context_size_increases_score_monotonically():
    small = analyze_complexity("hello", context_tokens=500)
    medium = analyze_complexity("hello", context_tokens=5_000)
    large = analyze_complexity("hello", context_tokens=20_000)
    assert small.score <= medium.score <= large.score


def test_reasons_explain_the_score():
    text = "Please debug and optimize this function step by step."
    result = analyze_complexity(text, context_tokens=100)
    assert len(result.reasons) > 0
    assert isinstance(result.reasons[0], str)


def test_reasoning_only_signal_under_1000_tokens_reaches_tier_2():
    """Regression test: a single strong signal (reasoning language) on a
    small/medium context was stuck at tier 1 forever, because the tier-2
    threshold (30) was higher than what any one signal alone could produce
    (reasoning = 25). This meant real analytical tasks -- e.g. diagnosing a
    production incident from logs -- always routed to the cheapest model
    regardless of how much reasoning they actually required.
    """
    text = (
        "Analyze the following production logs and identify the cause of the "
        "API latency spike. Determine the most likely cause of the errors."
    )
    result = analyze_complexity(text, context_tokens=133)
    assert result.reasoning_required is True
    assert result.tier == 2


def test_deterministic_same_input_same_output():
    text = "Design a caching strategy and explain the trade-offs."
    a = analyze_complexity(text, context_tokens=2000)
    b = analyze_complexity(text, context_tokens=2000)
    assert a.score == b.score
    assert a.tier == b.tier
