import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { useCommandStore } from './store';

// Reset the subroute channel between tests.
beforeEach(() => {
  useCommandStore.setState({ pendingSubroute: null, subrouteSeq: 0 });
});

afterEach(() => {
  useCommandStore.setState({ pendingSubroute: null, subrouteSeq: 0 });
});

describe('subroute channel', () => {
  it('publishes a request scoped to a tab', () => {
    useCommandStore.getState().requestSubroute('journal', 'analytics');
    const req = useCommandStore.getState().pendingSubroute;
    expect(req?.tab).toBe('journal');
    expect(req?.subroute).toBe('analytics');
    expect(req?.focus).toBeUndefined();
  });

  it('carries an optional focus target', () => {
    useCommandStore.getState().requestSubroute('economics', 'calendar', 'NFP');
    expect(useCommandStore.getState().pendingSubroute?.focus).toBe('NFP');
  });

  it('bumps seq so a repeat request for the same view re-fires', () => {
    useCommandStore.getState().requestSubroute('journal', 'trades');
    const first = useCommandStore.getState().pendingSubroute;
    useCommandStore.getState().requestSubroute('journal', 'trades');
    const second = useCommandStore.getState().pendingSubroute;
    expect(second?.seq).toBeGreaterThan(first?.seq ?? 0);
    // A new object identity is what the hook's subscribe comparison relies on.
    expect(second).not.toBe(first);
  });

  it('clearSubroute clears only the matching tab', () => {
    useCommandStore.getState().requestSubroute('journal', 'trades');
    useCommandStore.getState().clearSubroute('alerts');
    expect(useCommandStore.getState().pendingSubroute?.tab).toBe('journal');

    useCommandStore.getState().clearSubroute('journal');
    expect(useCommandStore.getState().pendingSubroute).toBeNull();
  });
});
