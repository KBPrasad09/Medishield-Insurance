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

EXPIRY — set appears_expired = true ONLY if the document displays an explicit \
"EXPIRED", "NOT VALID", "CARD EXPIRED", or similar stamp/marking on its face. Do \
NOT infer expiry by comparing the printed expiration date to today's date — many \
valid cards have near-term expiration dates. Absent an explicit expired marking, \
set appears_expired = false.

TAMPERING — inspect the EXPIRATION DATE and other data fields closely. Set \
tamper_suspected = true if a field (most often the expiration date) is rendered \
in a noticeably LARGER font, a DIFFERENT COLOR, or shifted/misaligned relative to \
the surrounding labels and values — telltale signs the value was digitally \
overwritten. Also flag obviously mismatched fonts or patched-over text. Do NOT \
flag general scan quality, blur, low resolution, or compression noise. When you \
flag it, name the field and describe what looked altered (e.g. "expiry date is \
larger and a different color than the other fields").

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

    # Image forensics (ELA) — advisory. Measured to carry no signal on this
    # dataset (eval/ela_findings.md), so it is reported, never acted on.
    try:
        from ..forensics import ela_score

        ela = ela_score(image_path)["top_z"]
    except Exception:  # noqa: BLE001 - forensics must never break intake
        ela = None

    full_name = data.get("full_name", "")
    dob = data.get("dob", "")
    id_expired = bool(data.get("appears_expired", False))
    tampered = bool(data.get("tamper_suspected", False))

    # ---- Database validation (robust to OCR/format variance) -----------
    member, name_matches = member_db.match_identity(full_name, dob)
    member_id_matched = member is not None and name_matches

    flags: list[str] = []
    if member is None:
        flags.append("member_not_matched")
    elif not name_matches:
        # Last name + DOB found the policyholder, but the first name differs —
        # this is the name-swap fraud pattern, not a simple lookup miss.
        flags.append("name_mismatch")
    if id_expired:
        flags.append("id_expired")
    if tampered:
        flags.append("tamper_suspected")

    kyc_passed = member_id_matched and not id_expired and not tampered

    notes = data.get("tamper_notes") or None
    if member is None:
        notes = (notes + " | " if notes else "") + f"No member on file for '{full_name}'."
    elif not name_matches:
        notes = (notes + " | " if notes else "") + (
            f"Last name + DOB match {member['full_name']}, but first name differs "
            f"(ID reads '{full_name}')."
        )

    return KYCOutput(
        kyc_passed=kyc_passed,
        member_id_matched=member_id_matched,
        id_expired=id_expired,
        tamper_suspected=tampered,
        ela_top_z=ela,
        confidence=float(data.get("confidence", 0.0)),
        flags=flags,
        notes=notes,
    )
