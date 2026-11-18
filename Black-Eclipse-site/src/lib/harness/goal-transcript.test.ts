import { describe, expect, it } from 'vitest';

import { goalActivityMessage, goalTurnMessageId, goalVerdictMessage } from './goal-transcript';
import type { GoalTurnActivity } from './use-goal-verdict-watch';

const snapshot: GoalTurnActivity = {
  goalId: 'goal_1',
  turn: 2,
  runId: 'run_1',
  status: 'running',
  activities: [
    { id: 'a', kind: 'tool', name: 'analysis_run', label: 'analysis_run', status: 'completed' },
  ],
};

describe('goal transcript messages', () => {
  it('uses one id per goal turn', () => {
    expect(goalTurnMessageId('goal_1', 2)).toBe('goal-goal_1-2');
    expect(goalActivityMessage(snapshot).id).toBe(goalVerdictMessage({
      goalId: 'goal_1', turn: 2, verdict: 'continue', reason: 'more evidence needed',
    }).id);
  });

  it('renders a live step card with the run\'s activities', () => {
    const message = goalActivityMessage(snapshot);
    expect(message.status).toBe('tool_running');
    expect(message.content).toContain('turn 2');
    expect(message.activities?.map((item) => item.name)).toEqual(['analysis_run']);
  });

  it('maps a finished or failed turn to a terminal chat status', () => {
    expect(goalActivityMessage({ ...snapshot, status: 'completed' }).status).toBe('completed');
    expect(goalActivityMessage({ ...snapshot, status: 'failed' }).status).toBe('error');
  });

  it('keeps the steps when the verdict closes the same turn', () => {
    const live = goalActivityMessage(snapshot);
    const closed = goalVerdictMessage(
      { goalId: 'goal_1', turn: 2, verdict: 'continue', reason: 'more evidence needed' },
      live,
    );
    expect(closed.status).toBe('completed');
    expect(closed.content).toContain('continue');
    expect(closed.content).toContain('more evidence needed');
    expect(closed.activities).toEqual(live.activities);

    const blocked = goalVerdictMessage(
      { goalId: 'goal_1', turn: 2, verdict: 'blocked', reason: 'turn budget exhausted' },
      live,
    );
    expect(blocked.status).toBe('error');
  });
});
