"""
MediShield document-intake API.

Endpoints:
  POST /cases/{case_id}/documents  upload a file into a case (case created if new)
  GET  /cases                      dashboard list (light summaries)
  GET  /cases/{case_id}            full case with all documents
  POST /cases/{case_id}/finalize   run the LangGraph decision (fraud -> orchestrator)
  POST /cases/{case_id}/override   human reviewer sets the final decision
  GET  /documents/{doc_id}/image   serve a stored document image for the UI

Uploads are processed asynchronously: each document is classified and routed to
its specialist agent in a BackgroundTask, then the case-level decision graph is
run on finalize.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
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
from fastapi.responses import FileResponse

from . import db, graph, pipeline, storage
from .schemas import (
    Case,
    CaseStatus,
    CaseSummary,
    Decision,
    Document,
    OverrideRequest,
)

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
log = logging.getLogger("medishield.api")

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


@app.post("/cases/{case_id}/finalize", response_model=Case)
def finalize_case(case_id: str) -> Case:
    """Run the case-level decision graph (Fraud -> Orchestrator) and return the
    decided case. Call once all of a case's documents have been uploaded."""
    if db.get_case(case_id) is None:
        raise HTTPException(status_code=404, detail=f"No case {case_id!r}")
    case = graph.run_case_decision(case_id)
    return case


@app.delete("/cases/{case_id}")
def delete_case(case_id: str) -> dict:
    """Remove a case and its documents (housekeeping for test/demo data)."""
    if not db.delete_case(case_id):
        raise HTTPException(status_code=404, detail=f"No case {case_id!r}")
    return {"deleted": case_id}


@app.post("/cases/{case_id}/override", response_model=Case)
def override_case(case_id: str, req: OverrideRequest) -> Case:
    """Human-in-the-loop: a reviewer sets the final decision on an escalated case.

    The automated decision is preserved in `original_decision` so the audit trail
    always shows what the system decided and who overrode it.
    """
    case = db.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"No case {case_id!r}")
    if case.decision is None:
        raise HTTPException(
            status_code=409,
            detail="Case has no automated decision yet — finalize it first.",
        )

    decision = case.decision
    decision.original_decision = decision.original_decision or decision.decision
    decision.decision = req.decision
    decision.overridden_by = req.reviewer
    decision.override_reason = req.reason
    decision.overridden_at = datetime.utcnow()

    db.set_case_decision(case_id, decision)
    db.update_case_status(case_id, CaseStatus.DECIDED)
    log.info("Override %s -> %s by %s (%s)", case_id, req.decision.value,
             req.reviewer, req.reason)
    return db.get_case(case_id)


@app.get("/documents/{doc_id}/image")
def get_document_image(doc_id: str):
    """Serve a stored document image so the review UI can display it."""
    doc = db.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"No document {doc_id!r}")
    path = Path(doc.stored_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored file is missing")
    return FileResponse(path, media_type=doc.content_type or "image/png")
