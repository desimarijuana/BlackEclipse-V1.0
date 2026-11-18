import { describe, expect, it } from 'vitest';

import { getTask } from './clients/tasks-browser';
import {
  goalActivitiesFromToolRows,
  goalTurnRunIds,
  splitGoalWatchTargets,
} from './goal-activity';

describe('goalActivitiesFromToolRows', () => {
  it('maps finished, failed and in-flight tool rows to the activity feed shape', () => {
    const items = goalActivitiesFromToolRows([
      { toolCallId: 'call_1', name: 'get_historical_prices', ok: true, durationMs: 812 },
      { toolCallId: 'call_2', name: 'analysis_run', ok: false },
      { toolCallId: 'call_3', name: 'analysis_run', ok: null },
    ]);

    expect(items.map((item) => item.status)).toEqual(['completed', 'failed', 'running']);
    expect(items[0].durationMs).toBe(812);
    expect(items[1].code).toBe('TOOL_ERROR');
    expect(items[0].kind).toBe('tool');
    expect(items[0].label.length).toBeGreaterThan(0);
  });

  it('keeps a retried step as two distinct rows', () => {
    const items = goalActivitiesFromToolRows([
      { name: 'analysis_run', ok: true },
      { name: 'analysis_run', ok: true },
    ]);
    expect(items).toHaveLength(2);
    expect(new Set(items.map((item) => item.id)).size).toBe(2);
  });

  it('skips nameless rows and empty input', () => {
    expect(goalActivitiesFromToolRows([])).toEqual([]);
    expect(goalActivitiesFromToolRows(null)).toEqual([]);
    expect(goalActivitiesFromToolRows([{ name: '   ', ok: true }])).toEqual([]);
  });
});

describe('splitGoalWatchTargets', () => {
  it('sweeps a goal once more when it closes, because that is where the last verdict lives', () => {
    const goals = [
      { id: 'g_open', status: 'active', taskId: 't1' },
      { id: 'g_done', status: 'completed', taskId: 't2' },
      { id: 'g_old', status: 'completed', taskId: 't3' },
    ];
    const { open, closing } = splitGoalWatchTargets(goals, new Set(['g_open', 'g_done']));
    expect(open.map((g) => g.id)).toEqual(['g_open']);
    // `g_done` was watched while open; `g_old` finished before this chat mounted,
    // so opening the chat never replays it.
    expect(closing.map((g) => g.id)).toEqual(['g_done']);
  });

  it('offers the in-flight run id from the attempt count, both neighbours', () => {
    // `executionCount` counts the attempt that is running, so the run may be
    // `_<count>` or `_<count+1>`; the caller keeps the one the runtime knows.
    expect(goalTurnRunIds('task_1', { executionCount: 1 })).toEqual([
      'taskrun_task_1_1',
      'taskrun_task_1_2',
    ]);
    expect(goalTurnRunIds('task_1', { executionCount: 0 })).toEqual(['taskrun_task_1_1']);
    // Once the run finishes the task reports it explicitly; that comes first.
    expect(goalTurnRunIds('task_1', { assignedRunId: 'taskrun_task_1_2', executionCount: 2 })[0])
      .toBe('taskrun_task_1_2');
    expect(goalTurnRunIds('task_1', { executions: [{ runId: null }, { runId: 'taskrun_task_1_2' }] })[0])
      .toBe('taskrun_task_1_2');
    expect(goalTurnRunIds(null, null)).toEqual([]);
  });
});

describe('getTask', () => {
  it('is exported for the watcher', () => {
    expect(typeof getTask).toBe('function');
  });
});
