"""
SQLite persistence layer.

Why plain sqlite3 + JSON columns (design decision, note in README):
  - Zero external services to stand up for a demo/eval — the graders can clone
    and run with nothing but Python. A production build would swap this module
    for Postgres behind the same function signatures; nothing else changes.
  - Agent outputs are stored as JSON text columns rather than a wide relational
    schema. The agent contracts evolve fast during development; serializing the
    Pydantic models keeps the DB from becoming a migration bottleneck this week.
  - Two tables: `cases` (one row per patient episode) and `documents`
    (many per case). The FK ties documents to their case.

Everything is funneled through small helper functions so the API layer never
writes SQL directly.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .schemas import (
    Case,
    CaseStatus,
    CaseSummary,
    ClassifierOutput,
    Decision,
    Document,
)

DB_PATH = Path(__file__).resolve().parent.parent / "medishield.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS cases (
                case_id     TEXT PRIMARY KEY,
                patient_id  TEXT,
                status      TEXT NOT NULL,
                fraud       TEXT,           -- JSON FraudOutput or NULL
                decision    TEXT,           -- JSON OrchestratorDecision or NULL
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS documents (
                doc_id        TEXT PRIMARY KEY,
                case_id       TEXT NOT NULL,
                filename      TEXT NOT NULL,
                stored_path   TEXT NOT NULL,
                content_type  TEXT,
                uploaded_at   TEXT NOT NULL,
                classification TEXT,        -- JSON ClassifierOutput or NULL
                ocr           TEXT,
                kyc           TEXT,
                claims        TEXT,
                policy        TEXT,
                FOREIGN KEY (case_id) REFERENCES cases (case_id) ON DELETE CASCADE
            );
            """
        )


# ──────────────────────────────────────────────────────────────────────
# Case operations
# ──────────────────────────────────────────────────────────────────────
def create_case_if_absent(case_id: str, patient_id: Optional[str] = None) -> Case:
    now = datetime.utcnow().isoformat()
    with _connect() as conn:
        existing = conn.execute(
            "SELECT case_id FROM cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        if existing is None:
            conn.execute(
                """INSERT INTO cases (case_id, patient_id, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (case_id, patient_id, CaseStatus.RECEIVED.value, now, now),
            )
        elif patient_id is not None:
            # Backfill patient_id if we learned it from a later upload.
            conn.execute(
                "UPDATE cases SET patient_id = COALESCE(patient_id, ?), updated_at = ? "
                "WHERE case_id = ?",
                (patient_id, now, case_id),
            )
    return get_case(case_id)  # type: ignore[return-value]


def update_case_status(case_id: str, status: CaseStatus) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE cases SET status = ?, updated_at = ? WHERE case_id = ?",
            (status.value, datetime.utcnow().isoformat(), case_id),
        )


def get_case(case_id: str) -> Optional[Case]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        if row is None:
            return None
        docs = conn.execute(
            "SELECT * FROM documents WHERE case_id = ? ORDER BY uploaded_at",
            (case_id,),
        ).fetchall()

    return _row_to_case(row, docs)


def list_cases() -> list[CaseSummary]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT c.*, COUNT(d.doc_id) AS doc_count
               FROM cases c LEFT JOIN documents d ON c.case_id = d.case_id
               GROUP BY c.case_id
               ORDER BY c.created_at DESC"""
        ).fetchall()

    summaries: list[CaseSummary] = []
    for r in rows:
        decision = None
        if r["decision"]:
            decision = Decision(json.loads(r["decision"])["decision"])
        summaries.append(
            CaseSummary(
                case_id=r["case_id"],
                patient_id=r["patient_id"],
                status=CaseStatus(r["status"]),
                document_count=r["doc_count"],
                decision=decision,
                created_at=datetime.fromisoformat(r["created_at"]),
                updated_at=datetime.fromisoformat(r["updated_at"]),
            )
        )
    return summaries


# ──────────────────────────────────────────────────────────────────────
# Document operations
# ──────────────────────────────────────────────────────────────────────
def add_document(doc: Document) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO documents
               (doc_id, case_id, filename, stored_path, content_type, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                doc.doc_id,
                doc.case_id,
                doc.filename,
                doc.stored_path,
                doc.content_type,
                doc.uploaded_at.isoformat(),
            ),
        )
        conn.execute(
            "UPDATE cases SET updated_at = ? WHERE case_id = ?",
            (datetime.utcnow().isoformat(), doc.case_id),
        )


def set_document_classification(doc_id: str, result: ClassifierOutput) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE documents SET classification = ? WHERE doc_id = ?",
            (result.model_dump_json(), doc_id),
        )


def get_document(doc_id: str) -> Optional[Document]:
    with _connect() as conn:
        d = conn.execute(
            "SELECT * FROM documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
    return _row_to_document(d) if d else None


# ──────────────────────────────────────────────────────────────────────
# Row -> model helpers
# ──────────────────────────────────────────────────────────────────────
def _row_to_case(row: sqlite3.Row, doc_rows: list[sqlite3.Row]) -> Case:
    return Case(
        case_id=row["case_id"],
        patient_id=row["patient_id"],
        status=CaseStatus(row["status"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        fraud=json.loads(row["fraud"]) if row["fraud"] else None,
        decision=json.loads(row["decision"]) if row["decision"] else None,
        documents=[_row_to_document(d) for d in doc_rows],
    )


def _row_to_document(d: sqlite3.Row) -> Document:
    def _load(col: str):
        val = d[col]
        return json.loads(val) if val else None

    return Document(
        doc_id=d["doc_id"],
        case_id=d["case_id"],
        filename=d["filename"],
        stored_path=d["stored_path"],
        content_type=d["content_type"],
        uploaded_at=datetime.fromisoformat(d["uploaded_at"]),
        classification=_load("classification"),
        ocr=_load("ocr"),
        kyc=_load("kyc"),
        claims=_load("claims"),
        policy=_load("policy"),
    )
