// ─── Python runtime HTTP client ──────────────────────────────────────────────
// Thin typed wrapper over the Python service. This is the only place Next.js
// talks to the runtime; it adds no agentic logic of its own.

import { HARNESS_PY_URL, ensurePythonRuntime } from "./python-runtime";
import type { HarnessErrorJson, HarnessEvent, RunRecord, RunResult, UsageSummary } from "./types";
import { redactSecrets } from "./errors";

export class HarnessRuntimeUnavailable extends Error {
  readonly code = "RUNTIME_UNAVAILABLE" as const;
  constructor(message: string) {
    super(message);
    this.name = "HarnessRuntimeUnavailable";
  }
}

export interface RunRequestPayload {
  runId: string;
  input: {
    query: string;
    ticker?: string;
    market?: string;
    context?: Record<string, unknown>;
    history?: Array<{ role: "user" | "assistant"; content: string }>;
    documents?: Array<{ name: string; text: string }>;
  };
  /** Authoritative agent id; Python resolves the config + prompt from it. */
  agentId: string;
  modelSettings: {
    provider: string;
    baseUrl?: string;
    apiKey?: string;
    model: string;
    temperature?: number;
    /** Optional operator-declared context window; absent = unknown. */
    contextWindow?: number;
  };
  userId?: string;
  // M3/M4 request-scoped isolation identity (optional).
  sessionId?: string;
  profileId?: string;
  projectId?: string;
  callbackBaseUrl: string;
  callbackToken?: string;
}

async function request<T>(
  path: string,
  init: RequestInit & { timeoutMs?: number } = {}
): Promise<T> {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    throw new HarnessRuntimeUnavailable(
      "The Python agent runtime is not available. Install the runtime: npm run setup:python"
    );
  }
  const { timeoutMs = 180_000, ...rest } = init;
  const res = await fetch(`${HARNESS_PY_URL}${path}`, {
    ...rest,
    headers: { "Content-Type": "application/json", ...(rest.headers ?? {}) },
    signal: AbortSignal.timeout(timeoutMs),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (body as { detail?: string }).detail || `runtime HTTP ${res.status}`;
    throw new Error(redactSecrets(detail));
  }
  return body as T;
}

export async function runtimeHealth(): Promise<{ ok: boolean; tools?: string[]; providers?: string[] }> {
  if (!(await ensurePythonRuntime())) return { ok: false };
  return request<{ ok: boolean; tools?: string[]; providers?: string[] }>("/health", { method: "GET" });
}

export async function listModelProviders(): Promise<Array<Record<string, unknown>>> {
  const body = await request<{ providers: Array<Record<string, unknown>> }>("/models", { method: "GET" });
  return body.providers ?? [];
}

export async function listAgentsFromRuntime(): Promise<{
  agents: Array<Record<string, unknown>>;
  defaultAgentId: string;
}> {
  const body = await request<{ agents: Array<Record<string, unknown>>; defaultAgentId?: string }>("/agents", {
    method: "GET",
  });
  return { agents: body.agents ?? [], defaultAgentId: body.defaultAgentId ?? "eclipse-agent" };
}

export async function runViaRuntime(
  payload: RunRequestPayload,
  opts: { background?: boolean } = {}
): Promise<RunResult | { runId: string; status: string }> {
  const query = opts.background ? "?background=true" : "";
  return request<RunResult | { runId: string; status: string }>(`/runs${query}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * Start a run in the background so its SSE stream can be observed live.
 * Returns the run id; the caller then streams `/api/harness/runs/:id/stream`.
 */
export async function startRunBackground(payload: RunRequestPayload): Promise<string> {
  const body = await runViaRuntime(payload, { background: true });
  return (body as { runId: string }).runId;
}

export async function getRunFromRuntime(runId: string): Promise<RunRecord | null> {
  try {
    const body = await request<{ run: RunRecord }>(`/runs/${encodeURIComponent(runId)}`, { method: "GET" });
    return body.run;
  } catch (err) {
    if (err instanceof Error && /404/.test(err.message)) return null;
    throw err;
  }
}

export async function listRunsFromRuntime(limit = 50): Promise<RunRecord[]> {
  const body = await request<{ runs: RunRecord[] }>(`/runs?limit=${limit}`, { method: "GET" });
  return body.runs ?? [];
}

export async function getUsageSummaryFromRuntime(days = 30): Promise<UsageSummary> {
  return request<UsageSummary>(`/usage?days=${days}`, { method: "GET" });
}

export async function getEventsFromRuntime(
  runId: string
): Promise<{ events: HarnessEvent[]; toolExecutions: Array<Record<string, unknown>> }> {
  const body = await request<{ events: HarnessEvent[]; toolExecutions: Array<Record<string, unknown>> }>(
    `/runs/${encodeURIComponent(runId)}/events`,
    { method: "GET" }
  );
  return { events: body.events ?? [], toolExecutions: body.toolExecutions ?? [] };
}

/**
 * Fetch the durable research receipt for a run (Phase 4).
 *
 * Read-only. Returns null when no receipt exists (ordinary chat or an older
 * run), so callers can render an honest "unavailable" state.
 */
export async function getRunReceiptFromRuntime(
  runId: string
): Promise<Record<string, unknown> | null> {
  try {
    const body = await request<{ receipt: Record<string, unknown> }>(
      `/research/receipts/${encodeURIComponent(runId)}`,
      { method: "GET" }
    );
    return body.receipt ?? null;
  } catch (err) {
    if (err instanceof Error && /404/.test(err.message)) return null;
    throw err;
  }
}

/** Run-level memory/skill explanation (Phase 7). Derived, read-only, redacted. */
export async function getRunExplanationFromRuntime(
  runId: string
): Promise<Record<string, unknown> | null> {
  try {
    return await request<Record<string, unknown>>(
      `/runs/${encodeURIComponent(runId)}/explain`,
      { method: "GET" }
    );
  } catch (err) {
    if (err instanceof Error && /404/.test(err.message)) return null;
    throw err;
  }
}

export async function cancelRunInRuntime(runId: string): Promise<boolean> {
  const body = await request<{ cancelled: boolean }>(`/runs/${encodeURIComponent(runId)}/cancel`, {
    method: "POST",
  });
  return Boolean(body.cancelled);
}

export type { HarnessErrorJson };
