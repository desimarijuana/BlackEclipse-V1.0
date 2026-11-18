// ── Goal activity ─────────────────────────────────────────────────────────────
// A goal turn runs as a background TASK, not as a chat run, so it never reaches
// the chat's SSE stream. The chat still has to show what the turn is doing: this
// module turns the persisted tool-execution rows of the turn's run into the SAME
// `ActivityItem` shape the live chat feed renders, so one component displays
// both. Pure + deterministic (no fetching, no React) so it is unit-testable.

import { toolLabel, type ActivityItem } from '@/lib/agent/response-model';

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
