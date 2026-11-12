// ─── Harness jobs BROWSER client ─────────────────────────────────────────────
// The UI talks to the Next.js API routes (`/api/jobs/**`), which proxy to the
// Python runtime. This module MUST stay client-safe: no `child_process`, no `fs`,
// no `ensurePythonRuntime` (that lives in the server-only `jobs-client.ts`). Fetch
// only. Without this split the Phase-6/11 jobs screen cannot be mounted from a
// client component — importing the server client pulls `child_process` into the
// browser bundle and the page fails to compile.

import type {
  BreakerState,
  CreateJobInput,
  DeliveryAdapter,
  DeliveryOutcomeView,
  JobDefinitionView,
  JobDeliveryTargetView,
  JobKind,
  JobRunStatus,
  JobRunView,
  JobTarget,
  JobTemplateView,
} from './jobs-client';

// Type-only re-export — erased at compile time, so no server code ships.
export type {
  BreakerState,
  CreateJobInput,
  DeliveryAdapter,
  DeliveryOutcomeView,
  JobDefinitionView,
  JobDeliveryTargetView,
  JobKind,
  JobRunStatus,
  JobRunView,
  JobTarget,
  JobTemplateView,
};

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
  });
  const body = (await res.json().catch(() => ({}))) as T & { error?: string; detail?: string };
  if (!res.ok) throw new Error(body.error ?? body.detail ?? `request failed (${res.status})`);
  return body;
}

export async function listJobs(scopeId?: string): Promise<JobDefinitionView[]> {
  const query = scopeId ? `?scopeId=${encodeURIComponent(scopeId)}` : '';
  const body = await api<{ jobs: JobDefinitionView[] }>(`/api/jobs${query}`);
  return body.jobs ?? [];
}

export async function listJobTemplates(): Promise<JobTemplateView[]> {
  const body = await api<{ templates: JobTemplateView[] }>('/api/jobs/templates');
  return body.templates ?? [];
}

export async function getJob(id: string): Promise<JobDefinitionView> {
  const body = await api<{ job: JobDefinitionView }>(`/api/jobs/${encodeURIComponent(id)}`);
  return body.job;
}

export async function createJob(input: CreateJobInput): Promise<{ job: JobDefinitionView; webhookToken?: string }> {
  const body = await api<{ job: JobDefinitionView; webhookToken?: string }>('/api/jobs', {
    method: 'POST',
    body: JSON.stringify(input),
  });
  return { job: body.job, webhookToken: body.webhookToken };
}

export async function updateJob(id: string, patch: Record<string, unknown>): Promise<JobDefinitionView> {
  const body = await api<{ job: JobDefinitionView }>(`/api/jobs/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  });
  return body.job;
}

export async function deleteJob(id: string): Promise<void> {
  await api(`/api/jobs/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export async function setJobEnabled(id: string, enabled: boolean): Promise<JobDefinitionView> {
  const body = await api<{ job: JobDefinitionView }>(
    `/api/jobs/${encodeURIComponent(id)}/${enabled ? 'enable' : 'disable'}`,
    { method: 'POST' },
  );
  return body.job;
}

export async function runJobNow(id: string): Promise<{ jobRunId: string }> {
  return api(`/api/jobs/${encodeURIComponent(id)}/run`, { method: 'POST' });
}

export async function resetJobBreaker(id: string): Promise<JobDefinitionView> {
  const body = await api<{ job: JobDefinitionView }>(
    `/api/jobs/${encodeURIComponent(id)}/reset-breaker`,
    { method: 'POST' },
  );
  return body.job;
}

export async function listJobRuns(id: string): Promise<JobRunView[]> {
  const body = await api<{ runs: JobRunView[] }>(`/api/jobs/${encodeURIComponent(id)}/runs`);
  return body.runs ?? [];
}

export interface JobArtifactView {
  'report.md'?: string;
  'meta.json'?: Record<string, unknown> | null;
  'receipt.json'?: Record<string, unknown> | null;
}

export async function getJobRunArtifact(
  jobId: string,
  runId: string,
  scopeId?: string,
): Promise<JobArtifactView> {
  const query = scopeId ? `?scopeId=${encodeURIComponent(scopeId)}` : '';
  const body = await api<{ artifact: JobArtifactView }>(
    `/api/jobs/${encodeURIComponent(jobId)}/runs/${encodeURIComponent(runId)}/artifact${query}`,
  );
  return body.artifact;
}

// ── Pure, client-safe render helpers (mirrors of the server client) ─────────

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
