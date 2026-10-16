// ─── Native Automation Engine front door ────────────────────────────────────
// Thin, typed proxy over the Python runtime's `/automations` routes. Adds NO
// agentic logic (mirrors jobs-client.ts): it validates, forwards, and returns
// what the runtime owns. Operator-gated routes present the runtime secret by
// transport/token, never a body boolean.

import { HARNESS_PY_URL, ensurePythonRuntime } from "./python-runtime";
import { runtimeCallbackToken } from "./runtime-auth";
import { HarnessRuntimeUnavailable } from "./python-client";
import { redactSecrets } from "./errors";

export type AutomationState =
  | "draft" | "validating" | "active" | "paused" | "disabled" | "archived";
export type TriggerKind =
  | "cron" | "interval" | "one_time" | "event" | "condition" | "manual";
export type ActionKind =
  | "execute_task" | "execute_workflow" | "run_agent" | "delegate_agent"
  | "call_tool" | "create_task" | "send_notification" | "generate_report"
  | "run_code" | "browser_action" | "custom_action";
export type ExecutionState =
  | "triggered" | "queued" | "running" | "waiting" | "retrying" | "completed"
  | "failed" | "cancelled" | "timed_out" | "blocked" | "skipped";
export type BreakerState = "closed" | "open" | "half_open";
export type DeliveryAdapter = "in_app" | "artifact" | "messaging";

export interface ConditionView {
  expression: string;
  edge: boolean;
  variables: string[];
}

export interface TriggerView {
  type: TriggerKind;
  cron: string | null;
  intervalSeconds: number | null;
  runAt: string | null;
  eventType: string | null;
  eventFilter: Record<string, unknown>;
  condition: ConditionView | null;
  timezone: string;
  startAt: string | null;
  endAt: string | null;
}

export interface ActionView {
  type: ActionKind;
  objective: string | null;
  agentId: string | null;
  workflowId: string | null;
  workflowInput: Record<string, unknown>;
  toolName: string | null;
  toolArgs: Record<string, unknown>;
  taskTitle: string | null;
  skillId: string | null;
  skillVersion: string | null;
  workspaceRoot: string | null;
  autonomy: string | null;
  notificationTemplate: string | null;
  credentialRef: string | null;
  config: Record<string, unknown>;
}

export interface AutomationView {
  id: string;
  name: string;
  description: string | null;
  version: number;
  state: AutomationState;
  trigger: TriggerView;
  condition: ConditionView | null;
  action: ActionView;
  execution: {
    maxRuntimeS: number;
    misfire: "skip" | "run_once" | "catch_up";
    catchUpMax: number;
    timeoutS: number | null;
  };
  retry: {
    maxAttempts: number;
    initialBackoffS: number;
    backoffMultiplier: number;
    maxBackoffS: number;
    jitter: boolean;
    retryableClasses: string[];
    nonRetryableClasses: string[];
  };
  concurrency: {
    maxConcurrentRuns: number;
    onConflict: "queue_if_running" | "skip_if_running" | "cancel_previous";
  };
  limits: {
    maxRuntimeS: number | null;
    maxTokens: number | null;
    maxCost: number | null;
    maxToolCalls: number | null;
    maxParallelTasks: number | null;
    maxRetries: number | null;
  };
  permissions: {
    allowed: string[];
    denied: string[];
    requiresApproval: boolean;
    approvalScope: string | null;
  };
  delivery: {
    onSuccess: boolean;
    onFailure: boolean;
    onApprovalRequired: boolean;
    onConditionTriggered: boolean;
    onTimeout: boolean;
    adapter: DeliveryAdapter;
    title: string | null;
    destination: string | null;
    targets: Array<{ destination: string; adapter: DeliveryAdapter }>;
  };
  scopeId: string | null;
  tags: string[];
  createdAt: string;
  updatedAt: string;
  lastRunAt: string | null;
  nextRunAt: string | null;
  consecutiveFailures: number;
  breaker: BreakerState;
  breakerOpenedAt: string | null;
  breakerResetBy: string | null;
}

export interface ExecutionView {
  id: string;
  automationId: string;
  automationVersion: number;
  runId: string | null;
  taskId: string | null;
  scopeId: string | null;
  triggerType: string;
  triggerRef: string | null;
  state: ExecutionState;
  attempt: number;
  maxAttempts: number;
  scheduledFor: string | null;
  startedAt: string;
  finishedAt: string | null;
  outcomeReason: string | null;
  errorClass: string | null;
  cost: number | null;
  tokens: number | null;
  workerId: string | null;
  leaseExpiresAt: string | null;
  snapshot: Record<string, unknown> | null;
  dryRun: boolean;
  /** The run's answer, bounded. Null when the run produced nothing or failed. */
  output: string | null;
  events?: Array<{ seq: number; at: string; type: string; data: Record<string, unknown> | null }>;
  deliveries?: Array<{
    adapter: string; destination: string | null; ok: boolean;
    reasonCode: string | null; reason: string | null; at: string;
  }>;
}

export interface ValidationIssueView {
  severity: "error" | "warning";
  code: string;
  field: string;
  message: string;
}

export interface AutomationStatusView {
  automationId: string;
  state: AutomationState;
  version: number;
  nextRunAt: string | null;
  lastRunAt: string | null;
  breaker: BreakerState;
  executionCount: number;
  successCount: number;
  failureCount: number;
  successRate: number | null;
  averageDurationS: number | null;
  totalCost: number | null;
  totalTokens: number | null;
  lastExecution: ExecutionView | null;
}

export interface AutomationMetricsView {
  automationCount: number;
  activeAutomationCount: number;
  pausedAutomationCount: number;
  disabledAutomationCount: number;
  executionCount: number;
  successfulExecutionCount: number;
  failedExecutionCount: number;
  retryCount: number;
  deliveryCount: number;
  openBreakerCount: number;
  activeExecutionCount: number;
  inFlight: number;
  maxInFlight: number;
  workerId: string;
  tickMs: number;
  tickSeconds: number;
}

export interface CreateAutomationInput {
  name: string;
  description?: string;
  state?: AutomationState;
  trigger: Partial<TriggerView> & { type: TriggerKind };
  condition?: ConditionView;
  action: Partial<ActionView> & { type: ActionKind };
  execution?: Partial<AutomationView["execution"]>;
  retry?: Partial<AutomationView["retry"]>;
  concurrency?: Partial<AutomationView["concurrency"]>;
  limits?: Partial<AutomationView["limits"]>;
  permissions?: Partial<AutomationView["permissions"]>;
  delivery?: Partial<AutomationView["delivery"]>;
  scopeId?: string;
  tags?: string[];
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

export async function listAutomations(scopeId?: string, state?: AutomationState): Promise<AutomationView[]> {
  const params = new URLSearchParams();
  if (scopeId) params.set("scopeId", scopeId);
  if (state) params.set("state", state);
  const query = params.toString() ? `?${params.toString()}` : "";
  const body = await request<{ automations: AutomationView[] }>(`/automations${query}`, { method: "GET" });
  return body.automations ?? [];
}

export async function getAutomation(id: string): Promise<AutomationView> {
  const body = await request<{ automation: AutomationView }>(`/automations/${encodeURIComponent(id)}`, { method: "GET" });
  return body.automation;
}

export async function createAutomation(input: CreateAutomationInput): Promise<AutomationView> {
  const body = await request<{ automation: AutomationView }>("/automations", {
    method: "POST",
    body: JSON.stringify(input),
  });
  return body.automation;
}

export async function updateAutomation(id: string, patch: Record<string, unknown>): Promise<AutomationView> {
  const body = await request<{ automation: AutomationView }>(`/automations/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
  return body.automation;
}

export async function deleteAutomation(id: string): Promise<void> {
  await request(`/automations/${encodeURIComponent(id)}`, { method: "DELETE" });
}

async function lifecycle(id: string, action: string): Promise<AutomationView> {
  const body = await request<{ automation: AutomationView }>(
    `/automations/${encodeURIComponent(id)}/${action}`, { method: "POST" },
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
  return request(`/automations/${encodeURIComponent(id)}/run`, { method: "POST" });
}

export async function dryRunAutomation(id: string): Promise<Record<string, unknown>> {
  const body = await request<{ dryRun: Record<string, unknown> }>(
    `/automations/${encodeURIComponent(id)}/dry-run`, { method: "POST" },
  );
  return body.dryRun;
}

export async function testAutomation(id: string): Promise<{
  valid: boolean;
  issues: ValidationIssueView[];
  plannedActions: Record<string, unknown>;
}> {
  return request(`/automations/${encodeURIComponent(id)}/test`, { method: "POST" });
}

export async function validateAutomation(id: string): Promise<{ valid: boolean; issues: ValidationIssueView[] }> {
  return request(`/automations/${encodeURIComponent(id)}/validate`, { method: "POST" });
}

export async function getAutomationStatus(id: string): Promise<AutomationStatusView> {
  const body = await request<{ status: AutomationStatusView }>(
    `/automations/${encodeURIComponent(id)}/status`, { method: "GET" },
  );
  return body.status;
}

export async function listAutomationHistory(id: string): Promise<ExecutionView[]> {
  const body = await request<{ executions: ExecutionView[] }>(
    `/automations/${encodeURIComponent(id)}/history`, { method: "GET" },
  );
  return body.executions ?? [];
}

export async function listAutomationVersions(id: string): Promise<Array<{ version: number; createdAt: string; createdBy: string | null }>> {
  const body = await request<{ versions: Array<{ version: number; createdAt: string; createdBy: string | null }> }>(
    `/automations/${encodeURIComponent(id)}/versions`, { method: "GET" },
  );
  return body.versions ?? [];
}

export async function getAutomationExecution(executionId: string): Promise<ExecutionView> {
  const body = await request<{ execution: ExecutionView }>(
    `/automations/executions/${encodeURIComponent(executionId)}`, { method: "GET" },
  );
  return body.execution;
}

export async function getAutomationTimeline(executionId: string): Promise<NonNullable<ExecutionView["events"]>> {
  const body = await request<{ timeline: NonNullable<ExecutionView["events"]> }>(
    `/automations/executions/${encodeURIComponent(executionId)}/timeline`, { method: "GET" },
  );
  return body.timeline ?? [];
}

export async function cancelAutomationExecution(executionId: string): Promise<void> {
  await request(`/automations/executions/${encodeURIComponent(executionId)}/cancel`, { method: "POST" });
}

export async function resumeAutomationExecution(executionId: string): Promise<void> {
  await request(`/automations/executions/${encodeURIComponent(executionId)}/resume`, { method: "POST" });
}

export async function getAutomationMetrics(): Promise<AutomationMetricsView> {
  const body = await request<{ metrics: AutomationMetricsView }>("/automations/metrics", { method: "GET" });
  return body.metrics;
}

/** The plain status key for an execution. The ONE place the word is chosen. */
export function executionStateKey(state: ExecutionState): string {
  return `automations.execution.state.${state}`;
}

/** The plain sentence for a breaker state. */
export function breakerStateKey(state: BreakerState): string {
  return `automations.breaker.${state}`;
}
