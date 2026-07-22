"""
Claims Agent — structured extraction on CLAIM_FORM images (CMS-1500 / UB-04).

Extracts the fields MediShield's claim standard requires, then validates the
schema. Missing required fields (the dataset's "missing_fields" edge cases)
produce validation_errors and schema_valid = false.
"""

from __future__ import annotations

import re

from ..schemas import ClaimsOutput
from .vision import extract

_SYSTEM_PROMPT = """You are the Claims Agent in an insurance intake pipeline. \
You are shown a scanned health insurance claim form (CMS-1500 or UB-04). \
Extract the billing fields exactly as printed. Read all diagnosis (ICD-10) and \
procedure (CPT) codes present. If a field is missing or illegible, leave it \
empty rather than guessing. Report the total billed amount as a number without \
currency symbols or commas."""

_TOOL = {
    "name": "record_claim_extraction",
    "description": "Record billing fields read from the claim form.",
    "input_schema": {
        "type": "object",
        "properties": {
            "claim_amount": {"type": "number", "description": "Total billed amount."},
            "icd10_codes": {"type": "array", "items": {"type": "string"}},
            "cpt_codes": {"type": "array", "items": {"type": "string"}},
            "provider_npi": {"type": "string", "description": "Rendering provider NPI."},
            "service_date": {"type": "string", "description": "Date of service."},
            "member_policy_number": {"type": "string",
                "description": "Insured's member/policy number (e.g. MED-GLD-1234567)."},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "required": ["icd10_codes", "cpt_codes", "confidence"],
    },
}

# Required by MediShield's claim submission standard.
_ICD10_RE = re.compile(r"^[A-TV-Z][0-9][0-9A-Z]\.?[0-9A-Z]{0,4}$", re.I)
_CPT_RE = re.compile(r"^\d{4,5}$")


def run_claims(image_path: str, client=None) -> ClaimsOutput:
    data = extract(image_path, _SYSTEM_PROMPT, _TOOL, client=client)

    amount = data.get("claim_amount")
    icd = [c.strip() for c in data.get("icd10_codes", []) if c and c.strip()]
    cpt = [c.strip() for c in data.get("cpt_codes", []) if c and c.strip()]
    npi = (data.get("provider_npi") or "").strip()
    service_date = (data.get("service_date") or "").strip()
    policy_number = (data.get("member_policy_number") or "").strip()

    errors: list[str] = []
    if amount is None:
        errors.append("missing_claim_amount")
    if not icd:
        errors.append("missing_diagnosis_code")
    if not cpt:
        errors.append("missing_procedure_code")
    if not npi:
        errors.append("missing_provider_npi")
    if not service_date:
        errors.append("missing_service_date")

    # Format checks on what we did extract.
    for code in icd:
        if not _ICD10_RE.match(code):
            errors.append(f"malformed_icd10:{code}")
    for code in cpt:
        if not _CPT_RE.match(code):
            errors.append(f"malformed_cpt:{code}")

    schema_valid = len(errors) == 0

    return ClaimsOutput(
        claim_amount=float(amount) if amount is not None else None,
        icd10_codes=icd,
        cpt_codes=cpt,
        provider_npi=npi or None,
        service_date=service_date or None,
        member_policy_number=policy_number or None,
        schema_valid=schema_valid,
        validation_errors=errors,
        confidence=float(data.get("confidence", 0.0)),
        flags=[] if schema_valid else ["schema_invalid"],
    )
