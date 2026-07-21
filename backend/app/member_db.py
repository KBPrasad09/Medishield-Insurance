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
