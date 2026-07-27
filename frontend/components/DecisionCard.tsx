"use client";

import { useState } from "react";
import {
  overrideCase,
  type CaseModel,
  type DecisionValue,
} from "@/lib/api";
import { DecisionBadge } from "./Badges";

/**
 * Final decision + the human-in-the-loop override control.
 *
 * The automated decision is never destroyed: overriding stores the original in
 * `original_decision` and stamps who changed it and why, so the case keeps a
 * complete audit trail.
 */
export default function DecisionCard({
  caseId,
  data,
  onChange,
}: {
  caseId: string;
  data: CaseModel;
  onChange: (c: CaseModel) => void;
}) {
  const d = data.decision!;
  const [open, setOpen] = useState(false);
  const [reviewer, setReviewer] = useState("reviewer");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(decision: DecisionValue) {
    setBusy(true);
    setErr(null);
    try {
      onChange(await overrideCase(caseId, decision, reviewer, reason));
      setOpen(false);
      setReason("");
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  const tone =
    d.decision === "APPROVE"
      ? "border-emerald-200 bg-emerald-50"
      : d.decision === "REJECT"
      ? "border-red-200 bg-red-50"
      : "border-amber-200 bg-amber-50";

  return (
    <div className={`rounded-lg border p-4 ${tone}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <DecisionBadge decision={d.decision} />
            <span className="text-xs text-slate-600">
              confidence {d.confidence.toFixed(2)}
            </span>
          </div>
          <p className="mt-2 text-sm text-slate-800">{d.justification}</p>

          {d.overridden_by && (
            <p className="mt-2 rounded bg-white/70 px-2 py-1 text-xs text-slate-600">
              Overridden by <strong>{d.overridden_by}</strong>
              {d.original_decision && (
                <> (system decided {d.original_decision})</>
              )}
              {d.override_reason && <> — “{d.override_reason}”</>}
              {d.overridden_at && (
                <> · {new Date(d.overridden_at).toLocaleString()}</>
              )}
            </p>
          )}
        </div>

        <button
          onClick={() => setOpen(!open)}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium hover:bg-slate-50"
        >
          {open ? "Cancel" : "Reviewer override"}
        </button>
      </div>

      {Object.keys(d.agent_summaries).length > 0 && (
        <details className="mt-3 text-xs">
          <summary className="cursor-pointer text-slate-600">
            Why — agent evidence trail
          </summary>
          <dl className="mt-2 space-y-1 rounded bg-white/70 p-2">
            {Object.entries(d.agent_summaries).map(([k, v]) => (
              <div key={k} className="flex gap-2">
                <dt className="shrink-0 font-medium text-slate-500">{k}</dt>
                <dd className="text-slate-700">{v}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}

      {open && (
        <div className="mt-3 space-y-2 rounded-md bg-white p-3">
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              value={reviewer}
              onChange={(e) => setReviewer(e.target.value)}
              placeholder="Reviewer name"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm sm:w-48"
            />
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Reason for override (recorded in the audit trail)"
              className="w-full flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <div className="flex gap-2">
            {(["APPROVE", "REJECT", "ESCALATE"] as DecisionValue[]).map((v) => (
              <button
                key={v}
                onClick={() => submit(v)}
                disabled={busy}
                className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40"
              >
                {v}
              </button>
            ))}
          </div>
          {err && <p className="text-xs text-red-600">{err}</p>}
        </div>
      )}
    </div>
  );
}
