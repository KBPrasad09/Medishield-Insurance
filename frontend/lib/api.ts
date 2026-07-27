/**
 * Typed client for the MediShield backend.
 *
 * These types mirror backend/app/schemas.py one-for-one. Keeping the contract
 * explicit on both sides means a change to an agent's output shape shows up as
 * a TypeScript error here rather than as a silent `undefined` in the UI.
 */

export const API =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export type DocType =
  | "CLAIM_FORM"
  | "ID_DOCUMENT"
  | "DISCHARGE_SUMMARY"
  | "PRESCRIPTION"
  | "POLICY_AMENDMENT"
  | "UNKNOWN";

export type CaseStatus =
  | "RECEIVED"
  | "CLASSIFIED"
  | "PROCESSING"
  | "FRAUD_CHECK"
  | "AGGREGATED"
  | "DECIDED"
  | "NEEDS_REVIEW"
  | "FAILED";

export type DecisionValue = "APPROVE" | "REJECT" | "ESCALATE";
export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";

interface AgentBase {
  confidence: number;
  flags: string[];
  notes?: string | null;
}

export interface ClassifierOutput extends AgentBase {
  doc_type: DocType;
  routing_tags: string[];
}

export interface KYCOutput extends AgentBase {
  kyc_passed: boolean;
  member_id_matched: boolean;
  id_expired: boolean;
  tamper_suspected: boolean;
}

export interface ClaimsOutput extends AgentBase {
  claim_amount?: number | null;
  icd10_codes: string[];
  cpt_codes: string[];
  provider_npi?: string | null;
  service_date?: string | null;
  member_policy_number?: string | null;
  schema_valid: boolean;
  validation_errors: string[];
}

export interface PolicyOutput extends AgentBase {
  covered: boolean;
  coverage_percentage?: number | null;
  policy_clause?: string | null;
  exclusions: string[];
}

export interface FraudOutput extends AgentBase {
  fraud_score: number;
  risk_level: RiskLevel;
  anomalies: string[];
}

export interface OrchestratorDecision {
  decision: DecisionValue;
  confidence: number;
  justification: string;
  agent_summaries: Record<string, string>;
  overridden_by?: string | null;
  override_reason?: string | null;
  original_decision?: DecisionValue | null;
  overridden_at?: string | null;
}

export interface DocumentModel {
  doc_id: string;
  case_id: string;
  filename: string;
  stored_path: string;
  content_type?: string | null;
  uploaded_at: string;
  classification?: ClassifierOutput | null;
  kyc?: KYCOutput | null;
  claims?: ClaimsOutput | null;
  policy?: PolicyOutput | null;
}

export interface CaseModel {
  case_id: string;
  patient_id?: string | null;
  status: CaseStatus;
  created_at: string;
  updated_at: string;
  documents: DocumentModel[];
  fraud?: FraudOutput | null;
  decision?: OrchestratorDecision | null;
}

export interface CaseSummary {
  case_id: string;
  patient_id?: string | null;
  status: CaseStatus;
  document_count: number;
  decision?: DecisionValue | null;
  created_at: string;
  updated_at: string;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store", ...init });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

export const listCases = () => req<CaseSummary[]>("/cases");

export const getCase = (caseId: string) =>
  req<CaseModel>(`/cases/${encodeURIComponent(caseId)}`);

export async function deleteCase(caseId: string): Promise<void> {
  const res = await fetch(`${API}/cases/${encodeURIComponent(caseId)}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 204)
    throw new Error(`Delete failed: ${res.status}`);
}

export const finalizeCase = (caseId: string) =>
  req<CaseModel>(`/cases/${encodeURIComponent(caseId)}/finalize`, {
    method: "POST",
  });

export const overrideCase = (
  caseId: string,
  decision: DecisionValue,
  reviewer: string,
  reason: string
) =>
  req<CaseModel>(`/cases/${encodeURIComponent(caseId)}/override`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, reviewer, reason }),
  });

export async function uploadDocument(caseId: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(
    `${API}/cases/${encodeURIComponent(caseId)}/documents`,
    { method: "POST", body: form }
  );
  if (!res.ok) throw new Error(`Upload failed: ${res.status} ${await res.text()}`);
  return (await res.json()) as DocumentModel;
}

export const imageUrl = (docId: string) =>
  `${API}/documents/${encodeURIComponent(docId)}/image`;
