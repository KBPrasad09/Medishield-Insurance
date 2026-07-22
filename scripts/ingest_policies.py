"""
One-off (or re-runnable) policy ingestion into the vector store.

Run from repo root:
    python scripts/ingest_policies.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app import policy_rag  # noqa: E402

if __name__ == "__main__":
    n = policy_rag.ingest_policies()
    print(f"Ingested {n} policy chunks into {policy_rag.QDRANT_DIR}")
