"""
Build reference data used by the pipeline and the eval harness.

The synthetic documents are generated deterministically (random seed 42) by
generate_docs.py. That same seed lets us reproduce the exact ground-truth values
rendered on every document WITHOUT re-generating images. We use it for two things:

  1. dataset/ground_truth.json  — canonical answer key (identity fields, ICD/CPT,
     amounts, fraud labels, edge flags) used by the Day-5 eval harness.
  2. backend/reference.db       — the "member database" the KYC agent validates
     against, plus a per-cluster reference table the Claims/Fraud agents use.

Run from the repo root (after the dataset exists):
    python scripts/build_reference_data.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import generate_docs as g  # noqa: E402  (reproduces the seeded clusters)

GROUND_TRUTH_PATH = REPO_ROOT / "dataset" / "ground_truth.json"
REFERENCE_DB_PATH = REPO_ROOT / "backend" / "reference.db"


def _plan_tier(policy: str) -> str:
    if "GLD" in policy:
        return "GOLD"
    if "SLV" in policy:
        return "SILVER"
    return "UNKNOWN"


def _serialize_cluster(c: dict) -> dict:
    """Make one cluster JSON-safe and flatten the fields we care about."""
    out = dict(c)
    # datetime -> ISO date string
    td = c.get("treatment_date")
    if isinstance(td, datetime):
        out["treatment_date"] = td.strftime("%Y-%m-%d")
    # cpt_list is a list of (code, desc, price) tuples
    out["cpt_list"] = [
        {"code": code, "desc": desc, "price": price}
        for (code, desc, price) in c.get("cpt_list", [])
    ]
    return out


def build() -> None:
    clusters, _blurry = g.generate_patient_clusters(30)

    # ---- 1. ground_truth.json --------------------------------------------
    GROUND_TRUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    serialized = [_serialize_cluster(c) for c in clusters]
    GROUND_TRUTH_PATH.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
    print(f"Wrote {GROUND_TRUTH_PATH}  ({len(serialized)} clusters)")

    # ---- 2. reference.db --------------------------------------------------
    REFERENCE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if REFERENCE_DB_PATH.exists():
        REFERENCE_DB_PATH.unlink()

    conn = sqlite3.connect(REFERENCE_DB_PATH)
    conn.executescript(
        """
        CREATE TABLE members (
            policy_number TEXT PRIMARY KEY,
            patient_id    TEXT NOT NULL,
            full_name     TEXT NOT NULL,
            dob           TEXT NOT NULL,   -- MM/DD/YYYY as printed on IDs
            plan_tier     TEXT NOT NULL,
            state         TEXT
        );

        CREATE TABLE cluster_reference (
            cluster_id     TEXT PRIMARY KEY,
            patient_id     TEXT NOT NULL,
            policy_number  TEXT NOT NULL,
            claim_number   TEXT,
            service_date   TEXT,
            primary_icd    TEXT,
            cpt_codes      TEXT,           -- JSON list of CPT code strings
            provider_npi   TEXT,
            is_fraud       INTEGER,
            fraud_reason   TEXT,
            edge_flags     TEXT            -- JSON list
        );
        """
    )

    for c in clusters:
        conn.execute(
            "INSERT INTO members VALUES (?,?,?,?,?,?)",
            (
                c["policy"],
                c["patient_id"],
                c["name"],
                c["dob"],
                _plan_tier(c["policy"]),
                c.get("state"),
            ),
        )
        td = c["treatment_date"]
        service_date = td.strftime("%Y-%m-%d") if isinstance(td, datetime) else str(td)
        cpt_codes = [code for (code, _desc, _price) in c.get("cpt_list", [])]
        conn.execute(
            "INSERT INTO cluster_reference VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                c["cluster_id"],
                c["patient_id"],
                c["policy"],
                c.get("claim_number"),
                service_date,
                c.get("icd_code"),
                json.dumps(cpt_codes),
                c.get("npi"),
                1 if c.get("is_fraud") else 0,
                c.get("fraud_reason"),
                json.dumps(c.get("edge_flags", [])),
            ),
        )

    conn.commit()
    n_members = conn.execute("SELECT COUNT(*) FROM members").fetchone()[0]
    conn.close()
    print(f"Wrote {REFERENCE_DB_PATH}  ({n_members} members)")


if __name__ == "__main__":
    build()
