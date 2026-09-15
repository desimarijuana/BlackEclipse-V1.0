import { describe, it, expect } from 'vitest';
import {
  AURORA_PALETTE_KEY,
  AURORA_PRESETS,
  DEFAULT_AURORA_PALETTE,
  defaultAuroraPalette,
  isValidHex,
  paletteMatchesPreset,
  parseAuroraPalette,
  safeHex,
  type AuroraPalette,
} from './theme';
import { resolveAuroraVisuals } from '../aurora-sentiment';

const STATES = ['bearish', 'neutral', 'bullish'] as const;

describe('AURORA_PRESETS — integrity', () => {
  it('ships a healthy number of presets', () => {
    expect(AURORA_PRESETS.length).toBeGreaterThanOrEqual(10);
  });

  it('has unique ids and labels', () => {
    const ids = AURORA_PRESETS.map(p => p.id);
    const labels = AURORA_PRESETS.map(p => p.label);
    expect(new Set(ids).size).toBe(ids.length);
    expect(new Set(labels).size).toBe(labels.length);
  });

  it('every preset color is a valid hex, and core differs from edge', () => {
    for (const p of AURORA_PRESETS) {
      for (const state of STATES) {
        const { core, edge } = p.palette[state];
        expect(isValidHex(core), `${p.id}.${state}.core = ${core}`).toBe(true);
        expect(isValidHex(edge), `${p.id}.${state}.edge = ${edge}`).toBe(true);
        expect(core.toLowerCase()).not.toBe(edge.toLowerCase());
      }
    }
  });

  it('every preset has a non-empty description', () => {
    for (const p of AURORA_PRESETS) {
      expect(p.description.trim().length).toBeGreaterThan(0);
    }
  });

  it('the default preset reproduces the shipped brand palette', () => {
    const eclipse = AURORA_PRESETS.find(p => p.id === 'eclipse');
    expect(eclipse).toBeDefined();
    expect(eclipse!.palette).toEqual(DEFAULT_AURORA_PALETTE);
  });

  it('is a normalized/complete palette (all states present)', () => {
    for (const p of AURORA_PRESETS) {
      for (const state of STATES) {
        expect(typeof p.palette[state].core).toBe('string');
        expect(typeof p.palette[state].edge).toBe('string');
      }
    }
  });
});

describe('applying a preset drives Aurora correctly', () => {
  it('resolves each preset to its exact cores at the sentiment extremes', () => {
    for (const p of AURORA_PRESETS) {
      expect(resolveAuroraVisuals(1, p.palette).colorStops[1].toLowerCase())
        .toBe(p.palette.bullish.core.toLowerCase());
      expect(resolveAuroraVisuals(-1, p.palette).colorStops[1].toLowerCase())
        .toBe(p.palette.bearish.core.toLowerCase());
      expect(resolveAuroraVisuals(0, p.palette).colorStops[1].toLowerCase())
        .toBe(p.palette.neutral.core.toLowerCase());
    }
  });

  it('uses the preset edge colors at the ribbon extremes', () => {
    for (const p of AURORA_PRESETS) {
      const stops = resolveAuroraVisuals(1, p.palette).colorStops;
      expect(stops[0].toLowerCase()).toBe(p.palette.bullish.edge.toLowerCase());
      expect(stops[2].toLowerCase()).toBe(p.palette.bullish.edge.toLowerCase());
    }
  });

  it('classifies bullish/bearish correctly regardless of preset colors', () => {
    for (const p of AURORA_PRESETS) {
      expect(resolveAuroraVisuals(0.5, p.palette).state).toBe('bullish');
      expect(resolveAuroraVisuals(-0.5, p.palette).state).toBe('bearish');
      expect(resolveAuroraVisuals(0, p.palette).state).toBe('neutral');
    }
  });

  it('interpolates between neutral and bullish monotonically for every preset', () => {
    // At increasing positive scores the resolved color must move away from the
    // neutral core toward the bullish core (no repeats, distinct endpoints).
    for (const p of AURORA_PRESETS) {
      const neutral = resolveAuroraVisuals(0, p.palette).colorStops[1];
      const mid = resolveAuroraVisuals(0.5, p.palette).colorStops[1];
      const bull = resolveAuroraVisuals(1, p.palette).colorStops[1];
      expect(new Set([neutral, mid, bull]).size).toBe(3);
    }
  });
});

describe('paletteMatchesPreset', () => {
  it('matches a preset by its own reference', () => {
    for (const p of AURORA_PRESETS) {
      expect(paletteMatchesPreset(p.palette, p.palette)).toBe(true);
    }
  });

  it('matches case-insensitively and ignores irrelevant formatting', () => {
    const upper: AuroraPalette = {
      bullish: { core: DEFAULT_AURORA_PALETTE.bullish.core.toUpperCase(), edge: DEFAULT_AURORA_PALETTE.bullish.edge.toUpperCase() },
      neutral: { core: DEFAULT_AURORA_PALETTE.neutral.core.toUpperCase(), edge: DEFAULT_AURORA_PALETTE.neutral.edge.toUpperCase() },
      bearish: { core: DEFAULT_AURORA_PALETTE.bearish.core.toUpperCase(), edge: DEFAULT_AURORA_PALETTE.bearish.edge.toUpperCase() },
    };
    expect(paletteMatchesPreset(upper, DEFAULT_AURORA_PALETTE)).toBe(true);
  });

  it('does not confuse distinct presets (all pairwise distinct)', () => {
    for (let i = 0; i < AURORA_PRESETS.length; i++) {
      for (let j = i + 1; j < AURORA_PRESETS.length; j++) {
        expect(
          paletteMatchesPreset(AURORA_PRESETS[i].palette, AURORA_PRESETS[j].palette),
          `${AURORA_PRESETS[i].id} vs ${AURORA_PRESETS[j].id}`,
        ).toBe(false);
      }
    }
  });

  it('returns false after a single color is changed', () => {
    const edited = defaultAuroraPalette();
    edited.bullish = { ...edited.bullish, core: '#123456' };
    expect(paletteMatchesPreset(edited, DEFAULT_AURORA_PALETTE)).toBe(false);
  });
});

describe('parseAuroraPalette — defensive loading', () => {
  it('round-trips a preset through JSON', () => {
    for (const p of AURORA_PRESETS) {
      const parsed = parseAuroraPalette(JSON.stringify(p.palette));
      expect(parsed).toEqual(p.palette);
    }
  });

  it('falls back to defaults for garbage input', () => {
    expect(parseAuroraPalette('not json')).toEqual(DEFAULT_AURORA_PALETTE);
    expect(parseAuroraPalette(null)).toEqual(DEFAULT_AURORA_PALETTE);
    expect(parseAuroraPalette('{}')).toEqual(DEFAULT_AURORA_PALETTE);
  });

  it('fills only missing/invalid colors (keeps valid ones)', () => {
    const partial = parseAuroraPalette(
      JSON.stringify({ bullish: { core: '#abcdef', edge: 'nope' } }),
    );
    expect(partial.bullish.core).toBe('#abcdef');
    expect(partial.bullish.edge).toBe(DEFAULT_AURORA_PALETTE.bullish.edge);
    expect(partial.neutral).toEqual(DEFAULT_AURORA_PALETTE.neutral);
    expect(partial.bearish).toEqual(DEFAULT_AURORA_PALETTE.bearish);
  });
});

describe('helpers', () => {
  it('isValidHex accepts 3/6-digit hex only', () => {
    expect(isValidHex('#fff')).toBe(true);
    expect(isValidHex('#7aff78')).toBe(true);
    expect(isValidHex('#GGGGGG')).toBe(false);
    expect(isValidHex('7aff78')).toBe(false);
    expect(isValidHex('')).toBe(false);
    expect(isValidHex(null)).toBe(false);
  });

  it('safeHex lowercases valid input, else returns the fallback', () => {
    expect(safeHex('#ABCDEF', '#000')).toBe('#abcdef');
    expect(safeHex('bad', '#000')).toBe('#000');
  });

  it('defaultAuroraPalette returns an independent clone each call', () => {
    const a = defaultAuroraPalette();
    const b = defaultAuroraPalette();
    a.bullish.core = '#000000';
    expect(b.bullish.core).not.toBe('#000000');
    expect(DEFAULT_AURORA_PALETTE.bullish.core).not.toBe('#000000');
  });

  it('exposes a stable storage key', () => {
    expect(AURORA_PALETTE_KEY).toBe('be_aurora_palette_v1');
  });
});
