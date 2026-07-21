"""
Shared vision-LLM plumbing for all specialist agents.

Every agent uses the same pattern: send a document image, force a single
tool_use call whose input schema IS the agent's extraction contract, and return
the parsed arguments. Centralizing it here means the classifier, KYC, and claims
agents can't drift apart on encoding, model, or parsing.
"""

from __future__ import annotations

import base64
from pathlib import Path

import anthropic

from ..config import CLASSIFIER_MODEL, require_api_key

_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".pdf": "application/pdf",
}


def encode(path: Path) -> tuple[str, str]:
    media_type = _MEDIA_TYPES.get(path.suffix.lower())
    if media_type is None:
        raise ValueError(f"Unsupported file type: {path.suffix}")
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return media_type, data


def _content_block(media_type: str, data: str) -> dict:
    kind = "document" if media_type == "application/pdf" else "image"
    return {
        "type": kind,
        "source": {"type": "base64", "media_type": media_type, "data": data},
    }


def extract(
    image_path: str,
    system_prompt: str,
    tool: dict,
    user_text: str = "Extract the requested fields from this document.",
    client: anthropic.Anthropic | None = None,
    max_tokens: int = 1024,
) -> dict:
    """Run one forced-tool vision call and return the tool_use input dict."""
    path = Path(image_path)
    media_type, data = encode(path)
    client = client or anthropic.Anthropic(api_key=require_api_key())

    response = client.messages.create(
        model=CLASSIFIER_MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[
            {
                "role": "user",
                "content": [
                    _content_block(media_type, data),
                    {"type": "text", "text": user_text},
                ],
            }
        ],
    )
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            return block.input
    raise ValueError(f"Model did not return a tool_use block for {tool['name']}.")
