"""
Classifier Agent — the first stage of the pipeline.

Looks at a document image with a vision-capable Claude model and returns a
typed ClassifierOutput: which of the six document types it is, how confident
the model is, and routing tags the orchestrator uses to fan out to specialists.

Reliability choices (worth explaining in the demo):
  - We use Anthropic *tool use* to force structured output. Instead of asking
    for JSON in prose and hoping it parses, we define a `record_classification`
    tool whose input schema IS our contract, and set tool_choice to require it.
    The model must return arguments matching the schema, so parsing can't drift.
  - doc_type is constrained to the six-value enum at the schema level, so the
    model literally cannot invent a new category.
  - Deterministic-ish: temperature 0 for stable, reproducible classifications
    across eval runs.
"""

from __future__ import annotations

import base64
from pathlib import Path

import anthropic

from ..config import CLASSIFIER_MODEL, require_api_key
from ..schemas import ClassifierOutput, DocType

_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".pdf": "application/pdf",
}

_SYSTEM_PROMPT = """You are the Classifier Agent in MediShield's insurance \
document intake pipeline. You are shown a single scanned document image. \
Identify which ONE of these types it is:

- CLAIM_FORM: insurance claim forms (e.g. CMS-1500, UB-04) with billing codes, \
amounts, provider info.
- ID_DOCUMENT: government identity documents — driver's license, passport, state ID.
- DISCHARGE_SUMMARY: hospital discharge summaries with admission/discharge dates, \
diagnoses, treatment narrative.
- PRESCRIPTION: prescription / Rx documents listing medications, dosage, prescriber.
- POLICY_AMENDMENT: policy change/amendment request forms (typed or handwritten).
- UNKNOWN: anything that does not clearly fit the above (bank statements, utility \
bills, blank scans, unrelated paperwork).

Judge only from what is visible. If the document is blurry, blank, ambiguous, or \
out-of-domain, classify as UNKNOWN and give a low confidence. Report confidence \
as your true calibrated certainty from 0.0 to 1.0."""

# Tool schema = our output contract. The model must fill exactly these fields.
_CLASSIFY_TOOL = {
    "name": "record_classification",
    "description": "Record the document classification result.",
    "input_schema": {
        "type": "object",
        "properties": {
            "doc_type": {
                "type": "string",
                "enum": [t.value for t in DocType],
                "description": "The single best-fitting document type.",
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Calibrated certainty in the classification.",
            },
            "routing_tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Short tags describing salient content "
                "(e.g. 'cms1500', 'handwritten', 'expired_looking').",
            },
            "notes": {
                "type": "string",
                "description": "One short sentence of visual justification.",
            },
        },
        "required": ["doc_type", "confidence"],
    },
}


def _encode(path: Path) -> tuple[str, str]:
    media_type = _MEDIA_TYPES.get(path.suffix.lower())
    if media_type is None:
        raise ValueError(f"Unsupported file type for classification: {path.suffix}")
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return media_type, data


def _content_block(media_type: str, data: str) -> dict:
    # PDFs go in a 'document' block; images in an 'image' block.
    kind = "document" if media_type == "application/pdf" else "image"
    return {
        "type": kind,
        "source": {"type": "base64", "media_type": media_type, "data": data},
    }


def classify_document(image_path: str, client: anthropic.Anthropic | None = None) -> ClassifierOutput:
    """Classify one document image. `client` is injectable for testing."""
    path = Path(image_path)
    media_type, data = _encode(path)

    client = client or anthropic.Anthropic(api_key=require_api_key())

    response = client.messages.create(
        model=CLASSIFIER_MODEL,
        max_tokens=512,
        temperature=0,
        system=_SYSTEM_PROMPT,
        tools=[_CLASSIFY_TOOL],
        tool_choice={"type": "tool", "name": "record_classification"},
        messages=[
            {
                "role": "user",
                "content": [
                    _content_block(media_type, data),
                    {"type": "text", "text": "Classify this document."},
                ],
            }
        ],
    )

    tool_input = _extract_tool_input(response)
    return ClassifierOutput(
        doc_type=DocType(tool_input["doc_type"]),
        confidence=float(tool_input.get("confidence", 0.0)),
        routing_tags=tool_input.get("routing_tags", []) or [],
        notes=tool_input.get("notes"),
    )


def _extract_tool_input(response) -> dict:
    """Pull the tool_use block's input out of the Messages response."""
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            return block.input
    raise ValueError("Model did not return a tool_use block for classification.")
