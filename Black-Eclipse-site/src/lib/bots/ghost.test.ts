import { describe, expect, it } from 'vitest';
import {
  DEFAULT_GHOST_SPEC,
  GHOST_ACCESSORY_COUNT,
  GHOST_EYE_COUNT,
  GHOST_MOUTH_COUNT,
  GHOST_PATTERN_COUNT,
  GHOST_VARIANT_COUNT,
  ghostSpecFromId,
  ghostSpecKey,
  hashString,
  mulberry32,
  normalizeGhostSpec,
  randomGhostSpec,
} from './ghost';

describe('hashString / mulberry32', () => {
  it('is stable for the same input', () => {
    expect(hashString('bot-1')).toBe(hashString('bot-1'));
    expect(hashString('bot-1')).not.toBe(hashString('bot-2'));
  });

  it('produces a deterministic sequence in [0,1)', () => {
    const a = mulberry32(42);
    const b = mulberry32(42);
    for (let i = 0; i < 20; i += 1) {
      const x = a();
      expect(x).toBe(b());
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThan(1);
    }
  });
});

describe('randomGhostSpec', () => {
  it('keeps every index inside its authored range', () => {
    for (let seed = 0; seed < 200; seed += 1) {
      const spec = randomGhostSpec(mulberry32(seed));
      expect(spec.variant).toBeGreaterThanOrEqual(0);
      expect(spec.variant).toBeLessThan(GHOST_VARIANT_COUNT);
      expect(spec.eyes).toBeGreaterThanOrEqual(0);
      expect(spec.eyes).toBeLessThan(GHOST_EYE_COUNT);
      expect(spec.mouth).toBeGreaterThanOrEqual(0);
      expect(spec.mouth).toBeLessThan(GHOST_MOUTH_COUNT);
      expect(spec.accessory).toBeGreaterThanOrEqual(0);
      expect(spec.accessory).toBeLessThan(GHOST_ACCESSORY_COUNT);
      expect(spec.pattern).toBeGreaterThanOrEqual(0);
      expect(spec.pattern).toBeLessThan(GHOST_PATTERN_COUNT);
      expect(spec.bodyColor).toMatch(/^#[0-9a-f]{6}$/);
      expect(spec.accentColor).toMatch(/^#[0-9a-f]{6}$/);
    }
  });

  it('is deterministic for a fixed seed', () => {
    expect(randomGhostSpec(mulberry32(7))).toEqual(randomGhostSpec(mulberry32(7)));
  });
});

describe('ghostSpecFromId', () => {
  it('is stable and id-dependent', () => {
    expect(ghostSpecFromId('abc')).toEqual(ghostSpecFromId('abc'));
    expect(ghostSpecKey(ghostSpecFromId('abc'))).not.toBe(ghostSpecKey(ghostSpecFromId('xyz')));
  });

  it('falls back to the default for an empty id', () => {
    expect(ghostSpecFromId('')).toEqual(DEFAULT_GHOST_SPEC);
  });
});

describe('normalizeGhostSpec', () => {
  it('rejects out-of-range indices and bad colors', () => {
    const spec = normalizeGhostSpec({
      variant: 99,
      eyes: -1,
      mouth: 1.5,
      accessory: 999,
      pattern: 2,
      bodyColor: 'not-a-color',
      accentColor: '#AABBCC',
    });
    expect(spec.variant).toBe(DEFAULT_GHOST_SPEC.variant);
    expect(spec.eyes).toBe(DEFAULT_GHOST_SPEC.eyes);
    expect(spec.mouth).toBe(1);
    expect(spec.accessory).toBe(DEFAULT_GHOST_SPEC.accessory);
    expect(spec.pattern).toBe(2);
    expect(spec.bodyColor).toBe(DEFAULT_GHOST_SPEC.bodyColor);
    expect(spec.accentColor).toBe('#aabbcc');
  });

  it('returns the default for non-object input', () => {
    expect(normalizeGhostSpec(null)).toEqual(DEFAULT_GHOST_SPEC);
    expect(normalizeGhostSpec('nope')).toEqual(DEFAULT_GHOST_SPEC);
  });
});
