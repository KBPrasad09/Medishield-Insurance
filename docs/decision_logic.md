# Decision Logic & Validation

The Orchestrator aggregates every agent's output for a case and issues a final
**APPROVE / REJECT / ESCALATE** decision. Implementation:
`backend/app/agents/orchestrator.py`.

## Decision policy (ordered by precedence)

Escalation is evaluated **first** — tampering, fraud signals, and low-confidence
outputs should always reach a human reviewer rather than be auto-denied, even
when a hard-reject reason also applies.

**1. ESCALATE** (route to human review queue) if ANY of:
- an UNKNOWN / out-of-domain document is present in the case
- `fraud_score >= 0.3`
- a document shows suspected ID tampering
- any agent reported `confidence < 0.6` (unreliable signal)

**2. REJECT** (and not already escalated) if ANY of:
- KYC failed for identity reasons (expired ID, or member not on file)
- a claim failed schema validation (missing required fields)
- a procedure is not covered by the member's policy

**3. APPROVE** otherwise:
- identity verified, claim valid, procedures covered, and low fraud risk

Status mapping: an ESCALATE decision sets the case status to `NEEDS_REVIEW`;
APPROVE / REJECT set it to `DECIDED`.

## Validation matrix

Each row is an automated test case (see the decision test in the eval suite).
All seven pass.

| Case type | Trigger | Expected decision | Rationale |
|---|---|---|---|
| Clean | ID valid, claim valid, covered, no fraud | **APPROVE** | Nothing flagged; low fraud risk |
| Structuring fraud | Claim total $9,875 (just under $10k) | **ESCALATE** | `fraud_score = 0.8` ≥ 0.3 |
| Uncovered procedure | CPT 17000 (cosmetic) | **REJECT** | Policy exclusion (Section 4.1) |
| Expired ID | ID expiry passed / EXPIRED stamp | **REJECT** | KYC failed (identity) |
| Tampered ID | Visual tampering on the ID | **ESCALATE** | Needs human review, not auto-deny |
| Missing fields | Claim missing diagnosis code | **REJECT** | Claim schema invalid |
| Unknown document | Out-of-domain scan | **ESCALATE** | Cannot be auto-processed |

## Mapping to the six injected fraud patterns

The Fraud agent (`backend/app/agents/fraud.py`) raises `fraud_score` for each
pattern, which the Orchestrator turns into ESCALATE:

| Fraud pattern | How it's detected | Signal |
|---|---|---|
| `amount_under_10k` (structuring) | Rule: `9000 <= claim_amount < 10000` | 0.80 |
| `proc_diag_mismatch` | Rule: maternity CPT (59400) with non-pregnancy ICD | 0.85 |
| `duplicate_claim` | Rule: >1 claim form in one case | 0.85 |
| `name_mismatch` | Rule: ID holder not the policyholder (KYC) | 0.80 |
| `readmission_30d` | LLM pass over discharge summary | 0.80 |
| `date_conflict` | LLM pass over prescription vs. service date | 0.80 |
