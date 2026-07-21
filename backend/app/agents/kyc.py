"""
KYC Agent — identity verification on ID_DOCUMENT images.

Two-part check (vision + database):
  1. Vision extraction: read the ID's name, DOB, expiry, and look for tamper /
     expired markings. IDs in this dataset literally stamp "** EXPIRED **" and
     tampered ones show visual artifacts, so the vision model can detect both.
  2. Database validation: match the extracted identity against the member
     reference DB. A name that isn't on file (e.g. an ID whose name doesn't match
     the policyholder) fails the match — that catches the name-mismatch fraud.

kyc_passed = identity matched AND not expired AND not tampered.
"""

from __future__ import annotations

from .. import member_db
from ..schemas import KYCOutput
from .vision import extract

_SYSTEM_PROMPT = """You are the KYC Agent in an insurance intake pipeline. You \
are shown a scanned identity document (driver's license, passport, state ID, \
insurance card, or medicare card). Read it carefully and report exactly what is \
printed.

Pay special attention to:
- Any visible "EXPIRED", "NOT VALID", or similar marking, or an expiration date \
that has clearly passed -> set appears_expired = true.
- Signs of tampering: mismatched fonts, misaligned text, digitally altered \
fields, inconsistent backgrounds, pixelation around specific fields -> set \
tamper_suspected = true and describe what you saw.
Report values as printed; use empty string if a field is not present."""

_TOOL = {
    "name": "record_kyc_extraction",
    "description": "Record identity fields read from the ID document.",
    "input_schema": {
        "type": "object",
        "properties": {
            "full_name": {"type": "string", "description": "Name as printed."},
            "dob": {"type": "string", "description": "Date of birth, MM/DD/YYYY."},
            "id_type": {"type": "string", "description": "e.g. drivers_license, passport."},
            "id_number": {"type": "string", "description": "License/policy/member number if visible."},
            "expiry_date": {"type": "string", "description": "Expiration date as printed."},
            "appears_expired": {"type": "boolean"},
            "tamper_suspected": {"type": "boolean"},
            "tamper_notes": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "required": ["full_name", "appears_expired", "tamper_suspected", "confidence"],
    },
}


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def run_kyc(image_path: str, client=None) -> KYCOutput:
    data = extract(image_path, _SYSTEM_PROMPT, _TOOL, client=client)

    full_name = data.get("full_name", "")
    dob = data.get("dob", "")
    id_expired = bool(data.get("appears_expired", False))
    tampered = bool(data.get("tamper_suspected", False))

    # ---- Database validation -------------------------------------------
    member = member_db.find_member_by_name(full_name)
    if member is None and data.get("id_number"):
        member = member_db.find_member_by_policy(data["id_number"])

    id_matched = member is not None
    dob_matches = bool(member) and _norm(member["dob"]) == _norm(dob)
    # If we found the member but the DOB disagrees, treat identity as unverified.
    member_id_matched = id_matched and (dob_matches or not dob)

    flags: list[str] = []
    if not member_id_matched:
        flags.append("member_not_matched")
    if id_expired:
        flags.append("id_expired")
    if tampered:
        flags.append("tamper_suspected")

    kyc_passed = member_id_matched and not id_expired and not tampered

    notes = data.get("tamper_notes") or None
    if member is None:
        notes = (notes + " | " if notes else "") + f"No member on file for '{full_name}'."

    return KYCOutput(
        kyc_passed=kyc_passed,
        member_id_matched=member_id_matched,
        id_expired=id_expired,
        tamper_suspected=tampered,
        confidence=float(data.get("confidence", 0.0)),
        flags=flags,
        notes=notes,
    )
