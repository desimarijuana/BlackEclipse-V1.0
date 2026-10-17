// ─── Advisory Ledger front door ─────────────────────────────────────────────
// Thin, typed proxy over the Python runtime's `/advisory` routes. Adds NO logic:
// it validates, forwards and returns what the runtime owns. Operator-gated
// routes present the runtime secret by transport/token, never a body boolean.

import { HARNESS_PY_URL, ensurePythonRuntime } from "./python-runtime";
import { runtimeCallbackToken } from "./runtime-auth";
import { HarnessRuntimeUnavailable } from "./python-client";
import { redactSecrets } from "./errors";

export type AdvisoryStatus = "computed" | "sourced" | "unverified";
export type OutcomeVerdict = "right" | "wrong" | "neutral";

export interface AdvisoryBasisView {
  kind: string;
  ref: string | null;
  valueHash: string | null;
}

export interface AdvisoryOutcomeView {
  decisionId: string;
  evaluatedAt: string;
  horizon: string | null;
  realizedReturn: number | null;
  benchmarkReturn: number | null;
  verdict: OutcomeVerdict;
  note: string | null;
}

export interface AdvisoryDecisionView {
  id: string;
  runId: string | null;
  portfolioId: string | null;
  conversationId: string | null;
  ownerId: string | null;
  createdAt: string;
  action: string;
  symbols: string[];
  target: string | null;
  thesis: string | null;
  status: AdvisoryStatus;
  truthReason: string | null;
  basis?: AdvisoryBasisView[];
  outcome?: AdvisoryOutcomeView | null;
}

export interface AdvisoryScorecardView {
  total: number;
  byStatus: Record<AdvisoryStatus, number>;
  evaluated: number;
  outcomes: Record<OutcomeVerdict, number>;
  hitRate: number | null;
  avgRealizedReturn: number | null;
  avgBenchmarkReturn: number | null;
}

async function request<T>(path: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<T> {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    throw new HarnessRuntimeUnavailable(
      "The Python agent runtime is not available. Install the runtime: npm run setup:python",
    );
  }
  const { timeoutMs = 30_000, ...rest } = init;
  const operatorToken = runtimeCallbackToken();
  const res = await fetch(`${HARNESS_PY_URL}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
      ...(rest.headers ?? {}),
    },
    signal: AbortSignal.timeout(timeoutMs),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (body as { detail?: string }).detail || `runtime HTTP ${res.status}`;
    throw new Error(redactSecrets(detail));
  }
  return body as T;
}

export async function listDecisions(opts: {
  portfolioId?: string;
  status?: AdvisoryStatus;
  limit?: number;
} = {}): Promise<AdvisoryDecisionView[]> {
  const params = new URLSearchParams();
  if (opts.portfolioId) params.set("portfolio_id", opts.portfolioId);
  if (opts.status) params.set("status", opts.status);
  if (opts.limit) params.set("limit", String(opts.limit));
  const query = params.toString() ? `?${params.toString()}` : "";
  const body = await request<{ decisions: AdvisoryDecisionView[] }>(`/advisory/decisions${query}`, { method: "GET" });
  return body.decisions ?? [];
}

export async function getDecision(id: string): Promise<AdvisoryDecisionView> {
  return request<AdvisoryDecisionView>(`/advisory/decisions/${encodeURIComponent(id)}`, { method: "GET" });
}

export async function advisoryScorecard(portfolioId?: string): Promise<AdvisoryScorecardView> {
  const query = portfolioId ? `?portfolio_id=${encodeURIComponent(portfolioId)}` : "";
  return request<AdvisoryScorecardView>(`/advisory/scorecard${query}`, { method: "GET" });
}

export async function evaluateDecisions(
  marks: Record<string, number>,
  benchmarkReturn?: number,
): Promise<{ evaluated: number; outcomes: AdvisoryOutcomeView[] }> {
  return request<{ evaluated: number; outcomes: AdvisoryOutcomeView[] }>("/advisory/evaluate", {
    method: "POST",
    body: JSON.stringify({ marks, benchmarkReturn }),
  });
}
