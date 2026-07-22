"""
Fraud Detection Agent — operates on a whole case (all documents together).

The six fraud patterns in the dataset split into two kinds:

  Computable from structured extractions (deterministic rules — precise, no LLM):
    - amount_under_10k  : claim total just below the $10,000 review threshold
    - proc_diag_mismatch: maternity CPT 59400 billed on a non-maternity diagnosis
    - duplicate_claim   : the same case carries two claim forms
    - name_mismatch     : the ID's name isn't the policyholder (KYC couldn't match)

  Requiring cross-document temporal reasoning (LLM pass over the images):
    - readmission_30d   : discharge shows a prior admission < 30 days earlier
    - date_conflict     : prescription dated 45+ days after the service date

We run the rules first, then an LLM anomaly pass over the case's discharge and
prescription images. The final fraud_score is the max of rule and LLM signals,
and every fired signal is listed in `anomalies` so the decision is explainable.
"""

from __future__ import annotations

import json

import anthropic

from ..config import CLASSIFIER_MODEL, require_api_key
from ..schemas import Case, DocType, FraudOutput, RiskLevel
from .vision import encode

# ICD-10 chapters that indicate pregnancy/maternity (O00-O9A, plus Z34/Z33/Z3A).
_PREGNANCY_PREFIXES = ("O", "Z34", "Z33", "Z3A")
_MATERNITY_CPT = {"59400", "59409", "59410", "59510", "59610"}


def _is_pregnancy_icd(code: str) -> bool:
    c = code.upper().strip()
    return c.startswith(_PREGNANCY_PREFIXES)


# ──────────────────────────────────────────────────────────────────────
# Deterministic rules over structured extractions
# ──────────────────────────────────────────────────────────────────────
def _rule_signals(case: Case) -> list[tuple[str, float]]:
    """Return (anomaly_description, score) for every deterministic rule fired."""
    signals: list[tuple[str, float]] = []

    claim_docs = [d for d in case.documents if d.classification
                  and d.classification.doc_type == DocType.CLAIM_FORM]
    id_docs = [d for d in case.documents if d.classification
               and d.classification.doc_type == DocType.ID_DOCUMENT]

    # duplicate_claim: more than one claim form in a single case.
    if len(claim_docs) > 1:
        signals.append(("duplicate_claim: multiple claim forms submitted for one case", 0.85))

    for d in claim_docs:
        cl = d.claims
        if not cl:
            continue
        # amount_under_10k (structuring)
        if cl.claim_amount is not None and 9000 <= cl.claim_amount < 10000:
            signals.append(
                (f"amount_under_10k: total ${cl.claim_amount:,.2f} just below $10,000 threshold", 0.8)
            )
        # proc_diag_mismatch: maternity CPT with non-pregnancy diagnosis
        if any(c in _MATERNITY_CPT for c in cl.cpt_codes):
            if cl.icd10_codes and not any(_is_pregnancy_icd(c) for c in cl.icd10_codes):
                signals.append(
                    ("proc_diag_mismatch: maternity CPT billed on non-maternity diagnosis "
                     f"({', '.join(cl.icd10_codes)})", 0.85)
                )

    # name_mismatch: last name + DOB match the policyholder, but the first name
    # differs — the injected name-swap fraud. (A generic member_not_matched from
    # an OCR miss does NOT trigger this.)
    for d in id_docs:
        if d.kyc and "name_mismatch" in d.kyc.flags:
            signals.append(("name_mismatch: ID first name does not match policyholder on file", 0.8))

    return signals


# ──────────────────────────────────────────────────────────────────────
# LLM anomaly pass (temporal / cross-document)
# ──────────────────────────────────────────────────────────────────────
_LLM_SYSTEM = """You are a health-insurance fraud analyst. You are shown the \
documents for a single claim case (which may include a discharge summary and a \
prescription). Look specifically for two temporal red flags:
1. readmission within 30 days: the discharge summary references a prior \
hospitalization/admission that ended fewer than 30 days before the current one.
2. date conflict: the prescription date is 45 or more days after the service / \
discharge date, which is temporally implausible.
Report only what the documents actually show."""

_LLM_TOOL = {
    "name": "record_fraud_anomalies",
    "description": "Record temporal fraud anomalies found across the case documents.",
    "input_schema": {
        "type": "object",
        "properties": {
            "readmission_30d": {"type": "boolean"},
            "date_conflict": {"type": "boolean"},
            "anomalies": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "required": ["readmission_30d", "date_conflict", "confidence"],
    },
}


def _llm_anomaly_pass(case: Case, client: anthropic.Anthropic) -> list[tuple[str, float]]:
    # Send discharge + prescription images (the temporally relevant docs).
    relevant = [
        d for d in case.documents
        if d.classification and d.classification.doc_type
        in (DocType.DISCHARGE_SUMMARY, DocType.PRESCRIPTION, DocType.CLAIM_FORM)
    ]
    if not relevant:
        return []

    content: list[dict] = []
    for d in relevant:
        media_type, data = encode_safe(d.stored_path)
        if data is None:
            continue
        kind = "document" if media_type == "application/pdf" else "image"
        content.append({"type": kind, "source": {
            "type": "base64", "media_type": media_type, "data": data}})
    content.append({"type": "text", "text":
                    "Inspect these case documents for readmission-within-30-days and "
                    "date-conflict anomalies."})
    if len(content) == 1:  # only the text block, no images decoded
        return []

    response = client.messages.create(
        model=CLASSIFIER_MODEL,
        max_tokens=1024,
        system=_LLM_SYSTEM,
        tools=[_LLM_TOOL],
        tool_choice={"type": "tool", "name": _LLM_TOOL["name"]},
        messages=[{"role": "user", "content": content}],
    )
    data = {}
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            data = block.input
            break

    signals: list[tuple[str, float]] = []
    if data.get("readmission_30d"):
        signals.append(("readmission_30d: prior admission < 30 days before current", 0.8))
    if data.get("date_conflict"):
        signals.append(("date_conflict: prescription dated 45+ days after service", 0.8))
    # The model's free-text observations are recorded for transparency but carry
    # ZERO weight: only the two temporal fraud patterns above may raise the score.
    # (Coverage issues like "procedure unrelated to diagnosis" are the Policy
    # agent's job, not fraud — otherwise we double-count the same fact.)
    for a in data.get("anomalies", []):
        signals.append((f"note: {a}", 0.0))
    return signals


def encode_safe(path: str):
    from pathlib import Path
    try:
        return encode(Path(path))
    except Exception:  # noqa: BLE001
        return None, None


# ──────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────
def assess_fraud(case: Case, client: anthropic.Anthropic | None = None,
                 use_llm: bool = True) -> FraudOutput:
    signals = _rule_signals(case)

    if use_llm:
        client = client or anthropic.Anthropic(api_key=require_api_key())
        try:
            signals += _llm_anomaly_pass(case, client)
        except Exception as exc:  # noqa: BLE001 - LLM pass is best-effort
            signals.append((f"llm_pass_error: {exc}", 0.0))

    fraud_score = max((s for _, s in signals), default=0.0)
    anomalies = [desc for desc, _ in signals]

    if fraud_score >= 0.7:
        risk = RiskLevel.HIGH
    elif fraud_score >= 0.3:
        risk = RiskLevel.MEDIUM
    else:
        risk = RiskLevel.LOW

    return FraudOutput(
        fraud_score=round(fraud_score, 2),
        risk_level=risk,
        anomalies=anomalies,
        confidence=0.9 if signals else 0.8,
        flags=[a.split(":")[0] for a, _ in signals],
    )
