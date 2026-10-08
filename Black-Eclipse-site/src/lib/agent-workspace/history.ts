// ── Agent Workspace — run history + persistent trace replay ─────────────────
// Read-only front-door fetches for the Agent Workspace's History view. Live runs
// stream over SSE (`stream.ts`); a finished run is reconstructed from the
// persisted event trace the runtime already writes (`GET /runs/{id}/events`).
//
// No second store, no new persistence: the runtime owns the trace.

import { normalizeWorkspaceEvent } from './normalize';
import { applyWorkspaceEvents, initialWorkspaceState } from './reducer';
import type { AgentWorkspaceState } from './types';

export interface WorkspaceRunRow {
  id: string;
  agentId?: string;
  status?: string;
  provider?: string | null;
  model?: string | null;
  modelSteps?: number;
  toolCalls?: number;
  toolErrors?: number;
  totalTokens?: number;
  output?: string | null;
  createdAt?: string;
  updatedAt?: string;
  startedAt?: string | null;
  finishedAt?: string | null;
}

export interface TraceEvent {
  id?: string;
  runId?: string;
  type: string;
  seq?: number;
  at?: string;
  data?: Record<string, unknown>;
}

/** A persisted tool execution row (its `text` is the bounded tool output). */
export interface ToolExecutionRow {
  toolCallId?: string;
  name?: string;
  ok?: boolean;
  durationMs?: number;
  text?: string;
  error?: string | null;
}

export async function listWorkspaceRuns(): Promise<WorkspaceRunRow[]> {
  const res = await fetch('/api/harness/runs', { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`runs unavailable (${res.status})`);
  const body = (await res.json()) as { runs?: WorkspaceRunRow[] };
  return body.runs ?? [];
}

export async function fetchRunTrace(
  runId: string,
): Promise<{ events: TraceEvent[]; toolExecutions: ToolExecutionRow[] }> {
  const res = await fetch(`/api/harness/runs/${encodeURIComponent(runId)}/events`, {
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) throw new Error(`trace unavailable (${res.status})`);
  const body = (await res.json()) as { events?: TraceEvent[]; toolExecutions?: ToolExecutionRow[] };
  return { events: body.events ?? [], toolExecutions: body.toolExecutions ?? [] };
}

function timeOf(iso: string | undefined, fallback: number): number {
  if (!iso) return fallback;
  const parsed = Date.parse(iso);
  return Number.isFinite(parsed) ? parsed : fallback;
}

/**
 * Reconstruct a workspace state from a persisted trace. Pure + deterministic so
 * it is unit-testable; the caller may render the result directly.
 */
export function replayTrace(runId: string, events: TraceEvent[]): AgentWorkspaceState {
  const state = initialWorkspaceState(runId);
  const ordered = [...events].sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0));
  for (const ev of ordered) {
    if (!ev.type) continue;
    const at = timeOf(ev.at, Date.now());
    const normalized = normalizeWorkspaceEvent(ev.type, ev.data ?? {}, at);
    applyWorkspaceEvents(state, normalized);
  }
  return state;
}
