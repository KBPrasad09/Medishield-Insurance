"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  getCase,
  imageUrl,
  listCases,
  type CaseModel,
  type CaseSummary,
} from "@/lib/api";
import DecisionCard from "@/components/DecisionCard";
import { FraudPanel } from "@/components/AgentPanels";

/**
 * Human review queue — the cases the orchestrator escalated.
 *
 * A reviewer picks a case, sees the evidence the agents produced, and issues the
 * final call. This is the human-in-the-loop half of the system: automation
 * decides the clear cases, people decide the ambiguous ones.
 */
export default function ReviewQueuePage() {
  const [queue, setQueue] = useState<CaseSummary[]>([]);
  const [active, setActive] = useState<CaseModel | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const all = await listCases();
      setQueue(all.filter((c) => c.status === "NEEDS_REVIEW"));
      setError(null);
    } catch (e) {
      setError(
        "Cannot reach the API. Start the backend with: uvicorn app.main:app --reload --app-dir backend"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function open(caseId: string) {
    try {
      setActive(await getCase(caseId));
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleChange(c: CaseModel) {
    setActive(c);
    await refresh(); // the case leaves the queue once a reviewer decides
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Review queue</h1>
        <p className="mt-1 text-sm text-slate-500">
          Cases the system escalated — fraud signals, out-of-domain submissions,
          or low-confidence extractions. A reviewer makes the final call.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-500">
              Awaiting review
            </h2>
            <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800 ring-1 ring-inset ring-amber-200">
              {queue.length}
            </span>
          </div>

          {loading && <p className="text-sm text-slate-400">Loading…</p>}
          {!loading && queue.length === 0 && (
            <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-400">
              Queue is clear — nothing needs human review.
            </p>
          )}

          {queue.map((c) => (
            <button
              key={c.case_id}
              onClick={() => open(c.case_id)}
              className={`w-full rounded-lg border p-3 text-left text-sm hover:bg-slate-50 ${
                active?.case_id === c.case_id
                  ? "border-slate-900 bg-white"
                  : "border-slate-200 bg-white"
              }`}
            >
              <div className="font-medium">{c.case_id}</div>
              <div className="mt-0.5 text-xs text-slate-500">
                {c.document_count} documents ·{" "}
                {new Date(c.updated_at).toLocaleString()}
              </div>
            </button>
          ))}
        </div>

        <div>
          {!active && (
            <div className="rounded-lg border border-dashed border-slate-300 p-10 text-center text-sm text-slate-400">
              Select a case to review its evidence.
            </div>
          )}

          {active && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">{active.case_id}</h2>
                <Link
                  href={`/cases/${encodeURIComponent(active.case_id)}`}
                  className="text-sm text-slate-500 hover:underline"
                >
                  Open full case →
                </Link>
              </div>

              {active.decision && (
                <DecisionCard
                  caseId={active.case_id}
                  data={active}
                  onChange={handleChange}
                />
              )}

              {active.fraud && <FraudPanel data={active.fraud} />}

              <div>
                <h3 className="mb-2 text-sm font-semibold text-slate-500">
                  Documents
                </h3>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {active.documents.map((d) => (
                    <figure
                      key={d.doc_id}
                      className="overflow-hidden rounded-lg border border-slate-200 bg-white"
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={imageUrl(d.doc_id)}
                        alt={d.filename}
                        className="h-36 w-full bg-slate-50 object-contain"
                      />
                      <figcaption className="border-t border-slate-100 px-2 py-1 text-[11px] text-slate-500">
                        {d.classification?.doc_type.replace(/_/g, " ") ?? "…"}
                      </figcaption>
                    </figure>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
