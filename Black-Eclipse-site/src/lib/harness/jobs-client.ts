// ─── Harness jobs front door (Phase 6) ──────────────────────────────────────
// Thin, typed proxy over the Python runtime's /jobs routes. Adds NO agentic
// logic (mirrors code-client.ts): it validates, forwards, and returns what the
// runtime owns. Operator-gated routes present the runtime secret by
// transport/token, never a body boolean.

import { HARNESS_PY_URL, ensurePythonRuntime } from "./python-runtime";
import { runtimeCallbackToken } from "./runtime-auth";
import { HarnessRuntimeUnavailable } from "./python-client";
import { redactSecrets } from "./errors";

export type JobKind = "cron" | "interval" | "file_watch" | "webhook" | "manual";
export type JobRunStatus = "running" | "ok" | "failed" | "skipped" | "timed_out" | "refused";
export type BreakerState = "closed" | "open" | "half_open";
export type DeliveryAdapter = "in_app" | "artifact" | "messaging";

/** One configured way for a job's result to reach the user (Phase 11). */
export interface JobDeliveryTargetView {
  destination: string;
  adapter: DeliveryAdapter;
}

export interface DeliveryOutcomeView {
  adapter: DeliveryAdapter;
  target: string | null;
  ok: boolean;
  reason: string | null;
  reasonCode: "NO_DESTINATION" | "DELIVERY_FAILED" | "REFUSED" | null;
}

export interface JobTarget {
  kind: "skill" | "objective";
  skillId: string | null;
  skillVersion: string | null;
  objective: string | null;
  agentId: string;
  workspaceRoot: string | null;
  autonomy: string | null;
}

export interface JobDefinitionView {
  id: string;
  name: string;
  kind: JobKind;
  cron: string | null;
  intervalSeconds: number | null;
  watchPath: string | null;
  timezone: string;
  onMissed: "skip" | "run_once";
  target: JobTarget;
  delivery: {
    adapter: DeliveryAdapter;
    title: string | null;
    destination: string | null;
    targets: JobDeliveryTargetView[];
  };
  scopeId: string | null;
  enabled: boolean;
  maxRuntimeS: number;
  createdAt: string;
  updatedAt: string;
  lastRunAt: string | null;
  consecutiveFailures: number;
  breaker: BreakerState;
  breakerOpenedAt: string | null;
  breakerResetBy: string | null;
  webhook: boolean;
  lastRun?: JobRunView | null;
}

export interface JobRunView {
  id: string;
  jobId: string;
  runId: string | null;
  triggeredBy: "schedule" | "webhook" | "file_watch" | "manual";
  scheduledFor: string;
  startedAt: string;
  finishedAt: string | null;
  status: JobRunStatus;
  outcomeReason: string | null;
  delivery: Record<string, unknown> | null;
  deliveries: DeliveryOutcomeView[] | null;
  scopeId: string | null;
  missed: boolean;
}

export interface JobTemplateView {
  id: string;
  name: string;
  description: string;
  kind: JobKind;
  cron: string | null;
  intervalSeconds: number | null;
  onMissed: "skip" | "run_once";
  parameters: Array<{ key: string; label: string; required: boolean; example: string }>;
}

export interface CreateJobInput {
  name?: string;
  kind?: JobKind;
  cron?: string;
  intervalSeconds?: number;
  watchPath?: string;
  timezone?: string;
  onMissed?: "skip" | "run_once";
  target?: Partial<JobTarget>;
  delivery?: {
    adapter: DeliveryAdapter;
    title?: string;
    destination?: string;
    targets?: JobDeliveryTargetView[];
  };
  scopeId?: string;
  maxRuntimeS?: number;
  templateId?: string;
  params?: Record<string, string>;
  enableWebhook?: boolean;
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

export async function listJobs(scopeId?: string): Promise<JobDefinitionView[]> {
  const query = scopeId ? `?scopeId=${encodeURIComponent(scopeId)}` : "";
  const body = await request<{ jobs: JobDefinitionView[] }>(`/jobs${query}`, { method: "GET" });
  return body.jobs ?? [];
}

export async function listJobTemplates(): Promise<JobTemplateView[]> {
  const body = await request<{ templates: JobTemplateView[] }>("/jobs/templates", { method: "GET" });
  return body.templates ?? [];
}

export async function getJob(id: string): Promise<JobDefinitionView> {
  const body = await request<{ job: JobDefinitionView }>(`/jobs/${encodeURIComponent(id)}`, { method: "GET" });
  return body.job;
}

export async function createJob(input: CreateJobInput): Promise<{ job: JobDefinitionView; webhookToken?: string }> {
  const body = await request<{ job: JobDefinitionView; webhookToken?: string }>("/jobs", {
    method: "POST",
    body: JSON.stringify(input),
  });
  return { job: body.job, webhookToken: body.webhookToken };
}

export async function updateJob(id: string, patch: Record<string, unknown>): Promise<JobDefinitionView> {
  const body = await request<{ job: JobDefinitionView }>(`/jobs/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
  return body.job;
}

export async function deleteJob(id: string): Promise<void> {
  await request(`/jobs/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function setJobEnabled(id: string, enabled: boolean): Promise<JobDefinitionView> {
  const body = await request<{ job: JobDefinitionView }>(
    `/jobs/${encodeURIComponent(id)}/${enabled ? "enable" : "disable"}`,
    { method: "POST" },
  );
  return body.job;
}

export async function runJobNow(id: string): Promise<{ jobRunId: string }> {
  return request(`/jobs/${encodeURIComponent(id)}/run`, { method: "POST" });
}

export async function resetJobBreaker(id: string): Promise<JobDefinitionView> {
  const body = await request<{ job: JobDefinitionView }>(
    `/jobs/${encodeURIComponent(id)}/reset-breaker`,
    { method: "POST" },
  );
  return body.job;
}

export async function listJobRuns(id: string): Promise<JobRunView[]> {
  const body = await request<{ runs: JobRunView[] }>(`/jobs/${encodeURIComponent(id)}/runs`, { method: "GET" });
  return body.runs ?? [];
}

/** The plain status key for a run. The ONE place a run status word is chosen. */
export function jobRunStatusKey(status: JobRunStatus): string {
  return `jobs.run.status.${status}`;
}

/** The plain sentence for a breaker state. */
export function breakerStateKey(state: BreakerState): string {
  return `jobs.breaker.${state}`;
}

/** The plain refusal key for a delivery outcome. The code stays behind "details". */
export function deliveryReasonKey(reasonCode: string | null | undefined): string {
  if (reasonCode) return `refusal.${reasonCode}`;
  return 'refusal.DELIVERY_FAILED';
}

export interface JobArtifactView {
  'report.md'?: string;
  'meta.json'?: Record<string, unknown> | null;
  'receipt.json'?: Record<string, unknown> | null;
}

/** Read a saved report artifact for one run. The path is derived by the runtime. */
export async function getJobRunArtifact(
  jobId: string,
  runId: string,
  scopeId?: string,
): Promise<JobArtifactView> {
  const query = scopeId ? `?scopeId=${encodeURIComponent(scopeId)}` : '';
  const body = await request<{ artifact: JobArtifactView }>(
    `/jobs/${encodeURIComponent(jobId)}/runs/${encodeURIComponent(runId)}/artifact${query}`,
    { method: "GET" },
  );
  return body.artifact;
}
