import { describe, it, expect, beforeEach } from 'vitest';
import {
  clearCache, getCachedState, getInflight, isAssembling, isCacheFresh, setCachedState,
  setInflight, clearInflight, windowKey,
} from './cache';
import type { InvestorEyeState } from './types';

function state(hours: number): InvestorEyeState {
  return {
    generatedAt: new Date().toISOString(),
    windowHours: hours,
    events: [],
    countries: [],
    markets: [],
    status: { provenance: 'LIVE', updatedAt: null, label: 'x', sources: [] },
  };
}

// The cache must be shared across route bundles (globalThis) AND keyed by
// window, so `/risk?hours=24` and `/state?hours=168` cannot overwrite each
// other and a fan-out of routes triggers only one ingestion per window.
describe('investor-eye cache', () => {
  beforeEach(() => clearCache());

  it('keys state by window so windows do not overwrite each other', () => {
    setCachedState(state(24), 24);
    setCachedState(state(168), 168);
    expect(getCachedState(24)?.windowHours).toBe(24);
    expect(getCachedState(168)?.windowHours).toBe(168);
  });

  it('treats an unspecified window as the default 24h key', () => {
    setCachedState(state(24));
    expect(getCachedState()).not.toBeNull();
    expect(windowKey()).toBe('24');
  });

  it('reports freshness per window', () => {
    setCachedState(state(24), 24);
    expect(isCacheFresh(24)).toBe(true);
    expect(isCacheFresh(6)).toBe(false);
  });

  it('returns null for an uncached window', () => {
    expect(getCachedState(720)).toBeNull();
  });

  it('shares one in-flight promise per window', () => {
    const promise = Promise.resolve(state(24));
    setInflight(24, promise);
    expect(getInflight(24)).toBe(promise);
    expect(getInflight(6)).toBeUndefined();
    expect(isAssembling()).toBe(true);
  });

  it('clears an in-flight assembly once finished', () => {
    setInflight(24, Promise.resolve(state(24)));
    clearInflight(24);
    expect(getInflight(24)).toBeUndefined();
    expect(isAssembling()).toBe(false);
  });

  it('clearCache resets both state and in-flight', () => {
    setCachedState(state(24), 24);
    setInflight(24, Promise.resolve(state(24)));
    clearCache();
    expect(getCachedState(24)).toBeNull();
    expect(isAssembling()).toBe(false);
  });

  it('is anchored on globalThis so route bundles share one instance', async () => {
    setCachedState(state(24), 24);
    // Re-importing the module must observe the same global-anchored state.
    const again = await import('./cache');
    expect(again.getCachedState(24)?.windowHours).toBe(24);
  });
});
