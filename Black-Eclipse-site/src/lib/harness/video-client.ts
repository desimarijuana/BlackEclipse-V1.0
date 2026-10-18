// ─── Native video BROWSER client ─────────────────────────────────────────────
// The UI talks to the Next.js API route (`/api/video/**`), which proxies to the
// Python runtime's `/video/*` routes. This module MUST stay client-safe: fetch
// only — no `child_process`, no `fs`, no `python-runtime` import (that lives on
// the server side of the proxy).
//
// Every call reports failures as a `VideoApiError` carrying the Python error
// `code` (PROJECT_NOT_FOUND, REPAIR_LIMIT_REACHED, …) so the UI can be honest
// about WHY something was refused. Nothing here invents a job or a video.

export class VideoApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "VideoApiError";
    this.status = status;
    this.code = code;
  }
}

/** The Fabric job record for a video job, as the service reports it. */
export interface VideoJobView {
  jobId: string;
  status: string;
  progress?: number;
  terminal?: boolean;
  attempts?: number;
  maxAttempts?: number;
  error?: string | null;
  errorClass?: string | null;
  input?: Record<string, unknown> | null;
  output?: Record<string, unknown> | null;
  createdAt?: number;
  updatedAt?: number;
}

export interface VideoProjectView {
  id: string;
  name: string;
  kind: string;
  revision?: number;
  spec?: Record<string, unknown>;
  createdAt?: string;
  updatedAt?: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/video${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (data as { detail?: { code?: string; message?: string } }).detail;
    const message =
      detail?.message ??
      (data as { error?: string }).error ??
      `Video request failed (${res.status})`;
    throw new VideoApiError(message, res.status, detail?.code);
  }
  return data as T;
}

// ── capabilities ──────────────────────────────────────────────────────────────

export async function getVideoCapabilities(): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('/capabilities');
}

// ── projects ──────────────────────────────────────────────────────────────────

export async function listVideoProjects(): Promise<VideoProjectView[]> {
  const body = await request<{ projects: VideoProjectView[] }>('/projects');
  return body.projects ?? [];
}

export async function createVideoProject(input: {
  name: string;
  kind?: string;
  spec?: Record<string, unknown>;
}): Promise<VideoProjectView> {
  const body = await request<{ project: VideoProjectView }>('/projects', {
    method: 'POST',
    body: JSON.stringify(input),
  });
  return body.project;
}

/**
 * Create a data-bound market-recap video project (1-5 symbols). Every figure is
 * resolved through the market-data gateway at render time; rendering stays the
 * ordinary draft/final job.
 */
export async function createVideoRecap(input: {
  symbols: string[];
  title?: string;
  subtitle?: string;
}): Promise<VideoProjectView> {
  const body = await request<{ project: VideoProjectView }>('/recaps', {
    method: 'POST',
    body: JSON.stringify(input),
  });
  return body.project;
}

export async function getVideoProject(projectId: string): Promise<VideoProjectView> {
  const body = await request<{ project: VideoProjectView }>(
    `/projects/${encodeURIComponent(projectId)}`,
  );
  return body.project;
}

export async function updateVideoProject(
  projectId: string,
  input: { name?: string; spec?: Record<string, unknown> },
): Promise<VideoProjectView> {
  const body = await request<{ project: VideoProjectView }>(
    `/projects/${encodeURIComponent(projectId)}`,
    { method: 'PUT', body: JSON.stringify(input) },
  );
  return body.project;
}

export async function validateVideoProject(projectId: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(
    `/projects/${encodeURIComponent(projectId)}/validate`,
    { method: 'POST' },
  );
}

// ── job-submitting operations ─────────────────────────────────────────────────

export async function previewVideoProject(
  projectId: string,
  options: { conversationId?: string; frames?: boolean } = {},
): Promise<VideoJobView> {
  const body = await request<{ job: VideoJobView }>(
    `/projects/${encodeURIComponent(projectId)}/preview`,
    { method: 'POST', body: JSON.stringify(options) },
  );
  return body.job;
}

export async function renderVideoProject(
  projectId: string,
  mode: 'draft' | 'final',
  options: { conversationId?: string } = {},
): Promise<VideoJobView> {
  const body = await request<{ job: VideoJobView }>(
    `/projects/${encodeURIComponent(projectId)}/render`,
    { method: 'POST', body: JSON.stringify({ mode, ...options }) },
  );
  return body.job;
}

export async function repairVideoProject(
  projectId: string,
  ofJobId: string,
  options: { spec?: Record<string, unknown>; name?: string; conversationId?: string } = {},
): Promise<VideoJobView> {
  const body = await request<{ job: VideoJobView }>(
    `/projects/${encodeURIComponent(projectId)}/repair`,
    { method: 'POST', body: JSON.stringify({ ofJobId, ...options }) },
  );
  return body.job;
}

// ── jobs ──────────────────────────────────────────────────────────────────────

export async function getVideoJob(jobId: string): Promise<VideoJobView> {
  const body = await request<{ job: VideoJobView }>(`/jobs/${encodeURIComponent(jobId)}`);
  return body.job;
}

export async function listVideoJobs(projectId?: string): Promise<VideoJobView[]> {
  const suffix = projectId ? `?projectId=${encodeURIComponent(projectId)}` : '';
  const body = await request<{ jobs: VideoJobView[] }>(`/jobs${suffix}`);
  return body.jobs ?? [];
}

export async function cancelVideoJob(jobId: string): Promise<Record<string, unknown>> {
  const body = await request<{ cancellation: Record<string, unknown> }>(
    `/jobs/${encodeURIComponent(jobId)}/cancel`,
    { method: 'POST' },
  );
  return body.cancellation;
}
