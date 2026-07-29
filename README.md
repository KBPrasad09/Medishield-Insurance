# MediShield — Multi-Agent Document Intake

MediShield Insurance receives about 85,000 document submissions a month: claim forms,
ID scans, discharge summaries, prescriptions, policy amendments. Someone has to read
each one, check the identity, pull the billing codes, decide whether the policy covers
the procedure, and notice when something looks wrong.

This is a system that does that work and hands the hard cases to a person.

**Demo video:** _(link)_

A submission comes in as a set of images. Six agents process it — one classifies each
page, three extract and validate specific things, one looks for fraud across the whole
case, and one makes the call. Cases that are clear get approved or rejected
automatically. Cases that aren't go to a review queue with the evidence attached.

---

## What it does

Upload the five documents for a patient episode. Each page is classified, then routed
to whichever specialist handles that document type. When all pages are in, you run the
decision: the fraud agent looks at the case as a whole, and the orchestrator issues
APPROVE, REJECT, or ESCALATE.

An escalated case lands in the review queue. A reviewer sees the fraud signals, the
extracted fields, the policy clause that was cited, and the document images, then makes
the final call. Their override is recorded alongside the system's original decision, so
the audit trail shows both.

---

## Architecture

```
                       POST /cases/{id}/documents
                                  │
                                  ▼
                          ┌──────────────┐
                          │  Classifier  │  vision LLM, forced tool-use
                          └──────┬───────┘
                                 │  routes on doc_type
             ┌───────────────────┼───────────────────┐
             ▼                   ▼                   ▼
        ┌─────────┐        ┌──────────┐        ┌──────────┐
        │   KYC   │        │  Claims  │───────▶│  Policy  │  RAG over
        └─────────┘        └──────────┘        └──────────┘  plan documents
             │                   │                   │
             └───────────────────┼───────────────────┘
                                 │  POST /cases/{id}/finalize
                                 ▼
                          ┌──────────────┐
                          │    Fraud     │  rules + LLM, case-level
                          └──────┬───────┘
                                 ▼
                          ┌──────────────┐
                          │ Orchestrator │  APPROVE / REJECT / ESCALATE
                          └──────┬───────┘
                                 ▼
                     DECIDED  or  NEEDS_REVIEW → human
```

Per-document agents run in a FastAPI `BackgroundTask` as soon as a file is uploaded.
The case-level part (fraud, then the decision) is a LangGraph `StateGraph`, because it
needs every document present before it can run.

**Backend** — FastAPI, SQLite for cases and documents, Docling for policy-PDF parsing,
Qdrant for the embeddings, LangGraph for the decision state machine, Claude Sonnet for
every vision and reasoning call.

**Frontend** — Next.js with the App Router, TypeScript, Tailwind.

---

## The agents

| Agent | Input | What it produces |
|---|---|---|
| Classifier | one page | `doc_type`, confidence, routing tags |
| KYC | ID document | identity match against the member roster, expiry, tamper advisory |
| Claims | claim form | amount, ICD-10, CPT, NPI, service date + schema validation |
| Policy | CPT codes + plan tier | covered / not covered, cited clause, exclusions |
| Fraud | whole case | fraud score, risk level, the signals that fired |
| Orchestrator | everything above | the decision and why |

Every agent returns a Pydantic model, never a loose dict. The schemas are in
`backend/app/schemas.py` and the frontend mirrors them in `frontend/lib/api.ts`, so a
change to an agent's output shows up as a type error rather than as `undefined` in the
UI at demo time.

Every agent also reports a confidence. The orchestrator uses that: anything below 0.6
on an agent that matters to the decision sends the case to a human.

---

## Decisions

The rules, in the order they're checked:

**ESCALATE** — the submission has no recognizable ID or claim, or the fraud score is
0.3 or higher, or an agent that mattered reported confidence under 0.6.

**REJECT** — identity verification failed, or the claim didn't pass schema validation,
or the policy doesn't cover a billed procedure.

**APPROVE** — none of the above.

Escalation is checked first on purpose. If a case has both a fraud signal and a
rejectable defect, a person should still see it. Auto-denying a case that might be
fraud throws away the investigation.

Full write-up with the validation matrix: [`docs/decision_logic.md`](docs/decision_logic.md).

---

## Design decisions worth explaining

**Rules for what's computable, the model for what isn't.**
Four of the six fraud patterns are arithmetic: a total between $9,000 and $10,000, a
maternity CPT on a non-maternity diagnosis, two claim forms in one case, an ID name
that doesn't match the policyholder. Those are deterministic checks — they fire at
exactly the right threshold every time, which an LLM prompt does not. The two patterns
that need cross-document reasoning about dates go to the model. Mixing them costs
nothing and makes two thirds of the fraud logic testable without an API key.

**Forced tool-use instead of parsing JSON out of prose.**
Every agent call sets `tool_choice` to a specific tool whose input schema is that
agent's output contract. The model can't reply with prose, can't wrap JSON in
markdown, and can't invent an enum value. It also blocks the obvious prompt-injection
route: text inside a scanned document can't change the shape of what comes back.

**The vision model's tamper flag is advisory, not a decision gate.**
This started as an escalation trigger. Measuring it showed the precision isn't there —
it caught real tampered IDs but also flagged clean scans, and no prompt wording fixed
both directions at once. Tampering is a signal about pixels, not about language, and
the right tool is error-level analysis, not a language model. So the flag is surfaced
to the reviewer and recorded, but it doesn't move the decision on its own.

**One misread page doesn't escalate a whole case.**
An early version escalated any case containing an UNKNOWN document. A blurry policy
amendment was enough to hold up a complete, valid claim. Now UNKNOWN only forces
escalation when there's nothing actionable in the case at all — no ID, no claim form.
The confidence gate is scoped the same way, to the documents that actually drive the
decision.

**Coverage problems are not fraud.**
A cosmetic procedure billed against an appendicitis diagnosis is a coverage question,
and the policy agent already answers it. When the fraud model volunteered the same
observation, the case got counted twice and escalated instead of being rejected. The
fraud LLM's free-text notes are now kept for the reviewer at zero weight; only the two
temporal patterns it was asked about can move the score.

---

## Results

Run `python eval/run_eval.py` to reproduce. It runs all 30 patient clusters and the 4
out-of-domain documents through the real pipeline and scores them against the dataset's
ground truth. Output goes to `eval/results.md`.

| Metric | Score |
|---|---|
| Classification accuracy | 96.1% (116/121 documents) |
| Extraction completeness | 96.7% of required claim fields |
| CPT code recall | 100% |
| Policy coverage accuracy | 100% |
| Decision correctness | 76.5% (26/34 cases) |

Classification, extraction and policy retrieval are stable run to run. Decision
correctness is the number that moves, and all eight misses trace back to two signals.

### The eight it gets wrong

**Three tampered IDs — and the tampering isn't in the images.** These were the cases I
spent longest on, tuning the KYC prompt until wording that caught them stopped flagging
clean scans. Nothing worked in both directions, which was the clue.

Reading the generator explains why. `generate_docs.py` has a tamper branch that draws
the expiry date in a larger font and a different colour, but the dispatcher never passes
the argument:

```python
def generate_id_document(c, expired=False, blur=False):
    return _ID_GENERATORS[c["id_type"]](c, expired=expired, blur=blur)
```

`tampered=` appears at no call site, so that branch is dead code. And the three flagged
patients drew `state_id` and `insurance_card` templates, whose functions don't take a
`tampered` parameter at all. Put a flagged card next to a clean one of the same template
and they're identical but for the member's own data.

So these three are undetectable by any method. Prompt wording that seemed to "catch
tampering" was guessing on clean documents and getting credit by coincidence — which is
the strongest possible argument for the design choice above, that an unreliable signal
should inform a reviewer rather than gate a decision. Full write-up, including a
measured ELA experiment and a control:
[`eval/ela_findings.md`](eval/ela_findings.md).

**One missed name swap.** One vowel changes — "Mary" becomes "Mery". Vision models
silently correct the spelling as they read, so the ID comes back looking valid. Matching
on surname plus date of birth recovers some of these, not all. This one is a real
limitation.

**Three fraud false positives**, where the temporal-anomaly pass reads a date
inconsistency into a case that doesn't have one. Also real.

**One missed expiry**, where the ID's EXPIRED mark wasn't picked up.

**C_004** is a fourth data bug: the generator only applies the $9,875 structuring amount
to CMS-1500 claims, and C_004 is a UB-04, so its rendered total is $22,040 and the
signal the case tests for isn't on the page. It passes anyway, via a different signal.

Setting the three impossible cases aside, the achievable ceiling is 31/34 and the system
reaches 26 of those — **84% of what the data allows**. The remaining errors skew toward
review rather than toward wrong automatic decisions, which is the direction you want. A
reviewer spending five minutes on a clean case costs far less than auto-approving a
fraudulent one.

---

## Running it

You need Python 3.12, Node 18+, and an Anthropic API key.

```bash
git clone https://github.com/KBPrasad09/Medishield-Insurance.git
cd Medishield-Insurance

python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt

cp .env.example .env            # then put your key in .env
```

The synthetic documents aren't in the repo — they're 150-odd images and two PDFs, and
they're generated from a fixed seed, so the scripts reproduce them exactly. Run these
once, from the project root:

```bash
python scripts/generate_docs.py           # 30 patient clusters → dataset/
python scripts/generate_unknown.py        # 4 out-of-domain documents
python scripts/generate_gold_policy.py    # Gold plan PDF
python scripts/generate_silver_policy.py  # Silver plan PDF
```

Then build the reference data and the policy index:

```bash
python scripts/build_reference_data.py    # member roster + ground truth
python scripts/ingest_policies.py         # embeds both plan PDFs into Qdrant
```

`ingest_policies.py` parses both plan PDFs with Docling — layout-aware markdown, so
section headings stay headings and the excluded-CPT-range table stays a table, which is
what the chunker splits on and what the Policy agent ends up citing. PyMuPDF is wired as
a fallback so a heavy optional dependency can't block the pipeline; the log states which
parser ran. First run also downloads a ~50 MB embedding model and caches it. Expect 41
chunks (24 Gold, 17 Silver).
What gets generated is described in [`dataset_summary.md`](dataset_summary.md): 151
documents across 30 patient clusters, six of which carry an injected fraud pattern.

Then start both servers. On Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Or by hand, in two terminals:

```bash
uvicorn app.main:app --reload --app-dir backend    # http://127.0.0.1:8000
cd frontend && npm install && npm run dev          # http://localhost:3000
```

API docs are at http://127.0.0.1:8000/docs.

One thing to know: Qdrant's embedded mode takes a single-process lock on
`backend/.qdrant`. The API server and the eval harness can't both hold it, so stop the
server before running the eval.

### Trying it

Upload the five files for one patient to the same case ID, wait for the processing
banner to clear, then click **Run decision**. Windows Explorer's search box finds all
five at once if you search the patient ID inside `dataset/`.

Three clusters that show the different outcomes:

- **C_001** (PT_19116) — date conflict across documents → ESCALATE, goes to the queue
- **C_007** (PT_71993) — cosmetic CPT 17000 → REJECT, with the exclusion clause quoted
- **C_017** — clean case → APPROVE

---

## Layout

```
backend/
  app/
    main.py          FastAPI routes
    graph.py         LangGraph decision state machine
    pipeline.py      per-document routing
    schemas.py       every agent contract
    policy_rag.py    PDF → chunks → Qdrant → retrieval
    member_db.py     identity matching against the roster
    llm.py           Anthropic client, prompt caching, LangSmith
    agents/          classifier, kyc, claims, policy, fraud, orchestrator
frontend/
  app/               dashboard, case detail, review queue
  components/        agent panels, decision card, badges
  lib/api.ts         typed client mirroring the backend schemas
eval/
  run_eval.py        harness + scoring
  results.md         generated
scripts/
  build_reference_data.py
  ingest_policies.py
docs/
  decision_logic.md
```

---

## Cost and observability

Two things keep API spend down. The system prompt and tool schema on every call are
marked with `cache_control`, so repeated calls in a batch bill the static prefix at a
fraction of the price. And the eval harness caches each agent's output by document ID —
`python eval/run_eval.py --replay` re-scores from that cache with no API calls at all,
which is how the decision rules were tuned without paying for a full run each time.

Setting `LANGSMITH_TRACING=true` in `.env` traces every agent call — tokens, latency,
inputs, outputs — with no change to agent code. It's wired in `llm.py`.

---

## Bonus challenges

**LangSmith tracing** — every agent call is traced with tokens, latency and full I/O.
Because all six agents get their client from one factory in `llm.py`, wiring this
touched one file and no agent code. Enable with `LANGSMITH_TRACING=true`.

**Tamper detection (ELA)** — implemented in `backend/app/forensics.py` and reported on
the KYC output as `ela_top_z`. Then measured, with a control, in
[`eval/ela_findings.md`](eval/ela_findings.md): it carries no signal on this dataset,
because the documents are synthetic renders whose error maps are dominated by glyph
edges — and because, as above, the tampering was never drawn. It's surfaced to reviewers
and gates nothing. Reproduce with `python scripts/ela_experiment.py`.

**Prompt caching** (not on the list, but the same category) — system prompts and tool
schemas are marked `cache_control`, and the eval harness caches agent outputs so
decision rules can be re-scored with `--replay` at zero API cost.

---

## What I'd do next

Error-level analysis for tamper detection, so that signal can gate decisions instead of
just informing a reviewer. Streaming agent status over WebSocket rather than polling.
Confidence calibration — the agents report confidence, but I haven't measured whether
a 0.9 is right nine times out of ten, and the 0.6 threshold should be derived from that
rather than taken from the brief.
