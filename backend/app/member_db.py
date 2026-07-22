"""
Read-only access to the member reference database (backend/reference.db).

This stands in for MediShield's real member system. The KYC agent validates a
scanned ID against it; the Fraud agent (Day 4) uses cluster_reference for
history. Built by scripts/build_reference_data.py.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

REFERENCE_DB_PATH = Path(__file__).resolve().parent.parent / "reference.db"


def _connect() -> sqlite3.Connection:
    if not REFERENCE_DB_PATH.exists():
        raise RuntimeError(
            "reference.db not found. Run: python scripts/build_reference_data.py"
        )
    conn = sqlite3.connect(REFERENCE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def find_member_by_policy(policy_number: str) -> Optional[dict]:
    """Exact policy-number match. Returns member dict or None."""
    if not policy_number:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM members WHERE policy_number = ?",
            (policy_number.strip().upper(),),
        ).fetchone()
    return dict(row) if row else None


def find_member_by_name(full_name: str) -> Optional[dict]:
    """Loose name match fallback when the policy number is unreadable."""
    if not full_name:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM members WHERE LOWER(full_name) = LOWER(?)",
            (full_name.strip(),),
        ).fetchone()
    return dict(row) if row else None


# ──────────────────────────────────────────────────────────────────────
# Robust identity matching (tolerant of OCR/format variance)
# ──────────────────────────────────────────────────────────────────────
def _name_tokens(name: str) -> list[str]:
    """Lowercased alphabetic tokens of length >= 2 (drops middle initials)."""
    import re

    return [t for t in re.findall(r"[A-Za-z]{2,}", (name or "").lower())]


def _dob_digits(dob: str) -> str:
    import re

    return re.sub(r"\D", "", dob or "")


def match_identity(full_name: str, dob: str) -> tuple[Optional[dict], bool]:
    """
    Match an ID's (name, dob) against the member roster.

    Returns (member, first_name_matches):
      - member is the roster record whose LAST NAME + DOB agree with the ID
        (robust anchor — last names and DOBs are printed clearly), or None if
        no such person is on file.
      - first_name_matches is True only if the ID's first name also agrees. A
        found member with a mismatching first name is exactly the injected
        name-swap fraud (e.g. "Mary" printed as "Mery").
    """
    id_tokens = _name_tokens(full_name)
    id_dob = _dob_digits(dob)
    if not id_tokens:
        return None, False
    id_first, id_last = id_tokens[0], id_tokens[-1]

    with _connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM members").fetchall()]

    # Primary: last name + DOB anchor.
    for m in rows:
        mt = _name_tokens(m["full_name"])
        if not mt:
            continue
        if mt[-1] == id_last and id_dob and _dob_digits(m["dob"]) == id_dob:
            return m, (mt[0] == id_first)

    # Fallback: exact full-name token set (when DOB is unreadable).
    for m in rows:
        if set(_name_tokens(m["full_name"])) == set(id_tokens):
            return m, True

    return None, False
