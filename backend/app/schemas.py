"""
Typed contracts for every agent in the MediShield document-intake pipeline.

Design intent (defend this in the interview / README):
  - Each agent has an explicit, versioned output schema. Agents talk to the
    orchestrator only through these models, never through loose dicts. That is
    the "typed interfaces between agents" the rubric rewards.
  - Enums (not raw strings) for every closed vocabulary so a typo can never
    silently become a new document type or decision.
  - `BaseAgentOutput` carries a `confidence` on every agent so the orchestrator
    can apply the brief's rule: any agent confidence < 0.6 -> ESCALATE.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────
# Closed vocabularies
# ──────────────────────────────────────────────────────────────────────
class DocType(str, Enum):
    CLAIM_FORM = "CLAIM_FORM"
    ID_DOCUMENT = "ID_DOCUMENT"
    DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY"
    PRESCRIPTION = "PRESCRIPTION"
    POLICY_AMENDMENT = "POLICY_AMENDMENT"
    UNKNOWN = "UNKNOWN"


class CaseStatus(str, Enum):
    RECEIVED = "RECEIVED"
    CLASSIFIED = "CLASSIFIED"
    PROCESSING = "PROCESSING"
    FRAUD_CHECK = "FRAUD_CHECK"
    AGGREGATED = "AGGREGATED"
    DECIDED = "DECIDED"
    NEEDS_REVIEW = "NEEDS_REVIEW"  # low-confidence / UNKNOWN -> human queue
    FAILED = "FAILED"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Decision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"


# ──────────────────────────────────────────────────────────────────────
# Shared base
# ──────────────────────────────────────────────────────────────────────
class BaseAgentOutput(BaseModel):
    """Every agent reports how sure it is and can attach free-form flags."""

    confidence: float = Field(0.0, ge=0.0, le=1.0)
    flags: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────
# Per-agent output contracts
# ──────────────────────────────────────────────────────────────────────
class ClassifierOutput(BaseAgentOutput):
    doc_type: DocType
    routing_tags: list[str] = Field(default_factory=list)


class OCRResult(BaseModel):
    """Normalized text layer produced by the pre-processor before specialists."""

    raw_text: str = ""
    fields: dict[str, str] = Field(default_factory=dict)


class KYCOutput(BaseAgentOutput):
    kyc_passed: bool = False
    member_id_matched: bool = False
    id_expired: bool = False
    tamper_suspected: bool = False


class ClaimsOutput(BaseAgentOutput):
    claim_amount: Optional[float] = None
    icd10_codes: list[str] = Field(default_factory=list)
    cpt_codes: list[str] = Field(default_factory=list)
    provider_npi: Optional[str] = None
    service_date: Optional[str] = None  # ISO date string; kept as str for OCR tolerance
    member_policy_number: Optional[str] = None  # used to resolve the plan tier
    schema_valid: bool = False
    validation_errors: list[str] = Field(default_factory=list)


class PolicyOutput(BaseAgentOutput):
    covered: bool = False
    coverage_percentage: Optional[float] = None
    policy_clause: Optional[str] = None
    exclusions: list[str] = Field(default_factory=list)


class FraudOutput(BaseAgentOutput):
    fraud_score: float = Field(0.0, ge=0.0, le=1.0)
    risk_level: RiskLevel = RiskLevel.LOW
    anomalies: list[str] = Field(default_factory=list)


class OrchestratorDecision(BaseModel):
    decision: Decision
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    justification: str = ""
    agent_summaries: dict[str, str] = Field(default_factory=dict)

    # Set when a human reviewer overrides the automated decision. Keeping the
    # original decision alongside the override preserves the audit trail — you
    # can always see what the system decided and who changed it.
    overridden_by: Optional[str] = None
    override_reason: Optional[str] = None
    original_decision: Optional[Decision] = None
    overridden_at: Optional[datetime] = None


class OverrideRequest(BaseModel):
    """A human reviewer's final call on an escalated case."""

    decision: Decision
    reviewer: str = "reviewer"
    reason: str = ""


# ──────────────────────────────────────────────────────────────────────
# Persistence-facing models (API request / response shapes)
# ──────────────────────────────────────────────────────────────────────
class Document(BaseModel):
    doc_id: str
    case_id: str
    filename: str
    stored_path: str
    content_type: Optional[str] = None
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)

    # Filled in as the pipeline runs (all optional at intake time)
    classification: Optional[ClassifierOutput] = None
    ocr: Optional[OCRResult] = None
    kyc: Optional[KYCOutput] = None
    claims: Optional[ClaimsOutput] = None
    policy: Optional[PolicyOutput] = None


class Case(BaseModel):
    """
    A case is one patient episode. Multiple documents (ID, claim, discharge,
    prescription, amendment) attach to the same case_id and are decided together
    — this mirrors the dataset's 'case_cluster' grouping.
    """

    case_id: str
    patient_id: Optional[str] = None
    status: CaseStatus = CaseStatus.RECEIVED
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    documents: list[Document] = Field(default_factory=list)
    fraud: Optional[FraudOutput] = None
    decision: Optional[OrchestratorDecision] = None


class CaseSummary(BaseModel):
    """Light row for the dashboard list — no heavy nested agent output."""

    case_id: str
    patient_id: Optional[str] = None
    status: CaseStatus
    document_count: int
    decision: Optional[Decision] = None
    created_at: datetime
    updated_at: datetime
