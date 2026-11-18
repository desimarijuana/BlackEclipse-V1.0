// ── Goal activity ─────────────────────────────────────────────────────────────
// A goal turn runs as a background TASK, not as a chat run, so it never reaches
// the chat's SSE stream. The chat still has to show what the turn is doing: this
// module turns the persisted tool-execution rows of the turn's run into the SAME
// `ActivityItem` shape the live chat feed renders, so one component displays
// both. Pure + deterministic (no fetching, no React) so it is unit-testable.

import { toolLabel, type ActivityItem } from '@/lib/agent/response-model';

/** The minimal goal shape the watch selection needs. */
export interface GoalWatchRow {
  id: string;
  status: string;
  usedTurns?: number | null;
  taskId?: string | null;
}

const OPEN_STATUSES = new Set(['active', 'paused', 'blocked']);

/**
 * Which goals to watch this poll.
 *
 * `open` are worked now. `closing` are goals that WERE open and have since left
 * the open set — the turn that ends a goal (`done`, `blocked`, `cancelled`)
 * records its verdict and flips the status in the same instant, so a watcher
 * that only looks at open goals never sees the verdict that actually finished
 * the goal. They are inspected once more, then dropped by the caller.
 */
export function splitGoalWatchTargets<T extends GoalWatchRow>(
  goals: readonly T[],
  watchedOpen: ReadonlySet<string>,
): { open: T[]; closing: T[] } {
  const open: T[] = [];
  const closing: T[] = [];
  for (const goal of goals) {
    if (OPEN_STATUSES.has(goal.status)) open.push(goal);
    else if (watchedOpen.has(goal.id)) closing.push(goal);
  }
  return { open, closing };
}

/** The task fields that identify its turn's run. */
export interface GoalTaskRunRow {
  assignedRunId?: string | null;
  executionCount?: number | null;
  executions?: Array<{ runId?: string | null }> | null;
}

/**
 * The run ids a goal turn may be using, most specific first.
 *
 * While the turn is running the task exposes neither `assignedRunId` nor its
 * execution rows — both are written when the run finishes — and `executionCount`
 * already counts the in-flight attempt. Task runs are named
 * `taskrun_<taskId>_<attempt>`, so both neighbours are offered and the caller
 * keeps the first that the runtime knows.
 */
export function goalTurnRunIds(
  taskId: string | null | undefined,
  task: GoalTaskRunRow | null | undefined,
): string[] {
  const ids: Array<string | null> = [];
  ids.push(task?.assignedRunId ?? null);
  for (const execution of task?.executions ?? []) ids.push(execution.runId ?? null);
  if (taskId) {
    const count = Math.max(0, Number(task?.executionCount ?? 0));
    if (count > 0) ids.push(`taskrun_${taskId}_${count}`);
    ids.push(`taskrun_${taskId}_${count + 1}`);
  }
  return [...new Set(ids.filter((id): id is string => Boolean(id)))];
}

/** One persisted tool-execution row (`GET /api/harness/runs/{id}/events`). */
export interface GoalToolRow {
  toolCallId?: string | null;
  name?: string | null;
  /** `true` finished, `false` failed, absent/null still running. */
  ok?: boolean | null;
  durationMs?: number | null;
}

/**
 * Map tool rows to activity items, oldest first.
 *
 * A retried step repeats the tool name; the index keeps ids unique so two calls
 * read as two steps instead of one row hiding the other. A row with no name is
 * skipped — nothing honest can be labelled for it.
 */
export function goalActivitiesFromToolRows(
  rows: readonly GoalToolRow[] | null | undefined,
): ActivityItem[] {
  const out: ActivityItem[] = [];
  const seen = new Map<string, number>();
  (rows ?? []).forEach((row, index) => {
    const name = String(row?.name ?? '').trim();
    if (!name) return;
    const base = String(row?.toolCallId ?? `${name}-${index}`);
    const repeat = (seen.get(base) ?? 0) + 1;
    seen.set(base, repeat);
    const failed = row.ok === false;
    out.push({
      id: repeat === 1 ? base : `${base}#${repeat}`,
      kind: 'tool',
      name,
      label: toolLabel(name),
      status: row.ok === true ? 'completed' : failed ? 'failed' : 'running',
      ...(typeof row.durationMs === 'number' ? { durationMs: row.durationMs } : {}),
      ...(failed ? { code: 'TOOL_ERROR' } : {}),
    });
  });
  return out;
}
