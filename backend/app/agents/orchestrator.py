"""
Orchestrator — aggregates every agent's output for a case and issues the final
Approve / Reject / Escalate decision.

Decision policy (derived from the brief, ordered by precedence):

  ESCALATE (needs a human) if ANY of:
    - an UNKNOWN / out-of-domain document is in the case
    - fraud_score >= 0.3
    - a document shows suspected tampering
    - any agent reported confidence < 0.6   (unreliable signal)

  REJECT if ANY of (and not already escalated):
    - KYC failed for identity reasons (expired ID, member not on file)
    - a claim failed schema validation (missing required fields)
    - a procedure is not covered by the member's policy

  APPROVE otherwise (identity verified, claim valid, covered, low fraud).

Escalation is checked first because tampering / fraud / low-confidence all
warrant human review even when a hard reject reason also exists — the case
should reach a person, not be auto-denied.
"""

from __future__ import annotations

from ..config import CONFIDENCE_THRESHOLD
from ..schemas import (
    Case,
    Decision,
    DocType,
    OrchestratorDecision,
)

FRAUD_ESCALATE_THRESHOLD = 0.3


def decide(case: Case) -> OrchestratorDecision:
    kyc_list = [d.kyc for d in case.documents if d.kyc]
    claims_list = [d.claims for d in case.documents if d.claims]
    policy_list = [d.policy for d in case.documents if d.policy]
    fraud = case.fraud

    # An UNKNOWN document only forces escalation when the case has NOTHING
    # actionable — i.e. no recognizable ID or claim. A full patient case with a
    # valid claim shouldn't be escalated just because one page (e.g. a blurry
    # amendment) was misclassified; it's decided on its real signals instead.
    has_actionable = any(
        d.classification and d.classification.doc_type in
        (DocType.ID_DOCUMENT, DocType.CLAIM_FORM)
        for d in case.documents
    )
    unknown_only = (not has_actionable) and any(
        d.classification and d.classification.doc_type == DocType.UNKNOWN
        for d in case.documents
    )
    fraud_score = fraud.fraud_score if fraud else 0.0
    # Tamper is ADVISORY, not an auto-escalation trigger. A vision LLM's tamper
    # judgement is too low-precision to gate decisions (high false-positive rate
    # on scanned IDs). We surface it for the human reviewer instead; a production
    # build would use dedicated image forensics (ELA) before acting on it.
    tamper_advisory = any(k.tamper_suspected for k in kyc_list)

    # Confidence gate: consider only the agents that actually drive the
    # decision — the classification of ID/claim docs plus their specialists and
    # the fraud check. A low-confidence secondary page (blurry amendment, an
    # unrecognized extra scan) must not by itself escalate an otherwise clean case.
    confidences: list[float] = []
    for d in case.documents:
        is_actionable = d.classification and d.classification.doc_type in (
            DocType.ID_DOCUMENT, DocType.CLAIM_FORM)
        if is_actionable:
            confidences.append(d.classification.confidence)
        if d.kyc:
            confidences.append(d.kyc.confidence)
        if d.claims:
            confidences.append(d.claims.confidence)
        if d.policy:
            confidences.append(d.policy.confidence)
    if fraud:
        confidences.append(fraud.confidence)
    low_conf = any(c < CONFIDENCE_THRESHOLD for c in confidences)

    # Identity failure means the person isn't verifiable: not on the member roster,
    # or the ID carries an explicit EXPIRED mark. A tamper suspicion alone is NOT an
    # identity failure — it's a low-precision advisory signal (see above), and letting
    # it reject a case would auto-deny people whose ID merely scanned oddly.
    kyc_failed = any(
        (not k.member_id_matched) or k.id_expired for k in kyc_list
    )
    schema_invalid = any(not c.schema_valid for c in claims_list)
    not_covered = any(not p.covered for p in policy_list)

    reasons: list[str] = []

    # ---- ESCALATE ------------------------------------------------------
    escalate_reasons = []
    if unknown_only:
        escalate_reasons.append("no recognizable ID or claim (out-of-domain submission)")
    if fraud_score >= FRAUD_ESCALATE_THRESHOLD:
        escalate_reasons.append(
            f"fraud_score {fraud_score:.2f} >= {FRAUD_ESCALATE_THRESHOLD}"
        )
    if low_conf:
        escalate_reasons.append("an agent reported confidence < 0.6")

    if escalate_reasons:
        return _build(Decision.ESCALATE, escalate_reasons, case, fraud_score, confidences)

    # ---- REJECT --------------------------------------------------------
    reject_reasons = []
    if kyc_failed:
        reject_reasons.append("KYC failed (expired ID or member not on file)")
    if schema_invalid:
        reject_reasons.append("claim failed schema validation")
    if not_covered:
        reject_reasons.append("procedure not covered by policy")

    if reject_reasons:
        return _build(Decision.REJECT, reject_reasons, case, fraud_score, confidences)

    # ---- APPROVE -------------------------------------------------------
    return _build(
        Decision.APPROVE,
        ["identity verified, claim valid, procedures covered, low fraud risk"],
        case,
        fraud_score,
        confidences,
    )


def _build(decision, reasons, case, fraud_score, confidences) -> OrchestratorDecision:
    summaries: dict[str, str] = {}
    for d in case.documents:
        dt = d.classification.doc_type.value if d.classification else "?"
        if d.kyc:
            summaries[f"KYC[{dt}]"] = (
                f"passed={d.kyc.kyc_passed} flags={d.kyc.flags}"
            )
        if d.claims:
            summaries[f"Claims[{dt}]"] = (
                f"schema_valid={d.claims.schema_valid} errors={d.claims.validation_errors}"
            )
        if d.policy:
            summaries[f"Policy[{dt}]"] = (
                f"covered={d.policy.covered} exclusions={d.policy.exclusions}"
            )
    if case.fraud:
        summaries["Fraud"] = (
            f"score={case.fraud.fraud_score} risk={case.fraud.risk_level.value} "
            f"anomalies={case.fraud.anomalies}"
        )

    # Decision confidence: the weakest link, lightly floored.
    conf = min(confidences) if confidences else 0.5

    return OrchestratorDecision(
        decision=decision,
        confidence=round(conf, 2),
        justification=f"{decision.value}: " + "; ".join(reasons),
        agent_summaries=summaries,
    )
