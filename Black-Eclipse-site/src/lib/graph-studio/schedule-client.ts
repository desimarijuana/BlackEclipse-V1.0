// ── Schedule client ─────────────────────────────────────────────────────────
// Browser-side wrappers over the schedule routes. A schedule is user config, so
// it lives in JDDS (Prisma) — not in the runtime's run store.

export interface WorkflowSchedule {
  id: string;
  workflowId: string;
  name: string;
  cron: string;
  timezone: string;
  enabled: boolean;
  catchUp: 'skip' | 'coalesce';
  version: number | null;
  lastRunAt: string | null;
  lastRunId: string | null;
  lastStatus: string | null;
  lastError: string | null;
  nextRunAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export class ScheduleApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'ScheduleApiError';
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ScheduleApiError((data as { error?: string }).error ?? `Request failed (${res.status})`, res.status);
  return data as T;
}

export async function listSchedules(workflowId: string): Promise<WorkflowSchedule[]> {
  const data = await request<{ schedules: WorkflowSchedule[] }>(`/api/workflows/${workflowId}/schedules`);
  return data.schedules ?? [];
}

export async function createSchedule(
  workflowId: string,
  input: { name: string; cron: string; timezone?: string; catchUp?: 'skip' | 'coalesce' },
): Promise<WorkflowSchedule> {
  const data = await request<{ schedule: WorkflowSchedule }>(`/api/workflows/${workflowId}/schedules`, {
    method: 'POST',
    body: JSON.stringify(input),
  });
  return data.schedule;
}

export async function updateSchedule(id: string, patch: Partial<WorkflowSchedule>): Promise<WorkflowSchedule> {
  const data = await request<{ schedule: WorkflowSchedule }>(`/api/workflow-schedules/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  });
  return data.schedule;
}

export async function deleteSchedule(id: string): Promise<void> {
  await request(`/api/workflow-schedules/${id}`, { method: 'DELETE' });
}

export async function tickSchedules(): Promise<number> {
  const data = await request<{ outcomes: unknown[] }>('/api/workflow-schedules/tick', { method: 'POST' });
  return data.outcomes?.length ?? 0;
}
