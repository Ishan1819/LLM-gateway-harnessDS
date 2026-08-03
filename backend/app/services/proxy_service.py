"""Upstream forwarding to OpenAI / Anthropic using the client's own API keys.

The proxy is deliberately transparent: request bodies are passed through
untouched, so a developer only has to change `base_url` in their SDK setup.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from app.config import settings
from app.models import Organization
from app.services.encryption_service import decrypt
from app.utils.pricing import detect_provider


class UpstreamKeyMissing(Exception):
    """The org hasn't configured a key for the provider this model belongs to."""


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=settings.UPSTREAM_TIMEOUT_SECONDS)


def resolve_api_key(org: Organization, provider: str) -> str:
    encrypted = (
        org.anthropic_api_key_encrypted
        if provider == "anthropic"
        else org.openai_api_key_encrypted
    )
    if not encrypted:
        raise UpstreamKeyMissing(
            f"No {provider} API key configured for this organization. "
            "An admin can add one under Settings."
        )
    return decrypt(encrypted)


def build_target(provider: str, path: str, api_key: str) -> tuple[str, dict[str, str]]:
    if provider == "anthropic":
        url = f"{settings.ANTHROPIC_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": settings.ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
    else:
        url = f"{settings.OPENAI_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
        headers = {
            "authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        }
    return url, headers


def passthrough_headers(incoming: dict[str, str], provider: str) -> dict[str, str]:
    """Forward provider-specific opt-ins (beta flags, org/project scoping)."""
    allowed_prefixes = ("anthropic-beta", "openai-organization", "openai-project", "openai-beta")
    return {
        k.lower(): v
        for k, v in incoming.items()
        if k.lower().startswith(allowed_prefixes)
    }


def extract_usage(provider: str, body: dict) -> Usage:
    usage = body.get("usage") or {}
    if provider == "anthropic":
        # Cache tokens are billed as input; count them so cost isn't understated.
        prompt = (
            int(usage.get("input_tokens", 0))
            + int(usage.get("cache_creation_input_tokens", 0) or 0)
            + int(usage.get("cache_read_input_tokens", 0) or 0)
        )
        return Usage(prompt, int(usage.get("output_tokens", 0)))
    return Usage(
        int(usage.get("prompt_tokens", 0)),
        int(usage.get("completion_tokens", 0)),
    )


def merge_stream_usage(provider: str, event: dict, usage: Usage) -> Usage:
    """Accumulate usage from a single SSE event so streamed calls still get billed."""
    if provider == "anthropic":
        if event.get("type") == "message_start":
            u = (event.get("message") or {}).get("usage") or {}
            usage.prompt_tokens += (
                int(u.get("input_tokens", 0))
                + int(u.get("cache_creation_input_tokens", 0) or 0)
                + int(u.get("cache_read_input_tokens", 0) or 0)
            )
            usage.completion_tokens += int(u.get("output_tokens", 0) or 0)
        elif event.get("type") == "message_delta":
            u = event.get("usage") or {}
            usage.completion_tokens += int(u.get("output_tokens", 0) or 0)
    else:
        # OpenAI only emits usage when stream_options.include_usage is set.
        u = event.get("usage")
        if u:
            usage.prompt_tokens = int(u.get("prompt_tokens", usage.prompt_tokens))
            usage.completion_tokens = int(u.get("completion_tokens", usage.completion_tokens))
    return usage


def prompt_preview(payload: dict) -> str:
    """First 100 characters of the prompt — never the whole thing."""
    parts: list[str] = []

    system = payload.get("system")
    if isinstance(system, str):
        parts.append(system)
    elif isinstance(system, list):
        parts.extend(b.get("text", "") for b in system if isinstance(b, dict))

    for message in payload.get("messages", []) or []:
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.extend(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )

    return " ".join(p for p in parts if p).strip()[:100]


async def forward(
    *,
    provider: str,
    path: str,
    payload: dict,
    api_key: str,
    extra_headers: dict[str, str],
) -> tuple[int, dict, Usage]:
    """Non-streaming forward. Returns (status, body, usage)."""
    url, headers = build_target(provider, path, api_key)
    headers.update(extra_headers)

    async with _client() as client:
        response = await client.post(url, json=payload, headers=headers)

    try:
        body = response.json()
    except json.JSONDecodeError:
        body = {"error": {"message": response.text, "type": "upstream_error"}}

    usage = extract_usage(provider, body) if response.is_success else Usage()
    return response.status_code, body, usage


def stream_forward(
    *,
    provider: str,
    path: str,
    payload: dict,
    api_key: str,
    extra_headers: dict[str, str],
):
    """Streaming forward.

    Returns an async context manager yielding (response, line_iterator). The
    caller tees the lines to the client while accumulating usage, then records
    it once the stream closes.
    """
    url, headers = build_target(provider, path, api_key)
    headers.update(extra_headers)
    client = _client()
    return client, client.stream("POST", url, json=payload, headers=headers)


__all__ = [
    "Usage",
    "UpstreamKeyMissing",
    "detect_provider",
    "resolve_api_key",
    "passthrough_headers",
    "extract_usage",
    "merge_stream_usage",
    "prompt_preview",
    "forward",
    "stream_forward",
]
