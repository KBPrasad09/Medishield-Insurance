"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  deleteCase,
  listCases,
  uploadDocument,
  type CaseSummary,
} from "@/lib/api";
import { DecisionBadge, StatusBadge } from "@/components/Badges";

export default function CasesPage() {
  const router = useRouter();
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [newCaseId, setNewCaseId] = useState("");
  const [files, setFiles] = useState<FileList | null>(null);
  const [uploading, setUploading] = useState(false);

  async function refresh() {
    try {
      setCases(await listCases());
      setError(null);
    } catch (e) {
      setError(
        `Cannot reach the API at ${process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"}. Is the backend running?`
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // Poll so cases move through PROCESSING -> DECIDED without a manual refresh.
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newCaseId.trim() || !files?.length) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        await uploadDocument(newCaseId.trim(), file);
      }
      router.push(`/cases/${encodeURIComponent(newCaseId.trim())}`);
    } catch (err) {
      setError(String(err));
      setUploading(false);
    }
  }

  async function handleDelete(caseId: string) {
    if (!confirm(`Delete case ${caseId} and all its documents?`)) return;
    try {
      await deleteCase(caseId);
      setCases((cs) => cs.filter((c) => c.case_id !== caseId));
    } catch (e) {
      setError(String(e));
    }
  }

  const counts = {
    total: cases.length,
    review: cases.filter((c) => c.status === "NEEDS_REVIEW").length,
    decided: cases.filter((c) => c.status === "DECIDED").length,
    processing: cases.filter((c) =>
      ["RECEIVED", "PROCESSING", "CLASSIFIED", "FRAUD_CHECK"].includes(c.status)
    ).length,
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Cases</h1>
        <p className="mt-1 text-sm text-slate-500">
          Each case is one patient episode. Upload its documents, then finalize
          to run fraud detection and the decision graph.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[
          ["Total cases", counts.total, "text-slate-900"],
          ["In progress", counts.processing, "text-blue-600"],
          ["Needs review", counts.review, "text-amber-600"],
          ["Decided", counts.decided, "text-emerald-600"],
        ].map(([label, value, color]) => (
          <div
            key={label as string}
            className="rounded-lg border border-slate-200 bg-white p-4"
          >
            <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
              {label as string}
            </div>
            <div className={`mt-1 text-2xl font-semibold ${color as string}`}>
              {value as number}
            </div>
          </div>
        ))}
      </div>

      <form
        onSubmit={handleCreate}
        className="rounded-lg border border-slate-200 bg-white p-4"
      >
        <div className="mb-3 text-sm font-semibold">New submission</div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="flex-1">
            <span className="mb-1 block text-xs font-medium text-slate-500">
              Case ID
            </span>
            <input
              value={newCaseId}
              onChange={(e) => setNewCaseId(e.target.value)}
              placeholder="C_007"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
            />
          </label>
          <label className="flex-[2]">
            <span className="mb-1 block text-xs font-medium text-slate-500">
              Documents (select all pages for this patient)
            </span>
            <input
              type="file"
              multiple
              accept="image/*,application/pdf"
              onChange={(e) => setFiles(e.target.files)}
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm file:mr-3 file:rounded file:border-0 file:bg-slate-900 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-white"
            />
          </label>
          <button
            type="submit"
            disabled={uploading || !newCaseId.trim() || !files?.length}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            {uploading ? "Uploading…" : "Upload"}
          </button>
        </div>
      </form>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3 font-medium">Case</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Docs</th>
              <th className="px-4 py-3 font-medium">Decision</th>
              <th className="px-4 py-3 font-medium">Updated</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-400">
                  Loading…
                </td>
              </tr>
            )}
            {!loading && cases.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-400">
                  No cases yet — upload documents above to create one.
                </td>
              </tr>
            )}
            {cases.map((c) => (
              <tr key={c.case_id} className="hover:bg-slate-50">
                <td className="px-4 py-3">
                  <Link
                    href={`/cases/${encodeURIComponent(c.case_id)}`}
                    className="font-medium text-slate-900 hover:underline"
                  >
                    {c.case_id}
                  </Link>
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={c.status} />
                </td>
                <td className="px-4 py-3 text-slate-600">
                  {c.document_count}
                </td>
                <td className="px-4 py-3">
                  {c.decision ? (
                    <DecisionBadge decision={c.decision} />
                  ) : (
                    <span className="text-slate-400">—</span>
                  )}
                </td>
                <td className="px-4 py-3 text-xs text-slate-500">
                  {new Date(c.updated_at).toLocaleString()}
                </td>
                <td className="px-4 py-3 text-right">
                  <button
                    onClick={() => handleDelete(c.case_id)}
                    title="Delete case"
                    className="rounded px-2 py-1 text-xs text-slate-400 hover:bg-red-50 hover:text-red-600"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
