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


def get_client() -> anthropic.Anthropic:
    client = anthropic.Anthropic(api_key=require_api_key())
    if _TRACE:
        try:
            from langsmith.wrappers import wrap_anthropic

            return wrap_anthropic(client)
        except Exception as exc:  # noqa: BLE001 - tracing is best-effort
            print(f"[llm] LangSmith tracing unavailable ({exc}); using plain client.")
    return client
