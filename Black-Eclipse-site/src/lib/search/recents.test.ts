import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { useCommandStore } from './store';

// Reset the store between tests.
beforeEach(() => {
  useCommandStore.setState({ recents: [], pendingDestination: null, pendingFundId: null });
});

afterEach(() => {
  useCommandStore.setState({ recents: [], pendingDestination: null, pendingFundId: null });
});

describe('recents', () => {
  it('records a recent search', () => {
    useCommandStore.getState().recordRecent('AAPL');
    expect(useCommandStore.getState().recents.map((r) => r.text)).toContain('AAPL');
  });

  it('removes a single recent search', () => {
    useCommandStore.getState().recordRecent('AAPL');
    useCommandStore.getState().recordRecent('NFP');
    useCommandStore.getState().removeRecent('AAPL');
    const texts = useCommandStore.getState().recents.map((r) => r.text);
    expect(texts).not.toContain('AAPL');
    expect(texts).toContain('NFP');
  });

  it('clears all recents', () => {
    useCommandStore.getState().recordRecent('AAPL');
    useCommandStore.getState().recordRecent('NFP');
    useCommandStore.getState().clearRecents();
    expect(useCommandStore.getState().recents).toEqual([]);
  });
});
