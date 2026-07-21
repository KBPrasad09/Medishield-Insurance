# Assignment 2 — 7-Day Build Plan (MediShield Document Intake)

Goal: 1st prize. Differentiators: self-run eval report against metadata.json ground truth,
1–2 high-impact bonuses, tight demo. Judges score correctness, safety, "real product not demo".

## Scoping decisions (defend these in README as design trade-offs)
- Local filesystem storage behind a `StorageBackend` interface — not S3/MinIO. Production path documented.
- SQLite for cases + member DB — not Postgres. Same reason.
- FastAPI BackgroundTasks — not Redis/Celery. Same reason.
- These cost zero rubric points (rubric says "S3 or local", "Redis or Celery") and save ~1.5 days.

## Day 0 (today) — Setup
- [ ] Anthropic API key + $10–15 credit. Put in `.env`, never commit.
- [ ] New repo `medishield-intake`: `backend/` (FastAPI), `frontend/` (Next.js), `dataset/`, `eval/`
- [ ] Run datagen scripts in order: generate_docs → gold_policy → silver_policy → generate_unknown
- [ ] Verify: 155 entries in metadata.json, 2 policy PDFs
- [ ] Seed `members.db` (SQLite) from metadata.json patient clusters — this is your KYC lookup + fraud history table

## KEY INSIGHT (from metadata.json analysis, Day 0)
Ground truth is per CASE CLUSTER (30 patient episodes × ~5 docs), not per document.
metadata.json gives fraud_label + fraud_reason + edge_flags per doc; expected_decision exists
only for the 4 unknowns. Derive cluster-level expected decisions with the brief's rules:
- fraud cluster (6: readmission_30d, date_conflict, proc_diag_mismatch, amount_under_10k,
  duplicate_claim, name_mismatch) → ESCALATE
- expired_id / uncovered_procedure / missing_fields → REJECT
- tampered_id → ESCALATE
- expiring_soon_id / clean → APPROVE
- unknown docs → ESCALATE
Architecture consequence: a Case aggregates all docs of one patient episode; the Orchestrator
decides per case, not per doc. eval/derive_ground_truth.py builds the 30-case answer key first.

## Day 1 — Ingestion API + case store
- [ ] POST /cases (multipart upload, JPEG/PNG/PDF/TIFF) → case_id (uuid), store file, row in SQLite
- [ ] GET /cases, GET /cases/{id} — status: RECEIVED→CLASSIFIED→PROCESSING→DECIDED
- [ ] BackgroundTask kicks off pipeline stub
- [ ] Pydantic models for every agent's output schema NOW (typed interfaces = 10% of rubric)

## Day 2 — Classifier + OCR preprocessor
- [ ] Classifier: Claude vision → `{doc_type, confidence, routing_tags}` via tool-use/structured output
- [ ] Confidence < 0.6 or UNKNOWN → human review queue
- [ ] OCR preprocessor: Claude vision structured extraction → `{fields, raw_text}` (skip Tesseract; vision LLM covers it — document why)
- [ ] Test on 20 mixed docs incl. the 4 unknowns. Target ≥90% before moving on.

## Day 3 — KYC + Claims agents
- [ ] KYC: member lookup vs members.db, expiry check, tamper flags → `{kyc_passed, flags, confidence}`
- [ ] Claims: extract amount, ICD-10, CPT, NPI, service date; schema validation → `{extracted_fields, schema_valid, validation_errors}`
- [ ] Test against edge cases: 5 expired IDs, 3 tampered, 4 incomplete claims

## Day 4 — Policy RAG + Fraud agent
- [ ] Docling ingest of both policy PDFs → chunk by the 10 bookmarked sections → ChromaDB
- [ ] Query by CPT codes → `{covered, coverage_percentage, policy_clause, exclusions}`
- [ ] Fraud: query claim history from SQLite; rules for the 6 fraud patterns (duplicate, date conflict,
      proc-diag mismatch, readmission, structuring, name mismatch) + LLM anomaly reasoning → `{fraud_score, anomalies, risk_level}`

## Day 5 — LangGraph orchestration + EVAL
- [ ] StateGraph: RECEIVED → CLASSIFIED → [parallel KYC+Claims+Policy] → FRAUD → ORCHESTRATOR
- [ ] Conditional edges by doc_type; orchestrator decision rules exactly per brief (APPROVE/REJECT/ESCALATE thresholds)
- [ ] eval/run_eval.py: run all 155 docs, score vs metadata.json → classification acc, extraction completeness,
      decision correctness. Output eval/results.md with confusion matrix.
- [ ] Iterate prompts until decision correctness ≥ 80% (pass bar is 60; winners clear 80)

## Day 6 — UI + one bonus
- [ ] Next.js: dashboard (status badges), case detail (image viewer + collapsible agent panels),
      decision panel, human review queue with override, audit log
- [ ] Bonus #1: WebSocket streaming of per-agent status ("KYC Agent ✅") — biggest demo wow
- [ ] If time — Bonus #2: confidence calibration plot from Day-5 eval data (nearly free, looks rigorous)

## Day 7 — Package + demo
- [ ] README: architecture diagram (actual components/models), setup, .env.example, design decisions,
      known limitations, EVAL RESULTS TABLE, demo video link
- [ ] Demo video 5–10 min: upload doc → live agent stream → decision → review queue override → eval results
- [ ] Repo public, no secrets (check git history), LinkedIn post → LMS submission

## Demo script skeleton (record Day 7)
1. 30s problem framing (85k docs/mo, $18.4M cost)
2. Architecture diagram walkthrough (1 min)
3. Upload a clean claim → watch agents stream → APPROVE (2 min)
4. Upload a tampered/fraud doc → ESCALATE → human override in review queue (2 min)
5. Eval results: accuracy table vs 155-doc ground truth (1 min)
6. Design trade-offs + production path (1 min)
