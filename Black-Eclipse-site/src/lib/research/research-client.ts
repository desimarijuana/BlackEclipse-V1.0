// ── Research screen client ──────────────────────────────────────────────────
// The dedicated research surface talks to the Python web-research engine through
// the `/api/research/*` front-door proxy. This module MUST stay client-safe
// (fetch only). It adds no research logic — it lists, starts, polls, cancels and
// reads runs the runtime owns.

export interface ResearchRunRow {
  researchId: string;
  question: string;
  objective?: string | null;
  intent?: string | null;
  depth?: string | null;
  state: string;
  status?: string | null;
  pointInTime?: string | null;
  freshness?: string | null;
  /** The deterministic, evidence-grounded synthesized answer (persisted). */
  answer?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface ResearchEvidenceRow {
  evidenceId: string;
  sourceUrl?: string | null;
  rawText?: string | null;
  rawTextTruncated?: boolean;
  rawTextChars?: number;
  structuredValue?: number | null;
  unit?: string | null;
  period?: string | null;
  contentHash?: string | null;
  contentTrust?: string | null;
}

export interface ResearchRunDetail {
  run: ResearchRunRow;
  evidence: ResearchEvidenceRow[];
  sources: Array<Record<string, unknown>>;
  claims: Array<Record<string, unknown>>;
  citations: Array<Record<string, unknown>>;
  conflicts: Array<Record<string, unknown>>;
  entities?: Array<Record<string, unknown>>;
  relations?: Array<Record<string, unknown>>;
  snapshots: Array<Record<string, unknown>>;
}

export interface ResearchStatusView {
  researchId: string;
  state: string;
  stopReason?: string | null;
  progress?: number | null;
  sourceCount?: number | null;
  evidenceCount?: number | null;
  claimCount?: number | null;
  conflictCount?: number | null;
  questionsAnswered?: number | null;
  questionsTotal?: number | null;
}

export interface StartResearchInput {
  question: string;
  depth?: string;
  freshness?: string;
  pointInTime?: string;
  minSources?: number;
  maxSources?: number;
  maxQueries?: number;
  maxTimeSeconds?: number;
  crossValidationRequired?: boolean;
  primarySourcesRequired?: boolean;
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  const body = (await res.json().catch(() => ({}))) as T & { error?: string };
  if (!res.ok) throw new Error(body.error ?? `request failed (${res.status})`);
  return body;
}

export function listResearchRuns(limit = 50): Promise<ResearchRunRow[]> {
  return api<{ runs: ResearchRunRow[] }>(`/api/research/list?limit=${limit}`).then((b) => b.runs ?? []);
}

export function getResearchRun(researchId: string): Promise<ResearchRunDetail> {
  return api<ResearchRunDetail>(`/api/research/${encodeURIComponent(researchId)}`);
}

export function getResearchStatus(researchId: string): Promise<ResearchStatusView> {
  return api<{ status: ResearchStatusView }>(
    `/api/research/${encodeURIComponent(researchId)}/status`,
  ).then((b) => b.status);
}

export function startResearch(input: StartResearchInput): Promise<{ researchId: string }> {
  return api<{ researchId: string }>("/api/research/start", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function cancelResearch(researchId: string): Promise<{ success: boolean }> {
  return api(`/api/research/${encodeURIComponent(researchId)}/cancel`, { method: "POST" });
}

export function continueResearch(researchId: string): Promise<unknown> {
  return api(`/api/research/${encodeURIComponent(researchId)}/continue`, { method: "POST" });
}

/** True for a run that has reached a terminal, non-progressing state. */
export function isTerminalState(state: string | null | undefined): boolean {
  return state === "COMPLETED" || state === "PARTIAL" || state === "FAILED" || state === "CANCELLED";
}
