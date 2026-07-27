"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  finalizeCase,
  getCase,
  imageUrl,
  uploadDocument,
  type CaseModel,
  type DocumentModel,
} from "@/lib/api";
import {
  ClaimsPanel,
  ClassifierPanel,
  FraudPanel,
  KYCPanel,
  PolicyPanel,
} from "@/components/AgentPanels";
import { DecisionBadge, StatusBadge } from "@/components/Badges";
import DecisionCard from "@/components/DecisionCard";

export default function CaseDetailPage({ params }: { params: { id: string } }) {
  const caseId = decodeURIComponent(params.id);
  const [data, setData] = useState<CaseModel | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const c = await getCase(caseId);
      setData(c);
      setSelected((s) => s ?? c.documents[0]?.doc_id ?? null);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, [caseId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // While documents are still being processed, poll until every one has a
  // classification (agents run asynchronously in a BackgroundTask).
  useEffect(() => {
    if (!data) return;
    const pending = data.documents.some((d) => !d.classification);
    if (!pending) return;
    const t = setTimeout(refresh, 3000);
    return () => clearTimeout(t);
  }, [data, refresh]);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    if (!e.target.files?.length) return;
    setBusy(true);
    try {
      for (const f of Array.from(e.target.files)) await uploadDocument(caseId, f);
      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleFinalize() {
    setBusy(true);
    try {
      setData(await finalizeCase(caseId));
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  if (error && !data)
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        {error}
      </div>
    );
  if (!data) return <div className="text-slate-400">Loading…</div>;

  const doc: DocumentModel | undefined =
    data.documents.find((d) => d.doc_id === selected) ?? data.documents[0];
  const processing = data.documents.some((d) => !d.classification);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link href="/" className="text-sm text-slate-500 hover:underline">
            ← All cases
          </Link>
          <h1 className="mt-1 flex items-center gap-3 text-2xl font-semibold">
            {data.case_id}
            <StatusBadge status={data.status} />
            {data.decision && <DecisionBadge decision={data.decision.decision} />}
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <label className="cursor-pointer rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium hover:bg-slate-50">
            Add documents
            <input
              type="file"
              multiple
              accept="image/*,application/pdf"
              onChange={handleUpload}
              className="hidden"
            />
          </label>
          <button
            onClick={handleFinalize}
            disabled={busy || processing || data.documents.length === 0}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
            title={
              processing ? "Wait for document processing to finish" : undefined
            }
          >
            {busy ? "Running…" : "Run decision"}
          </button>
        </div>
      </div>

      {processing && (
        <div className="flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
          <span className="h-2 w-2 animate-pulse rounded-full bg-blue-500" />
          Agents are processing documents… this page updates automatically.
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {data.decision && <DecisionCard caseId={caseId} data={data} onChange={setData} />}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Document viewer */}
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {data.documents.map((d) => (
              <button
                key={d.doc_id}
                onClick={() => setSelected(d.doc_id)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium ring-1 ring-inset ${
                  d.doc_id === (doc?.doc_id ?? "")
                    ? "bg-slate-900 text-white ring-slate-900"
                    : "bg-white text-slate-600 ring-slate-200 hover:bg-slate-50"
                }`}
              >
                {d.classification?.doc_type.replace(/_/g, " ") ?? "processing…"}
              </button>
            ))}
          </div>
          {doc && (
            <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
              <div className="border-b border-slate-100 px-4 py-2 text-xs text-slate-500">
                {doc.filename}
              </div>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={imageUrl(doc.doc_id)}
                alt={doc.filename}
                className="max-h-[560px] w-full bg-slate-50 object-contain"
              />
            </div>
          )}
        </div>

        {/* Agent outputs for the selected document + case-level fraud */}
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-slate-500">
            Agent outputs
          </h2>
          {doc?.classification && <ClassifierPanel data={doc.classification} />}
          {doc?.kyc && <KYCPanel data={doc.kyc} />}
          {doc?.claims && <ClaimsPanel data={doc.claims} />}
          {doc?.policy && <PolicyPanel data={doc.policy} />}
          {data.fraud && <FraudPanel data={data.fraud} />}
          {!data.fraud && (
            <p className="rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-400">
              Fraud detection and the final decision run when you click{" "}
              <strong>Run decision</strong> — they need every document in the
              case together.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
