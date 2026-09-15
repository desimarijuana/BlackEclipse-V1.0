import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { useCommandStore, visitRecencyScore } from './store';

// Reset the store between tests.
beforeEach(() => {
  useCommandStore.setState({ recents: [], pins: [], visits: [], collapsedGroups: [], pendingDestination: null, pendingFundId: null });
});

afterEach(() => {
  useCommandStore.setState({ recents: [], pins: [], visits: [], collapsedGroups: [], pendingDestination: null, pendingFundId: null });
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

describe('pins', () => {
  const aapl = { id: 'eq-aapl', title: 'Apple Inc.', symbol: 'AAPL', kind: 'security', tab: 'chart', params: { symbol: 'AAPL' } };

  it('toggles a pin on and off', () => {
    useCommandStore.getState().togglePin(aapl);
    expect(useCommandStore.getState().isPinned('eq-aapl')).toBe(true);
    expect(useCommandStore.getState().pins).toHaveLength(1);

    useCommandStore.getState().togglePin(aapl);
    expect(useCommandStore.getState().isPinned('eq-aapl')).toBe(false);
    expect(useCommandStore.getState().pins).toEqual([]);
  });

  it('removes a pin by id', () => {
    useCommandStore.getState().togglePin(aapl);
    useCommandStore.getState().removePin('eq-aapl');
    expect(useCommandStore.getState().pins).toEqual([]);
  });
});

describe('group collapse', () => {
  it('toggles a group key', () => {
    useCommandStore.getState().toggleGroup('security');
    expect(useCommandStore.getState().collapsedGroups).toContain('security');
    useCommandStore.getState().toggleGroup('security');
    expect(useCommandStore.getState().collapsedGroups).not.toContain('security');
  });
});

describe('visits', () => {
  it('records a visit and scores it as recent', () => {
    useCommandStore.getState().recordVisit('eq-aapl');
    const visits = useCommandStore.getState().visits;
    expect(visits[0].id).toBe('eq-aapl');
    expect(visitRecencyScore(visits, 'eq-aapl')).toBeGreaterThan(0.9);
  });

  it('scores unknown ids as zero', () => {
    expect(visitRecencyScore([], 'nope')).toBe(0);
  });

  it('moves a repeated visit to the front without duplicating', () => {
    useCommandStore.getState().recordVisit('a');
    useCommandStore.getState().recordVisit('b');
    useCommandStore.getState().recordVisit('a');
    const visits = useCommandStore.getState().visits;
    expect(visits.map((v) => v.id)).toEqual(['a', 'b']);
  });
});
