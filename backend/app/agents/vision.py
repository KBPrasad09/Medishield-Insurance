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

from ..config import CLASSIFIER_MODEL
from ..llm import get_client

_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".pdf": "application/pdf",
}


# Anthropic's vision guidance: long edge <= 1568px and payload well under the
# 10 MB hard limit. We downscale/recompress images to satisfy both.
_MAX_EDGE = 1568
_MAX_BYTES = 4_500_000


def encode(path: Path) -> tuple[str, str]:
    media_type = _MEDIA_TYPES.get(path.suffix.lower())
    if media_type is None:
        raise ValueError(f"Unsupported file type: {path.suffix}")

    # PDFs pass through untouched.
    if media_type == "application/pdf":
        data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
        return media_type, data

    # Images: downscale the long edge and recompress until safely small.
    from io import BytesIO

    from PIL import Image

    img = Image.open(path).convert("RGB")
    if max(img.size) > _MAX_EDGE:
        ratio = _MAX_EDGE / max(img.size)
        img = img.resize((round(img.width * ratio), round(img.height * ratio)))

    quality = 90
    while True:
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        raw = buf.getvalue()
        if len(raw) <= _MAX_BYTES or quality <= 40:
            break
        quality -= 15
    data = base64.standard_b64encode(raw).decode("utf-8")
    return "image/jpeg", data


def as_str_list(v) -> list[str]:
    """Coerce a model-returned value into a clean list of strings.

    Vision models occasionally return an array field as a comma-separated string
    ('a, b, c') instead of a JSON list. Normalize both forms so downstream
    parsing and Pydantic validation never break mid-run.
    """
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        return [s.strip() for s in v.split(",") if s.strip()]
    return []


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
    client = client or get_client()

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
