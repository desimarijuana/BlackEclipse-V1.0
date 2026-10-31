// ── Schedule client ─────────────────────────────────────────────────────────
// Browser-side wrappers over the schedule routes. A schedule is user config, so
// it lives in JDDS (Prisma) — not in the runtime's run store.

export interface WorkflowSchedule {
  id: string;
  workflowId: string;
  /** The trigger.schedule node this schedule is attached to, when there is one. */
  nodeId: string | null;
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

/** Fired after any schedule mutation so the canvas can refresh node summaries. */
export const SCHEDULES_CHANGED_EVENT = 'eclipse:schedules-changed';

function notifySchedulesChanged(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(SCHEDULES_CHANGED_EVENT));
  }
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
  input: {
    nodeId?: string | null;
    name: string;
    cron: string;
    timezone?: string;
    catchUp?: 'skip' | 'coalesce';
    version?: number | null;
  },
): Promise<WorkflowSchedule> {
  const data = await request<{ schedule: WorkflowSchedule }>(`/api/workflows/${workflowId}/schedules`, {
    method: 'POST',
    body: JSON.stringify(input),
  });
  notifySchedulesChanged();
  return data.schedule;
}

export async function updateSchedule(id: string, patch: Partial<WorkflowSchedule>): Promise<WorkflowSchedule> {
  const data = await request<{ schedule: WorkflowSchedule }>(`/api/workflow-schedules/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  });
  notifySchedulesChanged();
  return data.schedule;
}

export async function deleteSchedule(id: string): Promise<void> {
  await request(`/api/workflow-schedules/${id}`, { method: 'DELETE' });
  notifySchedulesChanged();
}

/** Fire a schedule immediately. Same read-only test envelope as a timed fire. */
export async function runScheduleNow(id: string): Promise<void> {
  await request(`/api/workflow-schedules/${id}/run`, { method: 'POST' });
  notifySchedulesChanged();
}

export async function tickSchedules(): Promise<number> {
  const data = await request<{ outcomes: unknown[] }>('/api/workflow-schedules/tick', { method: 'POST' });
  return data.outcomes?.length ?? 0;
}
