"""
Policy Agent (RAG) — decides whether a claim's procedures are covered.

Flow:
  1. Build a coverage query from the claim's CPT codes (+ diagnosis context).
  2. Retrieve the most relevant clauses from the member's plan policy via the
     vector store (policy_rag.retrieve).
  3. Ask the LLM to decide coverage grounded ONLY in the retrieved clauses, and
     return a typed PolicyOutput. Grounding in retrieved text (not the model's
     prior knowledge) is what makes this real RAG and keeps the answer auditable.
"""

from __future__ import annotations

import anthropic

from .. import policy_rag
from ..config import CLASSIFIER_MODEL
from ..llm import cached_tool, get_client, system_block
from ..schemas import PolicyOutput
from .vision import as_str_list

_SYSTEM_PROMPT = """You are the Policy Agent for MediShield health insurance. \
You decide whether the procedures on a claim are covered under the member's plan.

You are given: (a) the CPT procedure codes on the claim, and (b) excerpts \
retrieved from the member's policy document. Decide coverage using ONLY the \
provided policy excerpts — do not rely on outside knowledge. If an excerpt lists \
a CPT code or range as excluded (e.g. an 'Excluded CPT Code Ranges' table), any \
claim code falling in that range is NOT covered. Cite the specific clause you \
relied on."""

_TOOL = {
    "name": "record_coverage_decision",
    "description": "Record the coverage decision for the claim's procedures.",
    "input_schema": {
        "type": "object",
        "properties": {
            "covered": {
                "type": "boolean",
                "description": "True only if none of the CPT codes are excluded.",
            },
            "coverage_percentage": {
                "type": "number",
                "description": "Plan coverage share for covered services, 0-100.",
            },
            "policy_clause": {
                "type": "string",
                "description": "The specific clause/section relied upon.",
            },
            "exclusions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "CPT codes or services found to be excluded, with reason.",
            },
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "required": ["covered", "confidence"],
    },
}


def run_policy(
    cpt_codes: list[str],
    plan_tier: str,
    diagnosis: str | None = None,
    client: anthropic.Anthropic | None = None,
) -> PolicyOutput:
    query = "Coverage and exclusions for procedure CPT codes: " + ", ".join(cpt_codes)
    if diagnosis:
        query += f". Primary diagnosis: {diagnosis}."

    clauses = policy_rag.retrieve(query, plan_tier, k=4)
    context = "\n\n---\n\n".join(
        f"[{c['section']}]\n{c['text']}" for c in clauses
    ) or "(no policy excerpts retrieved)"

    user_text = (
        f"Member plan: {plan_tier}\n"
        f"Claim CPT codes: {', '.join(cpt_codes) or '(none)'}\n"
        f"Diagnosis: {diagnosis or '(unknown)'}\n\n"
        f"Retrieved policy excerpts:\n{context}\n\n"
        "Decide coverage for these procedures."
    )

    client = client or get_client()
    response = client.messages.create(
        model=CLASSIFIER_MODEL,
        max_tokens=1024,
        system=system_block(_SYSTEM_PROMPT),
        tools=[cached_tool(_TOOL)],
        tool_choice={"type": "tool", "name": _TOOL["name"]},
        messages=[{"role": "user", "content": user_text}],
    )

    data = _tool_input(response)
    return PolicyOutput(
        covered=bool(data.get("covered", False)),
        coverage_percentage=data.get("coverage_percentage"),
        policy_clause=data.get("policy_clause"),
        exclusions=as_str_list(data.get("exclusions")),
        confidence=float(data.get("confidence", 0.0)),
        notes=f"Retrieved {len(clauses)} clause(s) for {plan_tier} plan.",
    )


def _tool_input(response) -> dict:
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            return block.input
    raise ValueError("Policy agent: no tool_use block returned.")
