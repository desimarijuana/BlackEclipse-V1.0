import { describe, expect, it } from 'vitest';
import {
  applyDelegationEvent,
  delegationCost,
  dropProvisionalDelegation,
  mergeChild,
  startProvisionalDelegation,
} from './delegation-reducer';
import type { DelegationChildView, DelegationView } from './response-model';

const start: DelegationView = {
  delegationId: 'dlg_1',
  aggregate: 'list',
  strategy: 'split',
  done: false,
  children: [
    { childIndex: 0, goal: 'Review AAPL', status: 'running', agentId: 'eclipse-agent' },
    { childIndex: 1, goal: 'Review MSFT', status: 'running', agentId: 'eclipse-agent' },
  ],
};

describe('applyDelegationEvent', () => {
  it('starts a fan-out with one row per part', () => {
    const state = applyDelegationEvent([], { kind: 'delegation_start', delegation: start });
    expect(state).toHaveLength(1);
    expect(state[0].children.map((c) => c.goal)).toEqual(['Review AAPL', 'Review MSFT']);
  });

  it('updates a row in place rather than duplicating it', () => {
    const state = applyDelegationEvent([start], {
      kind: 'delegation_progress',
      child: {
        delegationId: 'dlg_1',
        childIndex: 0,
        goal: 'Review AAPL',
        status: 'running',
        activity: 'Reading the filing',
        step: 3,
        maxSteps: 10,
        tokens: 1_200,
        costUsd: 0.12,
        recent: ['Starting', 'Reading the filing'],
      },
    });
    expect(state[0].children).toHaveLength(2);
    expect(state[0].children[0]).toMatchObject({
      activity: 'Reading the filing',
      recent: ['Starting', 'Reading the filing'],
      step: 3,
      maxSteps: 10,
      costUsd: 0.12,
    });
  });

  it('never downgrades a terminal part back to running', () => {
    const done = applyDelegationEvent([start], {
      kind: 'delegation_child',
      delegationId: 'dlg_1',
      childIndex: 0,
      status: 'completed',
      tokens: 500,
    });
    const late = applyDelegationEvent(done, {
      kind: 'delegation_progress',
      child: { delegationId: 'dlg_1', childIndex: 0, goal: '', status: 'running' },
    });
    expect(late[0].children[0].status).toBe('completed');
    expect(late[0].children[0].tokens).toBe(500);
  });

  it('keeps a known goal when a snapshot omits it', () => {
    const state = applyDelegationEvent([start], {
      kind: 'delegation_progress',
      child: { delegationId: 'dlg_1', childIndex: 0, goal: '', status: 'running' },
    });
    expect(state[0].children[0].goal).toBe('Review AAPL');
  });

  it('records the aggregated totals and done state', () => {
    const state = applyDelegationEvent([start], {
      kind: 'delegation_done',
      delegationId: 'dlg_1',
      droppedClaims: 2,
      tokens: 9_000,
      winner: 1,
    });
    expect(state[0]).toMatchObject({
      done: true, droppedClaims: 2, tokens: 9_000, winner: 1,
    });
  });

  it('keeps a best-of winner of part 0 (not treated as absent)', () => {
    const bestOf: DelegationView = { ...start, strategy: 'best_of' };
    const state = applyDelegationEvent([bestOf], {
      kind: 'delegation_done',
      delegationId: 'dlg_1',
      winner: 0,
    });
    expect(state[0].winner).toBe(0);
  });

  it('appears from progress even when the start frame was missed', () => {
    const state = applyDelegationEvent([], {
      kind: 'delegation_progress',
      child: { delegationId: 'dlg_x', childIndex: 1, goal: 'Late part', status: 'running' },
    });
    expect(state).toHaveLength(1);
    expect(state[0].children[0].goal).toBe('Late part');
  });
});

describe('provisional card', () => {
  it('shows a placeholder, then the real fan-out replaces it', () => {
    let state = startProvisionalDelegation([], 'call_1');
    expect(state).toHaveLength(1);
    expect(state[0]).toMatchObject({ title: 'Agents starting', children: [] });

    state = applyDelegationEvent(state, { kind: 'delegation_start', delegation: start });
    expect(state).toHaveLength(1);
    expect(state[0].delegationId).toBe('dlg_1');
    expect(state[0].children).toHaveLength(2);
  });

  it('drops the placeholder when the call is refused or the turn ends', () => {
    const pending = startProvisionalDelegation([], 'call_1');
    expect(dropProvisionalDelegation(pending)).toEqual([]);
    // A real card is left alone.
    expect(dropProvisionalDelegation([start])).toEqual([start]);
  });
});

describe('mergeChild', () => {
  it('preserves a terminal status', () => {
    const previous: DelegationChildView = { childIndex: 0, goal: 'g', status: 'failed' };
    const merged = mergeChild(previous, { childIndex: 0, goal: 'g', status: 'running' });
    expect(merged.status).toBe('failed');
  });
});

describe('delegationCost', () => {
  it('sums known prices and reports an unknown one honestly', () => {
    const children: DelegationChildView[] = [
      { childIndex: 0, goal: 'a', status: 'completed', tokens: 100, costUsd: 0.12 },
      { childIndex: 1, goal: 'b', status: 'running', tokens: 50, costUsd: null },
    ];
    const result = delegationCost(children);
    expect(result.total).toBeCloseTo(0.12);
    expect(result.unknown).toBe(true);
  });

  it('does not treat a free (0) price as unknown', () => {
    const result = delegationCost([
      { childIndex: 0, goal: 'a', status: 'completed', tokens: 100, costUsd: 0 },
    ]);
    expect(result).toEqual({ total: 0, unknown: false });
  });

  it('marks a completed but unpriced part unknown, a refused one not', () => {
    const completed = delegationCost([
      { childIndex: 0, goal: 'a', status: 'completed', tokens: 0, costUsd: null },
    ]);
    expect(completed.unknown).toBe(true);
    const refused = delegationCost([
      { childIndex: 0, goal: 'a', status: 'refused', costUsd: null },
    ]);
    expect(refused).toEqual({ total: 0, unknown: false });
  });
});
