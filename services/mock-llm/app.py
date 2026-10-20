"""Mock LLM provider — stands in for OpenAI and Anthropic during the demo.

No real model is called and nothing is billed. It speaks just enough of both
APIs for the gateway to forward, meter and cost a request:

    POST /v1/chat/completions   OpenAI shape (streaming supported)
    POST /v1/messages           Anthropic shape (streaming supported)
    GET  /health

Every response carries `x-served-by: <pod name>` so the admin dashboard can
show which replica handled a call (load balancing across the Service).

Knobs (env):
    MOCK_LATENCY_MS     base latency per request (default 150, +/- 50%)
    MOCK_FAILURE_RATE   fraction of requests answered with HTTP 503 (default 0)
                        -- used to demonstrate the gateway's retries.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import socket
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

POD_NAME = os.environ.get("POD_NAME") or socket.gethostname()
LATENCY_MS = float(os.environ.get("MOCK_LATENCY_MS", "150"))
FAILURE_RATE = float(os.environ.get("MOCK_FAILURE_RATE", "0"))

app = FastAPI(title="Mock LLM", version="1.0.0")
served = 0


def _text_of(payload: dict) -> str:
    parts: list[str] = []
    system = payload.get("system")
    if isinstance(system, str):
        parts.append(system)
    for message in payload.get("messages", []) or []:
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.extend(b.get("text", "") for b in content if isinstance(b, dict))
    return " ".join(parts)


def _prompt_tokens(payload: dict) -> int:
    # ~4 characters per token, the usual rule of thumb for English.
    return max(1, len(_text_of(payload)) // 4)


def _reply(model: str) -> tuple[str, int]:
    text = (
        f"[mock reply from {POD_NAME}] This is a simulated response for {model}. "
        "No real model was called and no money was spent."
    )
    return text, max(1, len(text) // 4) + random.randint(0, 40)


async def _simulate_work() -> JSONResponse | None:
    global served
    served += 1
    await asyncio.sleep(max(0.0, LATENCY_MS * random.uniform(0.5, 1.5)) / 1000)
    if FAILURE_RATE and random.random() < FAILURE_RATE:
        return JSONResponse(
            status_code=503,
            content={"error": {"message": "mock upstream overloaded", "type": "overloaded"}},
            headers={"x-served-by": POD_NAME},
        )
    return None


def _sse(events: list[dict], done_marker: bool):
    async def gen():
        for event in events:
            yield f"data: {json.dumps(event)}\n\n"
            await asyncio.sleep(0.02)
        if done_marker:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        gen(), media_type="text/event-stream", headers={"x-served-by": POD_NAME}
    )


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    payload = await request.json()
    failure = await _simulate_work()
    if failure:
        return failure

    model = payload.get("model", "unknown-model")
    prompt_tokens = _prompt_tokens(payload)
    text, completion_tokens = _reply(model)
    usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }

    if payload.get("stream"):
        words = text.split(" ")
        events = [{"choices": [{"delta": {"content": w + " "}}]} for w in words]
        events.append({"choices": [], "usage": usage})
        return _sse(events, done_marker=True)

    return JSONResponse(
        {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": usage,
        },
        headers={"x-served-by": POD_NAME},
    )


@app.post("/v1/messages")
async def messages(request: Request):
    payload = await request.json()
    failure = await _simulate_work()
    if failure:
        return failure

    model = payload.get("model", "unknown-model")
    input_tokens = _prompt_tokens(payload)
    text, output_tokens = _reply(model)

    if payload.get("stream"):
        events = [
            {
                "type": "message_start",
                "message": {"model": model, "usage": {"input_tokens": input_tokens, "output_tokens": 1}},
            },
            *(
                {"type": "content_block_delta", "delta": {"type": "text_delta", "text": w + " "}}
                for w in text.split(" ")
            ),
            {"type": "message_delta", "usage": {"output_tokens": output_tokens - 1}},
            {"type": "message_stop"},
        ]
        return _sse(events, done_marker=False)

    return JSONResponse(
        {
            "id": f"msg_{uuid.uuid4().hex[:12]}",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        },
        headers={"x-served-by": POD_NAME},
    )


@app.get("/health")
def health():
    return {"status": "healthy", "pod": POD_NAME, "served": served}
