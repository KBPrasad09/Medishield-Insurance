"""
Pipeline runner — the orchestration seam.

Day 2 scope: classify a freshly uploaded document, persist the result, and
advance case status. This function is invoked as a FastAPI BackgroundTask so
the upload request returns immediately while classification runs behind it.

Later days extend `process_document` (and add a case-level `process_case`) with
KYC / Claims / Policy / Fraud / Orchestrator stages. Keeping the entry point
stable now means the API layer never changes as the graph grows.
"""

from __future__ import annotations

import logging

from . import db
from .agents.claims import run_claims
from .agents.classifier import classify_document
from .agents.kyc import run_kyc
from .agents.policy import run_policy
from .config import CONFIDENCE_THRESHOLD
from .schemas import CaseStatus, DocType


def _plan_tier_from_policy(policy_number: str | None) -> str:
    if policy_number and "SLV" in policy_number.upper():
        return "SILVER"
    return "GOLD"  # default plan when the number is unreadable

log = logging.getLogger("medishield.pipeline")


def process_document(doc_id: str) -> None:
    """Run the (current) pipeline for one uploaded document."""
    doc = db.get_document(doc_id)
    if doc is None:
        log.warning("process_document: doc %s not found", doc_id)
        return

    try:
        result = classify_document(doc.stored_path)
        db.set_document_classification(doc_id, result)

        low_conf = result.confidence < CONFIDENCE_THRESHOLD
        if result.doc_type == DocType.UNKNOWN or low_conf:
            # Out-of-domain or unreliable -> human review queue (per brief).
            db.update_case_status(doc.case_id, CaseStatus.NEEDS_REVIEW)
            log.info("Classified %s -> %s (conf=%.2f) [review]",
                     doc_id, result.doc_type.value, result.confidence)
            return

        db.update_case_status(doc.case_id, CaseStatus.PROCESSING)
        log.info("Classified %s -> %s (conf=%.2f)",
                 doc_id, result.doc_type.value, result.confidence)

        # Route to the specialist agent for this document type.
        _run_specialist(doc_id, doc.stored_path, result.doc_type)

    except Exception:  # noqa: BLE001 - never let a background task crash silently
        log.exception("Classification failed for %s", doc_id)
        db.update_case_status(doc.case_id, CaseStatus.FAILED)


def _run_specialist(doc_id: str, path: str, doc_type: DocType) -> None:
    """Dispatch a classified document to its specialist agent (Day 3 subset)."""
    if doc_type == DocType.ID_DOCUMENT:
        kyc = run_kyc(path)
        db.set_document_kyc(doc_id, kyc)
        log.info("KYC %s -> passed=%s flags=%s", doc_id, kyc.kyc_passed, kyc.flags)
    elif doc_type == DocType.CLAIM_FORM:
        claims = run_claims(path)
        db.set_document_claims(doc_id, claims)
        log.info("Claims %s -> schema_valid=%s errors=%s",
                 doc_id, claims.schema_valid, claims.validation_errors)

        # Policy RAG depends on the CPT codes the Claims agent just extracted.
        if claims.cpt_codes:
            tier = _plan_tier_from_policy(claims.member_policy_number)
            diagnosis = claims.icd10_codes[0] if claims.icd10_codes else None
            policy = run_policy(claims.cpt_codes, tier, diagnosis)
            db.set_document_policy(doc_id, policy)
            log.info("Policy %s -> covered=%s exclusions=%s",
                     doc_id, policy.covered, policy.exclusions)
    # DISCHARGE_SUMMARY / PRESCRIPTION / POLICY_AMENDMENT specialists come later.
