// ─── Advisory Ledger BROWSER client ─────────────────────────────────────────
// The UI talks to the Next.js API routes (`/api/advisory/**`), which proxy to the
// Python runtime. This module MUST stay client-safe: fetch only (no fs, no
// child_process, no ensurePythonRuntime).

import type {
  AdvisoryDecisionView,
  AdvisoryScorecardView,
  AdvisoryStatus,
} from "./advisory-client";

export type { AdvisoryDecisionView, AdvisoryOutcomeView, AdvisoryScorecardView, AdvisoryStatus } from "./advisory-client";

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  const body = (await res.json().catch(() => ({}))) as T & { error?: string; detail?: string };
  if (!res.ok) throw new Error(body.error ?? body.detail ?? `request failed (${res.status})`);
  return body;
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
  const body = await api<{ decisions: AdvisoryDecisionView[] }>(`/api/advisory/decisions${query}`);
  return body.decisions ?? [];
}

export async function advisoryScorecard(portfolioId?: string): Promise<AdvisoryScorecardView> {
  const query = portfolioId ? `?portfolio_id=${encodeURIComponent(portfolioId)}` : "";
  return api<AdvisoryScorecardView>(`/api/advisory/scorecard${query}`);
}

export async function evaluateDecisions(
  marks: Record<string, number>,
  benchmarkReturn?: number,
): Promise<{ evaluated: number }> {
  return api<{ evaluated: number }>("/api/advisory/evaluate", {
    method: "POST",
    body: JSON.stringify({ marks, benchmarkReturn }),
  });
}
