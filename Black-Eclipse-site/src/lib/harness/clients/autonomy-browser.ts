// ─── W4 autonomy — browser client ────────────────────────────────────────────
// Client-safe sibling of `autonomy-client.ts`. The Go /loops endpoints live in
// the Python runtime, which a browser cannot reach directly (and must never
// spawn). Every call therefore goes through the Next front door's API routes,
// which own the runtime handshake + operator token. Importing the server client
// from a `'use client'` component is what pulled `fs`/`child_process` into the
// browser bundle and broke the build.

import type { AutonomyHealth, GoalView, GoalVerdictView, LoopView } from './autonomy-client';

export type { AutonomyHealth, GoalView, GoalVerdictView, LoopView };

async function request<T>(url: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<T> {
  const { timeoutMs = 30_000, ...rest } = init;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      ...rest,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(rest.headers ?? {}),
      },
    });
    const body = (await res.json().catch(() => ({}))) as T & { error?: string };
    if (!res.ok) throw new Error(body?.error || `request failed (${res.status})`);
    return body;
  } finally {
    clearTimeout(timer);
  }
}

function queryString(params: { sessionId?: string; status?: string }): string {
  const query = new URLSearchParams();
  if (params.sessionId) query.set('sessionId', params.sessionId);
  if (params.status) query.set('status', params.status);
  const suffix = query.toString();
  return suffix ? `?${suffix}` : '';
}

// ── Goals ────────────────────────────────────────────────────────────────────

export async function getHealth(): Promise<AutonomyHealth> {
  const body = await request<{ health: AutonomyHealth }>('/api/autonomy/health', { method: 'GET' });
  return body.health;
}

export async function listGoals(params: { sessionId?: string; status?: string } = {}): Promise<GoalView[]> {
  const body = await request<{ goals: GoalView[] }>(`/api/goals${queryString(params)}`, { method: 'GET' });
  return body.goals ?? [];
}

export async function pauseGoal(id: string, reason = ''): Promise<GoalView> {
  const body = await request<{ goal: GoalView }>(`/api/goals/${encodeURIComponent(id)}/pause`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
  return body.goal;
}

export async function resumeGoal(id: string): Promise<GoalView> {
  const body = await request<{ goal: GoalView }>(`/api/goals/${encodeURIComponent(id)}/resume`, {
    method: 'POST',
    body: JSON.stringify({}),
  });
  return body.goal;
}

export async function cancelGoal(id: string): Promise<GoalView> {
  const body = await request<{ goal: GoalView }>(`/api/goals/${encodeURIComponent(id)}/cancel`, {
    method: 'POST',
    body: JSON.stringify({}),
  });
  return body.goal;
}

export async function extendGoal(id: string, turns = 5): Promise<GoalView> {
  const body = await request<{ goal: GoalView }>(`/api/goals/${encodeURIComponent(id)}/extend`, {
    method: 'POST',
    body: JSON.stringify({ turns }),
  });
  return body.goal;
}

export async function reevaluateGoal(id: string): Promise<GoalView> {
  const body = await request<{ goal: GoalView }>(`/api/goals/${encodeURIComponent(id)}/reevaluate`, {
    method: 'POST',
    body: JSON.stringify({}),
    timeoutMs: 180_000,
  });
  return body.goal;
}

export async function goalVerdictHistory(id: string): Promise<GoalVerdictView[]> {
  const body = await request<{ verdicts: GoalVerdictView[] }>(
    `/api/goals/${encodeURIComponent(id)}/verdicts`,
    { method: 'GET' },
  );
  return body.verdicts ?? [];
}

// ── Loops / heartbeats ───────────────────────────────────────────────────────

export async function listLoops(params: { sessionId?: string; status?: string } = {}): Promise<LoopView[]> {
  const body = await request<{ loops: LoopView[] }>(`/api/loops${queryString(params)}`, { method: 'GET' });
  return body.loops ?? [];
}

export async function pauseLoop(id: string, reason = ''): Promise<LoopView> {
  const body = await request<{ loop: LoopView }>(`/api/loops/${encodeURIComponent(id)}/pause`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
  return body.loop;
}

export async function resumeLoop(id: string): Promise<LoopView> {
  const body = await request<{ loop: LoopView }>(`/api/loops/${encodeURIComponent(id)}/resume`, {
    method: 'POST',
    body: JSON.stringify({}),
  });
  return body.loop;
}

export async function cancelLoop(id: string): Promise<LoopView> {
  const body = await request<{ loop: LoopView }>(`/api/loops/${encodeURIComponent(id)}/cancel`, {
    method: 'POST',
    body: JSON.stringify({}),
  });
  return body.loop;
}
