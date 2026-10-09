import { describe, expect, it } from 'vitest';
import { buildBreakdown, resolveContextWindow, sourceColor, usagePercent } from './context-usage';
import type { ContextSource } from './types';

const catalog = {
  openai: { id: 'openai', contextWindow: 128000, modelWindows: { 'gpt-5': 400000, 'gpt-5-mini': null } },
  local: { id: 'local', contextWindow: null },
};

describe('resolveContextWindow', () => {
  it('prefers the per-model window over the provider default', () => {
    expect(resolveContextWindow(catalog, 'openai', 'gpt-5')).toBe(400000);
  });

  it('falls back to the provider default when the model window is unknown', () => {
    expect(resolveContextWindow(catalog, 'openai', 'gpt-5-mini')).toBe(128000);
    expect(resolveContextWindow(catalog, 'openai', 'unknown-model')).toBe(128000);
  });

  it('returns null for an unknown provider or a provider with no declared window', () => {
    expect(resolveContextWindow(catalog, 'missing', 'x')).toBeNull();
    expect(resolveContextWindow(catalog, 'local', 'x')).toBeNull();
    expect(resolveContextWindow(catalog, undefined, undefined)).toBeNull();
  });
});

describe('usagePercent', () => {
  it('computes a clamped percentage', () => {
    expect(usagePercent(250, 1000)).toBe(25);
    expect(usagePercent(2000, 1000)).toBe(100);
  });

  it('returns null when the window is unknown or non-positive (never fabricates)', () => {
    expect(usagePercent(250, null)).toBeNull();
    expect(usagePercent(250, 0)).toBeNull();
    expect(usagePercent(250, 1000, false)).toBeNull();
    expect(usagePercent(undefined, 1000)).toBeNull();
  });
});

describe('buildBreakdown', () => {
  const sources: ContextSource[] = [
    { id: 'system', source: 'system', tokens: 1000 },
    { id: 'skills', source: 'skills', tokens: 1000 },
    { id: 'empty', source: 'history', tokens: 0 },
  ];

  it('segments relative to the window when one is known', () => {
    const segs = buildBreakdown(sources, 10000);
    expect(segs).toHaveLength(2);
    expect(segs.map((s) => s.label)).toEqual(['system', 'skills']);
    expect(segs[0].percent).toBeCloseTo(10);
  });

  it('falls back to the reported total when the window is unknown', () => {
    const segs = buildBreakdown(sources, null);
    expect(segs).toHaveLength(2);
    expect(segs[0].percent).toBeCloseTo(50);
  });

  it('returns [] when no source has a positive token estimate', () => {
    expect(buildBreakdown([{ id: 'x', tokens: 0 }], 1000)).toEqual([]);
    expect(buildBreakdown([], 1000)).toEqual([]);
  });

  it('reuses a bounded color palette cyclically', () => {
    expect(sourceColor(0)).toBe(sourceColor(8));
    expect(sourceColor(0)).not.toBe(sourceColor(1));
  });
});
