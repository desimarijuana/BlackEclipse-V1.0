import { describe, expect, it } from 'vitest';
import {
  seedTaskStatuses,
  selectTaskTransitions,
  type WatchedTask,
} from './task-diff';

function task(partial: Partial<WatchedTask> & { id: string; status: string }): WatchedTask {
  return { title: 'A task', ...partial };
}

describe('seedTaskStatuses', () => {
  it('records every task status without producing notifications', () => {
    const seeded = seedTaskStatuses([
      task({ id: 'a', status: 'COMPLETED' }),
      task({ id: 'b', status: 'IN_PROGRESS' }),
    ]);
    expect([...seeded.entries()]).toEqual([
      ['a', 'COMPLETED'],
      ['b', 'IN_PROGRESS'],
    ]);
  });
});

describe('selectTaskTransitions', () => {
  it('notifies when a known task reaches COMPLETED', () => {
    const prev = seedTaskStatuses([task({ id: 'a', status: 'IN_PROGRESS' })]);
    const { notifications, next } = selectTaskTransitions(
      [task({ id: 'a', status: 'COMPLETED', title: 'Refresh data', completedAt: 'T1' })],
      prev,
    );
    expect(notifications).toHaveLength(1);
    expect(notifications[0]).toMatchObject({
      id: 'task:a:T1',
      taskId: 'a',
      title: 'Task completed',
      body: 'Refresh data',
      failed: false,
    });
    expect(next.get('a')).toBe('COMPLETED');
  });

  it('notifies when a known task reaches FAILED, with the error as body', () => {
    const prev = seedTaskStatuses([task({ id: 'a', status: 'IN_PROGRESS' })]);
    const { notifications } = selectTaskTransitions(
      [task({ id: 'a', status: 'FAILED', error: 'boom', updatedAt: 'T2' })],
      prev,
    );
    expect(notifications).toHaveLength(1);
    expect(notifications[0]).toMatchObject({ id: 'task:a:T2', failed: true, body: 'boom' });
  });

  it('never notifies for a task seen for the first time (even if terminal)', () => {
    const { notifications } = selectTaskTransitions(
      [task({ id: 'new', status: 'COMPLETED', completedAt: 'T1' })],
      new Map(),
    );
    expect(notifications).toEqual([]);
  });

  it('ignores non-terminal moves and unchanged statuses', () => {
    const prev = seedTaskStatuses([
      task({ id: 'a', status: 'TODO' }),
      task({ id: 'b', status: 'COMPLETED' }),
    ]);
    const { notifications } = selectTaskTransitions(
      [
        task({ id: 'a', status: 'IN_PROGRESS' }),
        task({ id: 'b', status: 'COMPLETED' }),
      ],
      prev,
    );
    expect(notifications).toEqual([]);
  });

  it('re-notifies when a reopened task completes again (new stamp → new id)', () => {
    const prev = seedTaskStatuses([task({ id: 'a', status: 'COMPLETED' })]);
    const reopened = selectTaskTransitions([task({ id: 'a', status: 'IN_PROGRESS' })], prev);
    expect(reopened.notifications).toEqual([]);
    const redone = selectTaskTransitions(
      [task({ id: 'a', status: 'COMPLETED', completedAt: 'T9' })],
      reopened.next,
    );
    expect(redone.notifications[0]?.id).toBe('task:a:T9');
  });

  it('drops vanished tasks from the next map instead of tracking them forever', () => {
    const prev = seedTaskStatuses([
      task({ id: 'a', status: 'TODO' }),
      task({ id: 'gone', status: 'TODO' }),
    ]);
    const { next } = selectTaskTransitions([task({ id: 'a', status: 'TODO' })], prev);
    expect(next.has('gone')).toBe(false);
  });

  it('falls back to the status in the id when no timestamps exist', () => {
    const prev = seedTaskStatuses([task({ id: 'a', status: 'TODO' })]);
    const { notifications } = selectTaskTransitions([task({ id: 'a', status: 'COMPLETED' })], prev);
    expect(notifications[0]?.id).toBe('task:a:COMPLETED');
  });
});
