import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  isKnownMarket,
  getUserMarket,
  setUserMarket,
  resolveUserMarket,
} from './user-market';

function makeStorage() {
  const store = new Map<string, string>();
  return {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
  };
}

describe('user market preference', () => {
  beforeEach(() => {
    vi.stubGlobal('window', { localStorage: makeStorage() });
    vi.stubGlobal('navigator', { language: 'en-US' });
  });

  it('recognizes only supported heatmap markets', () => {
    expect(isKnownMarket('US')).toBe(true);
    expect(isKnownMarket('crypto')).toBe(true);
    expect(isKnownMarket('PK')).toBe(true);
    expect(isKnownMarket('ZZ')).toBe(false);
  });

  it('round-trips an explicit market choice', () => {
    expect(getUserMarket()).toBeNull();
    setUserMarket('pk');
    expect(getUserMarket()).toBe('PK');
  });

  it('ignores an unknown market when storing', () => {
    setUserMarket('ZZ');
    expect(getUserMarket()).toBeNull();
  });

  it('prefers an explicit hint over stored and locale', () => {
    setUserMarket('PK');
    expect(resolveUserMarket('IN')).toBe('IN');
  });

  it('falls back to the stored choice, then the locale, then US', () => {
    expect(resolveUserMarket()).toBe('US');
    setUserMarket('IN');
    expect(resolveUserMarket()).toBe('IN');

    vi.stubGlobal('window', { localStorage: makeStorage() });
    vi.stubGlobal('navigator', { language: 'en-PK' });
    expect(resolveUserMarket()).toBe('PK');
  });
});
