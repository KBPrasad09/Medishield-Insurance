import type { CaseStatus, DecisionValue, RiskLevel } from "@/lib/api";

const base =
  "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset";

export function StatusBadge({ status }: { status: CaseStatus }) {
  const styles: Record<string, string> = {
    RECEIVED: "bg-slate-50 text-slate-700 ring-slate-200",
    PROCESSING: "bg-blue-50 text-blue-700 ring-blue-200",
    CLASSIFIED: "bg-blue-50 text-blue-700 ring-blue-200",
    FRAUD_CHECK: "bg-amber-50 text-amber-800 ring-amber-200",
    AGGREGATED: "bg-blue-50 text-blue-700 ring-blue-200",
    DECIDED: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    NEEDS_REVIEW: "bg-amber-50 text-amber-800 ring-amber-200",
    FAILED: "bg-red-50 text-red-700 ring-red-200",
  };
  return (
    <span className={`${base} ${styles[status] ?? styles.RECEIVED}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

export function DecisionBadge({ decision }: { decision: DecisionValue }) {
  const styles: Record<DecisionValue, string> = {
    APPROVE: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    REJECT: "bg-red-50 text-red-700 ring-red-200",
    ESCALATE: "bg-amber-50 text-amber-800 ring-amber-200",
  };
  return <span className={`${base} ${styles[decision]}`}>{decision}</span>;
}

export function RiskBadge({ risk, score }: { risk: RiskLevel; score: number }) {
  const styles: Record<RiskLevel, string> = {
    LOW: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    MEDIUM: "bg-amber-50 text-amber-800 ring-amber-200",
    HIGH: "bg-red-50 text-red-700 ring-red-200",
  };
  return (
    <span className={`${base} ${styles[risk]}`}>
      {risk} · {score.toFixed(2)}
    </span>
  );
}

/** Confidence pill — greys out below the 0.6 escalation threshold. */
export function Confidence({ value }: { value: number }) {
  const low = value < 0.6;
  return (
    <span
      className={`${base} ${
        low
          ? "bg-amber-50 text-amber-800 ring-amber-200"
          : "bg-slate-50 text-slate-600 ring-slate-200"
      }`}
      title={low ? "Below 0.6 — triggers escalation" : "Confidence"}
    >
      conf {value.toFixed(2)}
    </span>
  );
}
