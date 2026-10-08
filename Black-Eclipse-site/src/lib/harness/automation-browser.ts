// ─── Native Automation Engine BROWSER client ────────────────────────────────
// The UI talks to the Next.js API routes (`/api/automations/**`), which proxy to
// the Python runtime. This module MUST stay client-safe: no `child_process`, no
// `fs`, no `ensurePythonRuntime`. Fetch only (mirrors jobs-browser.ts).

import type {
  ActionKind,
  ActionView,
  AutomationMetricsView,
  AutomationState,
  AutomationStatusView,
  AutomationView,
  BreakerState,
  ConditionView,
  CreateAutomationInput,
  DeliveryAdapter,
  ExecutionState,
  ExecutionView,
  TriggerKind,
  TriggerView,
  ValidationIssueView,
} from "./automation-client";

export type {
  ActionKind,
  ActionView,
  AutomationMetricsView,
  AutomationState,
  AutomationStatusView,
  AutomationView,
  BreakerState,
  ConditionView,
  CreateAutomationInput,
  DeliveryAdapter,
  ExecutionState,
  ExecutionView,
  TriggerKind,
  TriggerView,
  ValidationIssueView,
};

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  const body = (await res.json().catch(() => ({}))) as T & { error?: string; detail?: string };
  if (!res.ok) throw new Error(body.error ?? body.detail ?? `request failed (${res.status})`);
  return body;
}

export async function listAutomations(scopeId?: string, state?: AutomationState): Promise<AutomationView[]> {
  const params = new URLSearchParams();
  if (scopeId) params.set("scopeId", scopeId);
  if (state) params.set("state", state);
  const query = params.toString() ? `?${params.toString()}` : "";
  const body = await api<{ automations: AutomationView[] }>(`/api/automations${query}`);
  return body.automations ?? [];
}

export async function getAutomation(id: string): Promise<AutomationView> {
  const body = await api<{ automation: AutomationView }>(`/api/automations/${encodeURIComponent(id)}`);
  return body.automation;
}

export async function createAutomation(input: CreateAutomationInput): Promise<AutomationView> {
  const body = await api<{ automation: AutomationView }>("/api/automations", {
    method: "POST", body: JSON.stringify(input),
  });
  return body.automation;
}

export async function updateAutomation(id: string, patch: Record<string, unknown>): Promise<AutomationView> {
  const body = await api<{ automation: AutomationView }>(`/api/automations/${encodeURIComponent(id)}`, {
    method: "PATCH", body: JSON.stringify(patch),
  });
  return body.automation;
}

export async function deleteAutomation(id: string): Promise<void> {
  await api(`/api/automations/${encodeURIComponent(id)}`, { method: "DELETE" });
}

async function lifecycle(id: string, action: string): Promise<AutomationView> {
  const body = await api<{ automation: AutomationView }>(
    `/api/automations/${encodeURIComponent(id)}/${action}`, { method: "POST" },
  );
  return body.automation;
}

export const enableAutomation = (id: string) => lifecycle(id, "enable");
export const disableAutomation = (id: string) => lifecycle(id, "disable");
export const pauseAutomation = (id: string) => lifecycle(id, "pause");
export const resumeAutomation = (id: string) => lifecycle(id, "resume");
export const archiveAutomation = (id: string) => lifecycle(id, "archive");
export const resetAutomationBreaker = (id: string) => lifecycle(id, "reset-breaker");

export async function runAutomationNow(id: string): Promise<{ executionId: string }> {
  return api(`/api/automations/${encodeURIComponent(id)}/run`, { method: "POST" });
}

export async function dryRunAutomation(id: string): Promise<Record<string, unknown>> {
  const body = await api<{ dryRun: Record<string, unknown> }>(
    `/api/automations/${encodeURIComponent(id)}/dry-run`, { method: "POST" },
  );
  return body.dryRun;
}

export async function testAutomation(id: string): Promise<{
  valid: boolean; issues: ValidationIssueView[]; plannedActions: Record<string, unknown>;
}> {
  return api(`/api/automations/${encodeURIComponent(id)}/test`, { method: "POST" });
}

export async function validateAutomation(id: string): Promise<{ valid: boolean; issues: ValidationIssueView[] }> {
  return api(`/api/automations/${encodeURIComponent(id)}/validate`, { method: "POST" });
}

export async function getAutomationStatus(id: string): Promise<AutomationStatusView> {
  const body = await api<{ status: AutomationStatusView }>(
    `/api/automations/${encodeURIComponent(id)}/status`,
  );
  return body.status;
}

export async function listAutomationHistory(id: string): Promise<ExecutionView[]> {
  const body = await api<{ executions: ExecutionView[] }>(
    `/api/automations/${encodeURIComponent(id)}/history`,
  );
  return body.executions ?? [];
}

export async function listAutomationVersions(id: string): Promise<Array<{ version: number; createdAt: string; createdBy: string | null }>> {
  const body = await api<{ versions: Array<{ version: number; createdAt: string; createdBy: string | null }> }>(
    `/api/automations/${encodeURIComponent(id)}/versions`,
  );
  return body.versions ?? [];
}

export async function getAutomationExecution(executionId: string): Promise<ExecutionView> {
  const body = await api<{ execution: ExecutionView }>(
    `/api/automations/executions/${encodeURIComponent(executionId)}`,
  );
  return body.execution;
}

export async function getAutomationTimeline(executionId: string): Promise<NonNullable<ExecutionView["events"]>> {
  const body = await api<{ timeline: NonNullable<ExecutionView["events"]> }>(
    `/api/automations/executions/${encodeURIComponent(executionId)}/timeline`,
  );
  return body.timeline ?? [];
}

export async function cancelAutomationExecution(executionId: string): Promise<void> {
  await api(`/api/automations/executions/${encodeURIComponent(executionId)}/cancel`, { method: "POST" });
}

export async function resumeAutomationExecution(executionId: string): Promise<void> {
  await api(`/api/automations/executions/${encodeURIComponent(executionId)}/resume`, { method: "POST" });
}

export async function getAutomationMetrics(): Promise<AutomationMetricsView> {
  const body = await api<{ metrics: AutomationMetricsView }>("/api/automations/metrics");
  return body.metrics;
}

export function executionStateKey(state: ExecutionState): string {
  return `automations.execution.state.${state}`;
}

export function breakerStateKey(state: BreakerState): string {
  return `automations.breaker.${state}`;
}
