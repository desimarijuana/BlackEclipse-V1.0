// ─── Evolution (self-improvement) front door (Phase 10) ─────────────────────
// Thin, typed proxy over the Python runtime's /evolution routes. Adds NO agentic
// logic (mirrors code-client.ts): it validates, forwards, and returns what the
// runtime owns. Operator-gated routes present the runtime secret by
// transport/token, never a body boolean.

import { HARNESS_PY_URL, ensurePythonRuntime } from "./python-runtime";
import { runtimeCallbackToken } from "./runtime-auth";
import { HarnessRuntimeUnavailable } from "./python-client";
import { redactSecrets } from "./errors";

export type EvolutionStatus =
  | "inert" | "proposed" | "refused" | "evaluating" | "evaluated_ok"
  | "evaluated_bad" | "canaried" | "activated" | "rolled_back" | "dismissed";

export interface EvolutionCandidate {
  id: string;
  signature: string;
  sourceCategory: string;
  observedCount: number;
  problemStatement: string;
  targetPath: string | null;
  status: EvolutionStatus;
  refusalCode: string | null;
  activatedVersion: string | null;
  previousVersion: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface EvolutionAttempt {
  id: string;
  candidateId: string;
  attemptIndex: number;
  targetPath: string;
  diffDigest: string;
  outcome: "success" | "failure" | "rolled_back" | "refused";
  outcomeReason: string | null;
  costMicros: number | null;
  tokensUsed: number | null;
  evaluation: Record<string, unknown> | null;
  startedAt: string;
  finishedAt: string | null;
}

export interface EvolutionMetrics {
  attempts: number;
  successRate: number | "UNKNOWN";
  regressionRate: number | "UNKNOWN";
  rollbackCount: number;
  costPerSuccess: number | "UNKNOWN";
  perCategory: Record<string, { attempts: number; successes: number; rollbacks: number }>;
  unmeasured: string[];
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    throw new HarnessRuntimeUnavailable(
      "The Python agent runtime is not available. Install the runtime: npm run setup:python",
    );
  }
  const operatorToken = runtimeCallbackToken();
  const res = await fetch(`${HARNESS_PY_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
      ...(init.headers ?? {}),
    },
    signal: AbortSignal.timeout(600_000),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (body as { detail?: string }).detail || `runtime HTTP ${res.status}`;
    throw new Error(redactSecrets(detail));
  }
  return body as T;
}

export async function listEvolutionCandidates(): Promise<EvolutionCandidate[]> {
  const body = await request<{ candidates: EvolutionCandidate[] }>("/evolution/candidates", { method: "GET" });
  return body.candidates ?? [];
}

export async function getEvolutionCandidate(id: string): Promise<EvolutionCandidate> {
  const body = await request<{ candidate: EvolutionCandidate }>(
    `/evolution/candidates/${encodeURIComponent(id)}`, { method: "GET" },
  );
  return body.candidate;
}

export async function listEvolutionAttempts(id: string): Promise<EvolutionAttempt[]> {
  const body = await request<{ attempts: EvolutionAttempt[] }>(
    `/evolution/candidates/${encodeURIComponent(id)}/attempts`, { method: "GET" },
  );
  return body.attempts ?? [];
}

export async function evaluateEvolutionCandidate(id: string): Promise<unknown> {
  return request(`/evolution/candidates/${encodeURIComponent(id)}/evaluate`, { method: "POST", body: "{}" });
}

export async function activateEvolutionCandidate(id: string, canary = false): Promise<unknown> {
  return request(`/evolution/candidates/${encodeURIComponent(id)}/activate`, {
    method: "POST", body: JSON.stringify({ canary }),
  });
}

export async function rollbackEvolutionCandidate(id: string, reason = ""): Promise<unknown> {
  return request(`/evolution/candidates/${encodeURIComponent(id)}/rollback`, {
    method: "POST", body: JSON.stringify({ reason }),
  });
}

export async function dismissEvolutionCandidate(id: string): Promise<unknown> {
  return request(`/evolution/candidates/${encodeURIComponent(id)}/dismiss`, { method: "POST" });
}

export async function evolutionMetrics(): Promise<EvolutionMetrics> {
  return request<EvolutionMetrics>("/evolution/metrics", { method: "GET" });
}

/** The plain state key for a candidate. The ONE place a state word is chosen. */
export function evolutionStateKey(status: EvolutionStatus): string {
  return `evolution.state.${status}`;
}

/** A metric rendered as a number or the honest "not measured" value. */
export function metricLabel(value: number | "UNKNOWN"): string {
  return value === "UNKNOWN" ? "not measured yet" : String(value);
}
