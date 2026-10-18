// ── Graph Studio client — workflow documents over /api/workflows ─────────────
// Thin browser-side wrappers. No workflow logic lives here; the routes and the
// Prisma store are the authority. Errors surface as thrown `WorkflowApiError`
// so the UI can show a real message instead of an empty canvas.

import { readWorkflowIR } from './migrations';
import type { WorkflowIR } from './types';

export interface WorkflowSummary {
  id: string;
  name: string;
  description: string;
  tags: string[];
  owner: string;
  currentVersion: number;
  archived: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface WorkflowRecord extends WorkflowSummary {
  ir: WorkflowIR;
  contentHash: string;
  version: number;
}

export interface VersionSummary {
  version: number;
  contentHash: string;
  note: string | null;
  createdAt: string;
}

export class WorkflowApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'WorkflowApiError';
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new WorkflowApiError((data as { error?: string }).error ?? `Request failed (${res.status})`, res.status);
  }
  return data as T;
}

export async function listWorkflows(): Promise<WorkflowSummary[]> {
  const data = await request<{ workflows: WorkflowSummary[] }>('/api/workflows');
  return data.workflows ?? [];
}

export async function createWorkflow(input: { name: string; description?: string; tags?: string[]; ir: WorkflowIR }): Promise<WorkflowRecord> {
  const data = await request<{ workflow: WorkflowRecord }>('/api/workflows', {
    method: 'POST',
    body: JSON.stringify(input),
  });
  return { ...data.workflow, ir: readWorkflowIR(data.workflow.ir) };
}

export async function getWorkflow(id: string, version?: number): Promise<WorkflowRecord> {
  const qs = version ? `?version=${version}` : '';
  const data = await request<{ workflow: WorkflowRecord }>(`/api/workflows/${id}${qs}`);
  return { ...data.workflow, ir: readWorkflowIR(data.workflow.ir) };
}

export async function saveWorkflow(id: string, ir: WorkflowIR, note?: string): Promise<WorkflowRecord> {
  const data = await request<{ workflow: WorkflowRecord }>(`/api/workflows/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ ir, note }),
  });
  return { ...data.workflow, ir: readWorkflowIR(data.workflow.ir) };
}

export async function deleteWorkflow(id: string): Promise<void> {
  await request(`/api/workflows/${id}`, { method: 'DELETE' });
}

export async function listVersions(id: string): Promise<VersionSummary[]> {
  const data = await request<{ versions: VersionSummary[] }>(`/api/workflows/${id}/versions`);
  return data.versions ?? [];
}
