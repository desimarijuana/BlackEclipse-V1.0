import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { addToWatchlist, isInWatchlist, removeFromWatchlist } from './watchlist-store';

// The store guards on `typeof window`; the test env is Node, so we install a
// minimal window + localStorage and tear it down afterwards.
const store = new Map<string, string>();

function installWindow() {
  const localStorageMock = {
    getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
    setItem: (k: string, v: string) => void store.set(k, String(v)),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
  };
  (globalThis as unknown as { window: unknown }).window = {
    localStorage: localStorageMock,
    dispatchEvent: () => true,
  };
}

describe('watchlist imperative API', () => {
  beforeEach(() => {
    store.clear();
    installWindow();
  });

  afterEach(() => {
    delete (globalThis as unknown as { window?: unknown }).window;
  });

  it('adds a symbol and reports membership', () => {
    expect(isInWatchlist('NFLX')).toBe(false);
    expect(addToWatchlist('nflx')).toBe('NFLX');
    expect(isInWatchlist('NFLX')).toBe(true);
  });

  it('does not duplicate an existing symbol', () => {
    addToWatchlist('NFLX');
    expect(addToWatchlist('NFLX')).toBeNull();
  });

  it('removes a symbol', () => {
    addToWatchlist('NFLX');
    removeFromWatchlist('nflx');
    expect(isInWatchlist('NFLX')).toBe(false);
  });

  it('ignores blank input', () => {
    expect(addToWatchlist('   ')).toBeNull();
  });
});
