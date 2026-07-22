"""
LangGraph case-decision state machine.

The per-document specialists (classifier, KYC, claims, policy) already run at
upload time. This graph handles the case-level tail of the brief's flow:

    AGGREGATE  ->  FRAUD_CHECK  ->  ORCHESTRATE  ->  DECIDED

  - aggregate  : load the case with every document's specialist output
  - fraud_check: run the case-level Fraud agent (needs all documents together)
  - orchestrate: apply the Orchestrator decision rules
  - persist    : write fraud + decision, set status DECIDED / NEEDS_REVIEW

Modeling this as a LangGraph StateGraph (rather than a plain function) gives us
the explicit, inspectable state machine the brief asks for, and a natural place
to add checkpointing / streaming later.
"""

from __future__ import annotations

import logging
from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

from . import db
from .agents.fraud import assess_fraud
from .agents.orchestrator import decide
from .schemas import Case, CaseStatus, Decision, FraudOutput, OrchestratorDecision

log = logging.getLogger("medishield.graph")


class CaseState(TypedDict, total=False):
    case_id: str
    case: Optional[Case]
    fraud: Optional[FraudOutput]
    decision: Optional[OrchestratorDecision]


# ──────────────────────────────────────────────────────────────────────
# Nodes
# ──────────────────────────────────────────────────────────────────────
def _aggregate(state: CaseState) -> CaseState:
    case = db.get_case(state["case_id"])
    return {"case": case}


def _fraud_check(state: CaseState) -> CaseState:
    case = state["case"]
    fraud = assess_fraud(case)
    case.fraud = fraud  # make it visible to the orchestrator in-memory
    log.info("Fraud %s -> score=%.2f risk=%s", case.case_id,
             fraud.fraud_score, fraud.risk_level.value)
    return {"fraud": fraud, "case": case}


def _orchestrate(state: CaseState) -> CaseState:
    case = state["case"]
    decision = decide(case)
    log.info("Decision %s -> %s (%s)", case.case_id,
             decision.decision.value, decision.justification)
    return {"decision": decision}


def _persist(state: CaseState) -> CaseState:
    case_id = state["case_id"]
    if state.get("fraud"):
        db.set_case_fraud(case_id, state["fraud"])
    decision = state.get("decision")
    if decision:
        db.set_case_decision(case_id, decision)
        status = (CaseStatus.NEEDS_REVIEW
                  if decision.decision == Decision.ESCALATE
                  else CaseStatus.DECIDED)
        db.update_case_status(case_id, status)
    return {}


# ──────────────────────────────────────────────────────────────────────
# Graph assembly
# ──────────────────────────────────────────────────────────────────────
def _has_documents(state: CaseState) -> str:
    case = state.get("case")
    return "fraud_check" if case and case.documents else "empty"


def build_graph():
    g = StateGraph(CaseState)
    g.add_node("aggregate", _aggregate)
    g.add_node("fraud_check", _fraud_check)
    g.add_node("orchestrate", _orchestrate)
    g.add_node("persist", _persist)

    g.set_entry_point("aggregate")
    g.add_conditional_edges("aggregate", _has_documents,
                            {"fraud_check": "fraud_check", "empty": END})
    g.add_edge("fraud_check", "orchestrate")
    g.add_edge("orchestrate", "persist")
    g.add_edge("persist", END)
    return g.compile()


_GRAPH = None


def run_case_decision(case_id: str) -> Optional[Case]:
    """Execute the decision graph for a case and return the updated case."""
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    _GRAPH.invoke({"case_id": case_id})
    return db.get_case(case_id)
