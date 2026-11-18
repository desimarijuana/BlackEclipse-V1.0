// Opt-in integration check against the RUNNING app (not a unit test).
//
// It walks exactly the chain the chat's goal watcher walks — goals → the turn's
// task → the turn's run → that run's persisted tool rows — and renders the
// transcript message the chat would show. Skipped unless BE_LIVE_GOAL names a
// goal id, because it needs the desktop app on http://127.0.0.1:3100.
//
//   BE_LIVE_GOAL=goal_... npx vitest run src/lib/harness/goal-watch.live.test.ts

import { describe, expect, it } from 'vitest';

import { goalActivitiesFromToolRows } from './goal-activity';
import { goalActivityMessage, goalVerdictMessage } from './goal-transcript';

const GOAL_ID = process.env.BE_LIVE_GOAL ?? '';
const BASE = process.env.BE_LIVE_BASE ?? 'http://127.0.0.1:3100';

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
  return (await res.json()) as T;
}

describe.skipIf(!GOAL_ID)('live goal watch', () => {
  it('turns a real goal turn into a chat message with its steps and verdict', async () => {
    const goal = (
      await getJson<{ goal: { id: string; taskId: string; usedTurns: number } }>(
        `/api/goals/${GOAL_ID}`,
      )
    ).goal;
    const task = (
      await getJson<{
        task: {
          status: string;
          assignedRunId: string | null;
          executions?: Array<{ runId: string | null }>;
        };
      }>(`/api/tasks/${encodeURIComponent(goal.taskId)}`)
    ).task;
    const runId =
      task.assignedRunId ??
      (task.executions ?? []).map((execution) => execution.runId).filter(Boolean).pop() ??
      null;
    expect(runId).toBeTruthy();

    const trace = await getJson<{ toolExecutions: Array<{ name: string; ok: boolean }> }>(
      `/api/harness/runs/${encodeURIComponent(String(runId))}/events`,
    );
    const activities = goalActivitiesFromToolRows(trace.toolExecutions);

    const live = goalActivityMessage({
      goalId: goal.id,
      turn: Math.max(1, Number(goal.usedTurns) || 1),
      runId: String(runId),
      status: 'running',
      activities,
    });
    const verdicts = (
      await getJson<{ verdicts: Array<{ turn: number; verdict: string; reason: string }> }>(
        `/api/goals/${GOAL_ID}/verdicts`,
      )
    ).verdicts;
    const last = verdicts[verdicts.length - 1];
    const closed = goalVerdictMessage(
      { goalId: goal.id, turn: last.turn, verdict: last.verdict, reason: last.reason },
      live,
    );

    // eslint-disable-next-line no-console
    console.log(JSON.stringify({
      goal: goal.id,
      task: task.status,
      run: runId,
      steps: activities.map((item) => `${item.label} [${item.status}]`),
      live: { status: live.status, content: live.content },
      closed: { status: closed.status, content: closed.content.slice(0, 120) },
    }, null, 2));

    expect(activities.length).toBeGreaterThan(0);
    expect(live.status).toBe('tool_running');
    expect(closed.activities).toEqual(live.activities);
    expect(closed.status).toBe('completed');
  });
});
