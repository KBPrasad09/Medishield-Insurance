"""
MediShield ingestion API — Day 1 scaffold.

Endpoints:
  POST /cases/{case_id}/documents  upload a file into a case (case created if new)
  GET  /cases                      dashboard list (light summaries)
  GET  /cases/{case_id}            full case with all documents

The pipeline (classifier -> specialists -> fraud -> orchestrator) is not wired
yet; uploads land in status RECEIVED. Day 2+ adds a BackgroundTask that walks
the case through the LangGraph state machine.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware

from . import db, pipeline, storage
from .schemas import Case, CaseSummary, Document

ALLOWED_CONTENT = {
    "image/jpeg",
    "image/png",
    "image/tiff",
    "application/pdf",
}

app = FastAPI(title="MediShield Document Intake", version="0.1.0")

# Next.js dev server talks to us cross-origin during the demo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Surface agent progress logs (KYC/Claims/Policy/Fraud) in the console — useful
# for the demo and for watching a case move through the pipeline.
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter("%(levelname)s:     [%(name)s] %(message)s"))
_agent_log = logging.getLogger("medishield")
if not _agent_log.handlers:
    _agent_log.addHandler(_handler)
_agent_log.setLevel(logging.INFO)
_agent_log.propagate = False

# Ensure tables exist however the app is launched (uvicorn, tests, imports).
db.init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/cases/{case_id}/documents", response_model=Case, status_code=201)
async def upload_document(
    case_id: str,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    patient_id: Optional[str] = Form(None),
) -> Case:
    if file.content_type not in ALLOWED_CONTENT:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported type {file.content_type!r}. "
            f"Allowed: {sorted(ALLOWED_CONTENT)}",
        )

    db.create_case_if_absent(case_id, patient_id)

    stored_path = storage.save(case_id, file.filename, file.file)
    doc = Document(
        doc_id=f"doc_{uuid.uuid4().hex[:12]}",
        case_id=case_id,
        filename=file.filename,
        stored_path=stored_path,
        content_type=file.content_type,
    )
    db.add_document(doc)

    # Kick off classification without blocking the response.
    background.add_task(pipeline.process_document, doc.doc_id)

    case = db.get_case(case_id)
    if case is None:  # should never happen right after create
        raise HTTPException(status_code=500, detail="Case vanished after write")
    return case


@app.get("/cases", response_model=list[CaseSummary])
def list_cases() -> list[CaseSummary]:
    return db.list_cases()


@app.get("/cases/{case_id}", response_model=Case)
def get_case(case_id: str) -> Case:
    case = db.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"No case {case_id!r}")
    return case
