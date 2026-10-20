from app.services.governance_service import extract_message_blocks, run_governance


def test_extract_blocks_from_openai_style_payload():
    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What's the weather like?"},
        ],
    }
    blocks = extract_message_blocks(payload)
    assert blocks == ["You are a helpful assistant.", "What's the weather like?"]


def test_extract_blocks_from_anthropic_style_payload():
    payload = {
        "model": "claude-sonnet-5",
        "system": "You are concise.",
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "Summarize this doc."}]},
        ],
    }
    blocks = extract_message_blocks(payload)
    assert blocks == ["You are concise.", "Summarize this doc."]


def test_extract_blocks_handles_tool_result_content():
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "content": [{"text": "raw tool output here"}]},
                ],
            }
        ]
    }
    blocks = extract_message_blocks(payload)
    assert blocks == ["raw tool output here"]


def test_extract_blocks_empty_payload_returns_empty_list():
    assert extract_message_blocks({}) == []


def test_run_governance_end_to_end_simple_request():
    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "user", "content": "What is 2 + 2?"},
        ],
    }
    result = run_governance(payload, requested_model="gpt-4o")

    assert result.compression.original_tokens > 0
    assert result.complexity.tier == 1  # trivial question
    assert result.routing.required_tier == 1
    assert result.cost.original_model == "gpt-4o"
    assert result.cost.selected_model == result.routing.recommended_model
    # requested a frontier model for a trivial question -> should recommend
    # a cheaper model and show real routing savings
    assert result.cost.selected_model != "gpt-4o"
    assert result.cost.total_savings_usd > 0


def test_run_governance_repetitive_context_shows_compression_savings():
    noisy_context = "\n".join(f"log line {i % 3}: status ok, latency=12ms" for i in range(300))
    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "user", "content": f"Given this log dump:\n{noisy_context}\nAny issues?"},
        ],
    }
    result = run_governance(payload, requested_model="gpt-4o")
    assert result.compression.tokens_saved > 0
    assert result.cost.compression_savings_usd > 0


def test_run_governance_as_dict_is_json_serializable():
    import json

    payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}
    result = run_governance(payload, requested_model="gpt-4o-mini")
    json.dumps(result.as_dict())  # must not raise
