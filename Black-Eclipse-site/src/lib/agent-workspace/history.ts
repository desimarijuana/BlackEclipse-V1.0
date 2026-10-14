// ── Agent Workspace — run history + persistent trace replay ─────────────────
// Read-only front-door fetches for the Agent Workspace's History view. Live runs
// stream over SSE (`stream.ts`); a finished run is reconstructed from the
// persisted event trace the runtime already writes (`GET /runs/{id}/events`).
//
// No second store, no new persistence: the runtime owns the trace.

import { normalizeWorkspaceEvent } from './normalize';
import { applyRunRecordPatch, applyWorkspaceEvents, initialWorkspaceState } from './reducer';
import type { RunRecord } from '@/lib/harness/types';
import type { AgentStatus, AgentWorkspaceState } from './types';

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

/** Fetch the persisted run record (authoritative token/model/context figures). */
export async function fetchRunRecord(runId: string): Promise<RunRecord | null> {
  const res = await fetch(`/api/harness/runs/${encodeURIComponent(runId)}`, {
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) return null;
  const body = (await res.json()) as { run?: RunRecord };
  return body.run ?? null;
}

function statusOf(record: RunRecord): AgentStatus {
  switch (record.status) {
    case 'failed':
      return 'failed';
    case 'cancelled':
      return 'cancelled';
    case 'created':
    case 'running':
      return 'running';
    default:
      return record.finishedAt ? 'completed' : 'running';
  }
}

/**
 * Merge the authoritative run record into a replayed state. The event trace can
 * be incomplete (older runs may not persist `model.completed` / context events),
 * so the record's tokens, model and context budget fill the gaps — and win when
 * present. Pure: mutates and returns the given state.
 */
export function applyRunRecord(state: AgentWorkspaceState, record: RunRecord): AgentWorkspaceState {
  applyRunRecordPatch(state, {
    provider: record.provider ?? undefined,
    model: record.model ?? undefined,
    promptTokens: record.promptTokens,
    completionTokens: record.completionTokens,
    totalTokens: record.totalTokens,
    modelSteps: record.modelSteps,
    toolCalls: record.toolCalls,
    toolErrors: record.toolErrors,
    ...(record.context
      ? {
          windowTokens: record.context.window ?? state.context.windowTokens ?? null,
          windowKnown: record.context.windowKnown,
          turnsKept: record.context.keptTurns,
          turnsDropped: record.context.droppedTurns,
          droppedTokensEstimate: record.context.droppedTokensEstimate,
        }
      : {}),
  });

  const t = state.telemetry;
  const started = timeOf(record.startedAt ?? undefined, 0);
  if (started > 0) t.startedAt = started;
  const finished = timeOf(record.finishedAt ?? undefined, 0);
  if (finished > 0) t.finishedAt = finished;

  state.execution.runId = record.id;
  state.execution.status = statusOf(record);

  return state;
}

/**
 * Rebuild a finished run's workspace: replay its persisted trace (activity,
 * changes, context sources) and fold in the authoritative run record (tokens,
 * model, context window). Used by the History tab and when reopening a chat.
 */
export async function loadRunSnapshot(runId: string): Promise<AgentWorkspaceState> {
  const [trace, record] = await Promise.all([
    fetchRunTrace(runId),
    fetchRunRecord(runId).catch(() => null),
  ]);
  const state = replayTrace(runId, trace.events);
  return record ? applyRunRecord(state, record) : state;
}
