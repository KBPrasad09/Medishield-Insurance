"use client";

import { useState } from "react";
import type {
  ClaimsOutput,
  ClassifierOutput,
  FraudOutput,
  KYCOutput,
  PolicyOutput,
} from "@/lib/api";
import { Confidence, RiskBadge } from "./Badges";

function Panel({
  title,
  accent,
  badge,
  children,
  defaultOpen = false,
}: {
  title: string;
  accent: string;
  badge?: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-slate-50"
      >
        <span className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${accent}`} />
          <span className="text-sm font-semibold">{title}</span>
        </span>
        <span className="flex items-center gap-2">
          {badge}
          <span className="text-slate-400">{open ? "−" : "+"}</span>
        </span>
      </button>
      {open && (
        <div className="border-t border-slate-100 px-4 py-3 text-sm">
          {children}
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-1">
      <span className="text-slate-500">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

const Yes = ({ v }: { v: boolean }) => (
  <span className={v ? "text-emerald-600" : "text-slate-400"}>
    {v ? "yes" : "no"}
  </span>
);

const Flags = ({ items }: { items: string[] }) =>
  items.length === 0 ? (
    <span className="text-slate-400">none</span>
  ) : (
    <span className="flex flex-wrap justify-end gap-1">
      {items.map((f) => (
        <span
          key={f}
          className="rounded bg-amber-50 px-1.5 py-0.5 text-xs text-amber-800 ring-1 ring-inset ring-amber-200"
        >
          {f}
        </span>
      ))}
    </span>
  );

export function ClassifierPanel({ data }: { data: ClassifierOutput }) {
  return (
    <Panel
      title="Classifier"
      accent="bg-indigo-500"
      badge={<Confidence value={data.confidence} />}
      defaultOpen
    >
      <Row label="Document type" value={data.doc_type} />
      <Row label="Routing tags" value={<Flags items={data.routing_tags} />} />
      {data.notes && (
        <p className="mt-2 rounded bg-slate-50 p-2 text-xs text-slate-600">
          {data.notes}
        </p>
      )}
    </Panel>
  );
}

export function KYCPanel({ data }: { data: KYCOutput }) {
  return (
    <Panel
      title="KYC / Identity"
      accent="bg-sky-500"
      badge={<Confidence value={data.confidence} />}
    >
      <Row label="KYC passed" value={<Yes v={data.kyc_passed} />} />
      <Row label="Member matched" value={<Yes v={data.member_id_matched} />} />
      <Row label="ID expired" value={<Yes v={data.id_expired} />} />
      <Row
        label="Tamper suspected (advisory)"
        value={<Yes v={data.tamper_suspected} />}
      />
      <Row label="Flags" value={<Flags items={data.flags} />} />
      {data.notes && (
        <p className="mt-2 rounded bg-slate-50 p-2 text-xs text-slate-600">
          {data.notes}
        </p>
      )}
    </Panel>
  );
}

export function ClaimsPanel({ data }: { data: ClaimsOutput }) {
  return (
    <Panel
      title="Claims Extraction"
      accent="bg-violet-500"
      badge={<Confidence value={data.confidence} />}
    >
      <Row
        label="Claim amount"
        value={
          data.claim_amount != null
            ? `$${data.claim_amount.toLocaleString(undefined, {
                minimumFractionDigits: 2,
              })}`
            : "—"
        }
      />
      <Row label="ICD-10" value={data.icd10_codes.join(", ") || "—"} />
      <Row label="CPT" value={data.cpt_codes.join(", ") || "—"} />
      <Row label="Provider NPI" value={data.provider_npi || "—"} />
      <Row label="Service date" value={data.service_date || "—"} />
      <Row label="Schema valid" value={<Yes v={data.schema_valid} />} />
      {data.validation_errors.length > 0 && (
        <Row
          label="Validation errors"
          value={<Flags items={data.validation_errors} />}
        />
      )}
    </Panel>
  );
}

export function PolicyPanel({ data }: { data: PolicyOutput }) {
  return (
    <Panel
      title="Policy Coverage (RAG)"
      accent="bg-teal-500"
      badge={<Confidence value={data.confidence} />}
    >
      <Row label="Covered" value={<Yes v={data.covered} />} />
      <Row
        label="Coverage %"
        value={
          data.coverage_percentage != null ? `${data.coverage_percentage}%` : "—"
        }
      />
      {data.policy_clause && (
        <div className="mt-2 rounded bg-slate-50 p-2 text-xs">
          <div className="mb-1 font-medium text-slate-500">Cited clause</div>
          <div className="text-slate-700">{data.policy_clause}</div>
        </div>
      )}
      {data.exclusions.length > 0 && (
        <div className="mt-2 rounded bg-red-50 p-2 text-xs ring-1 ring-inset ring-red-100">
          <div className="mb-1 font-medium text-red-700">Exclusions</div>
          <ul className="list-inside list-disc text-red-800">
            {data.exclusions.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  );
}

export function FraudPanel({ data }: { data: FraudOutput }) {
  const signals = data.anomalies.filter((a) => !a.startsWith("note:"));
  const notes = data.anomalies.filter((a) => a.startsWith("note:"));
  return (
    <Panel
      title="Fraud Detection — whole case"
      accent="bg-rose-500"
      badge={<RiskBadge risk={data.risk_level} score={data.fraud_score} />}
      defaultOpen={data.fraud_score >= 0.3}
    >
      <p className="mb-2 rounded bg-slate-50 p-2 text-xs text-slate-600">
        Scored across every document in this case, not the one selected — the
        patterns it looks for (duplicate claims, conflicting dates) only exist
        between documents.
      </p>
      <Row label="Fraud score" value={data.fraud_score.toFixed(2)} />
      <Row label="Risk level" value={data.risk_level} />
      {signals.length > 0 && (
        <div className="mt-2 rounded bg-red-50 p-2 text-xs ring-1 ring-inset ring-red-100">
          <div className="mb-1 font-medium text-red-700">Scoring signals</div>
          <ul className="list-inside list-disc text-red-800">
            {signals.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </div>
      )}
      {notes.length > 0 && (
        <details className="mt-2 text-xs text-slate-600">
          <summary className="cursor-pointer text-slate-500">
            Analyst notes ({notes.length}) — informational, not scored
          </summary>
          <ul className="mt-1 list-inside list-disc">
            {notes.map((a, i) => (
              <li key={i}>{a.replace(/^note:\s*/, "")}</li>
            ))}
          </ul>
        </details>
      )}
    </Panel>
  );
}
