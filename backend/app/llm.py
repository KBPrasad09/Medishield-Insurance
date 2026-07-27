"""
Central Anthropic client factory.

All agents get their client from here so we can add cross-cutting concerns in one
place. Right now that's optional LangSmith tracing: when LANGSMITH_TRACING is
enabled in the environment, every Claude call (classifier, KYC, claims, policy,
fraud) is automatically traced — token counts, latency, inputs/outputs — with no
change to agent code. Falls back silently to a plain client if LangSmith isn't
installed or configured.
"""

from __future__ import annotations

import os

import anthropic

from .config import require_api_key

_TRACE = os.getenv("LANGSMITH_TRACING", "").lower() in ("1", "true", "yes")


def system_block(text: str) -> list[dict]:
    """Wrap a system prompt as a cacheable block.

    With prompt caching, the (identical) system prompt across many document
    calls is billed at ~10% on cache hits instead of full price. The cache is
    written once and reused for ~5 minutes, so a batch run (or the eval) reuses
    it across every call. No-op if the prefix is below the model's minimum
    cacheable size — the request still succeeds.
    """
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


def cached_tool(tool: dict) -> dict:
    """Mark a tool definition as cacheable (same static schema every call)."""
    return {**tool, "cache_control": {"type": "ephemeral"}}


def get_client() -> anthropic.Anthropic:
    # max_retries handles transient 429/500/529 (overloaded) with backoff.
    client = anthropic.Anthropic(api_key=require_api_key(), max_retries=6)
    if _TRACE:
        try:
            from langsmith.wrappers import wrap_anthropic

            return wrap_anthropic(client)
        except Exception as exc:  # noqa: BLE001 - tracing is best-effort
            print(f"[llm] LangSmith tracing unavailable ({exc}); using plain client.")
    return client
