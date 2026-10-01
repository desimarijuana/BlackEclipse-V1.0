// ─── Workflow front door (Harness closeout Phase 5) ─────────────────────────
// Thin typed wrapper over the Python runtime's /workflows endpoints. Python owns
// validation, storage and compilation; this only forwards (and forwards the
// operator token so a mutation authenticates by transport, never a body flag).

import { HARNESS_PY_URL, ensurePythonRuntime } from "./python-runtime";
import { runtimeCallbackToken } from "./runtime-auth";
import { HarnessRuntimeUnavailable } from "./python-client";
import { redactSecrets } from "./errors";
import type { Workflow, WorkflowRunResult, WorkflowSummary } from "./workflow-types";

async function request<T>(path: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<T> {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    throw new HarnessRuntimeUnavailable(
      "The Python agent runtime is not available. Install the runtime: npm run setup:python"
    );
  }
  const { timeoutMs = 300_000, ...rest } = init;
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

export async function listWorkflows(): Promise<WorkflowSummary[]> {
  const body = await request<{ workflows: WorkflowSummary[] }>("/workflows", { method: "GET" });
  return body.workflows ?? [];
}

export async function getWorkflow(id: string, version?: string): Promise<Workflow | null> {
  try {
    const q = version ? `?version=${encodeURIComponent(version)}` : "";
    const body = await request<{ workflow: Workflow }>(`/workflows/${encodeURIComponent(id)}${q}`, { method: "GET" });
    return body.workflow;
  } catch (err) {
    if (err instanceof Error && /404/.test(err.message)) return null;
    throw err;
  }
}

export async function saveWorkflow(workflow: Workflow): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/workflows", {
    method: "POST",
    body: JSON.stringify(workflow),
  });
}

export async function deleteWorkflow(id: string, version?: string): Promise<number> {
  const q = version ? `?version=${encodeURIComponent(version)}` : "";
  const body = await request<{ deleted: number }>(`/workflows/${encodeURIComponent(id)}${q}`, { method: "DELETE" });
  return body.deleted ?? 0;
}

export async function runWorkflow(payload: Record<string, unknown>): Promise<WorkflowRunResult> {
  return request<WorkflowRunResult>("/workflows/run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
