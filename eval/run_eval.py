"""
End-to-end evaluation harness.

Runs the FULL agent pipeline over every synthetic document and scores the system
against the deterministic ground truth (dataset/ground_truth.json + metadata.json):

  - Classification accuracy   (rubric 20%)
  - Extraction completeness    (rubric 20%)  — claim field coverage + CPT recall
  - Policy coverage accuracy   (rubric 15% proxy)
  - Decision correctness       (rubric 25%)  — APPROVE / REJECT / ESCALATE

For each of the 30 patient clusters it classifies each document, runs the
relevant specialist (KYC / Claims / Policy), assembles the Case, runs the Fraud
agent and the Orchestrator, and compares the final decision to the expected one.
The 4 out-of-distribution documents are scored as single-document ESCALATE cases.

Writes eval/results.md (tables + confusion matrices) and prints a summary.

Prereqs: reference.db + .qdrant built, .env with ANTHROPIC_API_KEY, and the
API server STOPPED (Qdrant local mode holds a single-process lock).

Run from repo root:
    python eval/run_eval.py            # full run (~150 LLM calls)
    python eval/run_eval.py --limit 3  # smoke test: first 3 clusters
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

from app.agents.classifier import classify_document  # noqa: E402
from app.agents.claims import run_claims  # noqa: E402
from app.agents.fraud import assess_fraud  # noqa: E402
from app.agents.kyc import run_kyc  # noqa: E402
from app.agents.orchestrator import decide  # noqa: E402
from app.agents.policy import run_policy  # noqa: E402
from app.schemas import (  # noqa: E402
    Case, ClaimsOutput, ClassifierOutput, Document, DocType,
    FraudOutput, KYCOutput, PolicyOutput,
)

DATASET = REPO / "dataset"
META_PATH = DATASET / "metadata.json"
GT_PATH = DATASET / "ground_truth.json"
CACHE_PATH = REPO / "eval" / "agent_cache.json"

# Per-document agent outputs are cached by doc_id so decision-RULE changes can be
# re-scored for free (no LLM calls). Delete agent_cache.json to force a fresh run.
_CACHE: dict = {}

CATEGORY_TO_DOCTYPE = {
    "claim_forms": DocType.CLAIM_FORM,
    "id_documents": DocType.ID_DOCUMENT,
    "discharge_summaries": DocType.DISCHARGE_SUMMARY,
    "prescriptions": DocType.PRESCRIPTION,
    "policy_amendments": DocType.POLICY_AMENDMENT,
    "unknown": DocType.UNKNOWN,
}
REQUIRED_CLAIM_FIELDS = ["claim_amount", "icd10_codes", "cpt_codes",
                         "provider_npi", "service_date"]


def _load_cache(refresh: bool) -> None:
    global _CACHE
    if refresh or not CACHE_PATH.exists():
        _CACHE = {}
    else:
        _CACHE = json.loads(CACHE_PATH.read_text())


def _save_cache() -> None:
    CACHE_PATH.write_text(json.dumps(_CACHE), encoding="utf-8")


def _cached(key: str, cls, fn, replay: bool):
    """Return cls(**cached) if present; else call fn(), cache its dump, return it."""
    if key in _CACHE:
        return cls(**_CACHE[key])
    if replay:
        raise RuntimeError(f"cache miss for {key} (replay mode; run without --replay first)")
    out = fn()
    _CACHE[key] = out.model_dump(mode="json")
    return out


def expected_decision(gt_cluster: dict) -> str:
    if gt_cluster.get("is_fraud"):
        return "ESCALATE"
    flags = gt_cluster.get("edge_flags", [])
    if "tampered_id" in flags:
        return "ESCALATE"
    if "expired_id" in flags or "uncovered_procedure" in flags or "missing_fields" in flags:
        return "REJECT"
    return "APPROVE"  # clean or expiring_soon_id


def plan_tier(policy_number: str) -> str:
    return "SILVER" if "SLV" in (policy_number or "").upper() else "GOLD"


def real_path(file_path: str) -> str:
    """metadata stores Windows absolute paths; map to this repo's dataset dir."""
    name = Path(file_path.replace("\\", "/")).name
    category = Path(file_path.replace("\\", "/")).parent.name
    return str(DATASET / category / name)


# ──────────────────────────────────────────────────────────────────────
def evaluate(limit: int | None = None, only: set[str] | None = None,
             replay: bool = False) -> dict:
    meta = json.loads(META_PATH.read_text())
    gt = {c["cluster_id"]: c for c in json.loads(GT_PATH.read_text())}

    by_cluster: dict[str, list[dict]] = defaultdict(list)
    unknowns: list[dict] = []
    for m in meta:
        if m["category"] == "unknown":
            unknowns.append(m)
        else:
            by_cluster[m["case_cluster_id"]].append(m)

    cluster_ids = sorted(by_cluster)
    if only:
        cluster_ids = [c for c in cluster_ids if c in only]
        unknowns = []  # skip unknowns when targeting specific clusters
    elif limit:
        cluster_ids = cluster_ids[:limit]

    results = {
        "cls_total": 0, "cls_correct": 0,
        "cls_confusion": Counter(),          # (expected, predicted) -> n
        "extract_field_scores": [],          # per-claim completeness 0..1
        "cpt_recall": [],                    # per-claim CPT recall 0..1
        "policy_total": 0, "policy_correct": 0,
        "dec_total": 0, "dec_correct": 0,
        "dec_confusion": Counter(),          # (expected, predicted) -> n
        "rows": [],                          # per-cluster detail
    }

    for cid in cluster_ids:
        try:
            _evaluate_cluster(cid, by_cluster[cid], gt[cid], results, replay)
        except Exception as exc:  # noqa: BLE001 - never abort a long run on one case
            print(f"  {cid}: ERROR {type(exc).__name__}: {exc}")
            results["rows"].append({"cluster": cid, "expected": "?", "got": "ERROR",
                                    "fraud": 0, "flags": [], "fraud_reason": str(exc)[:60]})

    # ---- unknown documents (single-doc ESCALATE cases) -----------------
    for um in (unknowns if not limit else unknowns[:1]):
        try:
            _evaluate_unknown(um, results, replay)
        except Exception as exc:  # noqa: BLE001
            print(f"  {um['doc_id']}: ERROR {type(exc).__name__}: {exc}")

    return results


def _evaluate_cluster(cid, docs_meta, gtc, results, replay=False):
    tier = plan_tier(gtc.get("policy", ""))
    documents: list[Document] = []
    claim_extract = None

    for dm in docs_meta:
        path = real_path(dm["file_path"])
        did = dm["doc_id"]
        expected_dt = CATEGORY_TO_DOCTYPE[dm["category"]]
        cls = _cached(f"cls:{did}", ClassifierOutput,
                      lambda p=path: classify_document(p), replay)
        results["cls_total"] += 1
        results["cls_correct"] += int(cls.doc_type == expected_dt)
        results["cls_confusion"][(expected_dt.value, cls.doc_type.value)] += 1

        doc = Document(doc_id=did, case_id=cid, filename=Path(path).name,
                       stored_path=path, classification=cls)

        if cls.doc_type == DocType.ID_DOCUMENT:
            doc.kyc = _cached(f"kyc:{did}", KYCOutput, lambda p=path: run_kyc(p), replay)
        elif cls.doc_type == DocType.CLAIM_FORM:
            doc.claims = _cached(f"clm:{did}", ClaimsOutput,
                                 lambda p=path: run_claims(p), replay)
            claim_extract = doc.claims
            if doc.claims.cpt_codes:
                diag = doc.claims.icd10_codes[0] if doc.claims.icd10_codes else None
                cpts = doc.claims.cpt_codes
                doc.policy = _cached(f"pol:{did}", PolicyOutput,
                                     lambda: run_policy(cpts, tier, diag), replay)
        documents.append(doc)

    # ---- extraction scoring (on the primary claim) --------------------
    if claim_extract:
        present = sum(int(bool(getattr(claim_extract, f))) for f in REQUIRED_CLAIM_FIELDS)
        results["extract_field_scores"].append(present / len(REQUIRED_CLAIM_FIELDS))
        gt_cpts = {c["code"] for c in gtc.get("cpt_list", [])}
        if gt_cpts:
            hit = len(gt_cpts & set(claim_extract.cpt_codes))
            results["cpt_recall"].append(hit / len(gt_cpts))

    # ---- policy coverage accuracy -------------------------------------
    expected_covered = "uncovered_procedure" not in gtc.get("edge_flags", [])
    pol_docs = [d for d in documents if d.policy]
    if pol_docs:
        got_covered = all(d.policy.covered for d in pol_docs)
        results["policy_total"] += 1
        results["policy_correct"] += int(got_covered == expected_covered)

    # ---- fraud + decision ---------------------------------------------
    case = Case(case_id=cid, documents=documents)
    case.fraud = _cached(f"frd:{cid}", FraudOutput, lambda: assess_fraud(case), replay)
    decision = decide(case)
    exp = expected_decision(gtc)
    got = decision.decision.value
    results["dec_total"] += 1
    results["dec_correct"] += int(got == exp)
    results["dec_confusion"][(exp, got)] += 1
    # capture KYC flags across ID docs for diagnosis
    kyc_flags = sorted({f for d in documents if d.kyc for f in d.kyc.flags})
    results["rows"].append({
        "cluster": cid, "expected": exp, "got": got,
        "fraud": case.fraud.fraud_score,
        "flags": gtc.get("edge_flags", []),
        "fraud_reason": gtc.get("fraud_reason"),
        "justification": decision.justification,
        "kyc_flags": kyc_flags,
    })
    mark = "OK" if got == exp else "XX"
    extra = "" if got == exp else f"  | {decision.justification}  kyc={kyc_flags}"
    print(f"  {cid}: decision {got:9} (expected {exp:9}) "
          f"{mark}  fraud={case.fraud.fraud_score}{extra}")


def _evaluate_unknown(um, results, replay=False):
    path = real_path(um["file_path"])
    did = um["doc_id"]
    cls = _cached(f"cls:{did}", ClassifierOutput, lambda: classify_document(path), replay)
    results["cls_total"] += 1
    results["cls_correct"] += int(cls.doc_type == DocType.UNKNOWN)
    results["cls_confusion"][("UNKNOWN", cls.doc_type.value)] += 1
    doc = Document(doc_id=did, case_id=did, filename=Path(path).name,
                   stored_path=path, classification=cls)
    case = Case(case_id=did, documents=[doc])
    case.fraud = FraudOutput(fraud_score=0.0, confidence=0.8)
    decision = decide(case)
    exp, got = "ESCALATE", decision.decision.value
    results["dec_total"] += 1
    results["dec_correct"] += int(got == exp)
    results["dec_confusion"][(exp, got)] += 1
    results["rows"].append({"cluster": um["doc_id"], "expected": exp, "got": got,
                            "fraud": case.fraud.fraud_score, "flags": ["unknown"],
                            "fraud_reason": None})
    print(f"  {um['doc_id']}: decision {got:9} (expected {exp:9}) "
          f"{'OK' if got == exp else 'XX'}")


def pct(n, d):
    return f"{100.0 * n / d:.1f}%" if d else "n/a"


def write_report(r: dict) -> None:
    cls_acc = r["cls_correct"] / r["cls_total"] if r["cls_total"] else 0
    dec_acc = r["dec_correct"] / r["dec_total"] if r["dec_total"] else 0
    ext = sum(r["extract_field_scores"]) / len(r["extract_field_scores"]) if r["extract_field_scores"] else 0
    cpt = sum(r["cpt_recall"]) / len(r["cpt_recall"]) if r["cpt_recall"] else 0
    pol = r["policy_correct"] / r["policy_total"] if r["policy_total"] else 0

    lines = ["# MediShield — Evaluation Results", ""]
    lines += [f"_Generated {time.strftime('%Y-%m-%d %H:%M')}_", ""]
    lines += ["## Summary", "",
              "| Metric | Rubric weight | Score |",
              "|---|---|---|",
              f"| Classification accuracy | 20% | **{pct(r['cls_correct'], r['cls_total'])}** ({r['cls_correct']}/{r['cls_total']}) |",
              f"| Extraction completeness | 20% | **{ext*100:.1f}%** (claim fields present) |",
              f"| — CPT code recall | — | {cpt*100:.1f}% |",
              f"| Policy coverage accuracy | 15% | **{pct(r['policy_correct'], r['policy_total'])}** |",
              f"| Decision correctness | 25% | **{pct(r['dec_correct'], r['dec_total'])}** ({r['dec_correct']}/{r['dec_total']}) |",
              ""]

    # Decision confusion matrix
    labels = ["APPROVE", "REJECT", "ESCALATE"]
    lines += ["## Decision confusion matrix", "",
              "Rows = expected, columns = predicted.", "",
              "| expected ↓ / got → | " + " | ".join(labels) + " |",
              "|---|" + "|".join(["---"] * len(labels)) + "|"]
    for exp in labels:
        row = [str(r["dec_confusion"].get((exp, got), 0)) for got in labels]
        lines.append(f"| {exp} | " + " | ".join(row) + " |")
    lines.append("")

    # Classification confusion (compact: only nonzero)
    lines += ["## Classification confusion (nonzero cells)", "",
              "| expected | predicted | count |", "|---|---|---|"]
    for (exp, got), n in sorted(r["cls_confusion"].items()):
        flag = "" if exp == got else "  ⟵ miss"
        lines.append(f"| {exp} | {got}{flag} | {n} |")
    lines.append("")

    # Per-cluster decisions
    lines += ["## Per-case decisions", "",
              "| case | expected | got | ok | fraud | notes |", "|---|---|---|---|---|---|"]
    for row in r["rows"]:
        ok = "✅" if row["expected"] == row["got"] else "❌"
        note = row["fraud_reason"] or ", ".join(row["flags"]) or "clean"
        lines.append(f"| {row['cluster']} | {row['expected']} | {row['got']} | {ok} | "
                     f"{row['fraud']} | {note} |")
    lines.append("")

    out = REPO / "eval" / "results.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {out}")
    print(f"Classification {pct(r['cls_correct'], r['cls_total'])} | "
          f"Extraction {ext*100:.1f}% | Policy {pct(r['policy_correct'], r['policy_total'])} | "
          f"Decision {pct(r['dec_correct'], r['dec_total'])}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="only run the first N clusters (smoke test)")
    ap.add_argument("--clusters", type=str, default=None,
                    help="comma-separated cluster ids to run, e.g. C_006,C_010,C_016")
    ap.add_argument("--replay", action="store_true",
                    help="re-score from cached agent outputs (no LLM calls) — "
                         "for tuning decision rules for free")
    ap.add_argument("--refresh", action="store_true",
                    help="ignore the cache and call the agents fresh")
    args = ap.parse_args()

    only = {c.strip() for c in args.clusters.split(",")} if args.clusters else None
    _load_cache(refresh=args.refresh)
    t0 = time.time()
    mode = ("replay" if args.replay else "clusters %s" % args.clusters if only
            else "limit %d" % args.limit if args.limit else "full")
    print(f"Running eval ({mode}) ...")
    results = evaluate(limit=args.limit, only=only, replay=args.replay)
    if not args.replay:
        _save_cache()
    write_report(results)
    print(f"Done in {time.time() - t0:.0f}s")
