import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  AURORA_CONFIG_KEY,
  AURORA_MOTION_LIMITS,
  AURORA_SHAPE_LIMITS,
  AURORA_STYLE_IDS,
  AURORA_STYLE_LIMITS,
  DEFAULT_AURORA_MOTION,
  DEFAULT_AURORA_SHAPE,
  DEFAULT_AURORA_STYLE,
  defaultAuroraConfig,
  loadAuroraConfig,
  normalizeAuroraConfig,
  normalizeAuroraMotion,
  normalizeAuroraShape,
  normalizeAuroraStyle,
  resetAuroraConfig,
  saveAuroraConfig,
} from './config';
import { AURORA_PALETTE_KEY, DEFAULT_AURORA_PALETTE } from './theme';

const values = new Map<string, string>();
const storage = {
  getItem: (name: string) => values.get(name) ?? null,
  setItem: (name: string, value: string) => { values.set(name, value); },
  removeItem: (name: string) => { values.delete(name); },
};

beforeEach(() => {
  values.clear();
  vi.stubGlobal('localStorage', storage);
  vi.stubGlobal('window', { localStorage: storage, dispatchEvent: vi.fn() });
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe('defaultAuroraConfig', () => {
  it('reproduces the shipped palette + neutral motion/shape/style', () => {
    const c = defaultAuroraConfig();
    expect(c.palette).toEqual(DEFAULT_AURORA_PALETTE);
    expect(c.motion).toEqual(DEFAULT_AURORA_MOTION);
    expect(c.shape).toEqual(DEFAULT_AURORA_SHAPE);
    expect(c.style).toEqual(DEFAULT_AURORA_STYLE);
  });

  it('returns independent clones (no shared references)', () => {
    const a = defaultAuroraConfig();
    const b = defaultAuroraConfig();
    a.shape.height = 999;
    a.palette.bullish.core = '#000000';
    a.style.id = 'dots';
    expect(b.shape.height).toBe(DEFAULT_AURORA_SHAPE.height);
    expect(b.palette.bullish.core).toBe(DEFAULT_AURORA_PALETTE.bullish.core);
    expect(b.style.id).toBe(DEFAULT_AURORA_STYLE.id);
  });
});

describe('normalizeAuroraMotion / normalizeAuroraShape — clamping', () => {
  it('clamps out-of-range values into the slider bounds', () => {
    expect(normalizeAuroraMotion({ intensity: 99 }).intensity).toBe(AURORA_MOTION_LIMITS.intensity.max);
    expect(normalizeAuroraMotion({ intensity: -5 }).intensity).toBe(AURORA_MOTION_LIMITS.intensity.min);
    expect(normalizeAuroraShape({ height: 100000 }).height).toBe(AURORA_SHAPE_LIMITS.height.max);
    expect(normalizeAuroraShape({ noiseScale: 0 }).noiseScale).toBe(AURORA_SHAPE_LIMITS.noiseScale.min);
  });

  it('fills missing / non-finite values from the defaults', () => {
    expect(normalizeAuroraMotion({}).intensity).toBe(DEFAULT_AURORA_MOTION.intensity);
    expect(normalizeAuroraMotion({ speed: NaN }).speed).toBe(DEFAULT_AURORA_MOTION.speed);
    expect(normalizeAuroraShape({}).height).toBe(DEFAULT_AURORA_SHAPE.height);
    expect(normalizeAuroraShape({ softness: Infinity }).softness).toBe(DEFAULT_AURORA_SHAPE.softness);
  });

  it('rounds height to a whole pixel', () => {
    expect(normalizeAuroraShape({ height: 200.6 }).height).toBe(201);
  });
});

describe('normalizeAuroraStyle', () => {
  it('accepts every known style id', () => {
    for (const id of AURORA_STYLE_IDS) {
      expect(normalizeAuroraStyle({ id }).id).toBe(id);
    }
  });

  it('falls back to the default for an unknown style id', () => {
    expect(normalizeAuroraStyle({ id: 'hologram' as never }).id).toBe(DEFAULT_AURORA_STYLE.id);
    expect(normalizeAuroraStyle(null).id).toBe(DEFAULT_AURORA_STYLE.id);
  });

  it('clamps and rounds the grid size', () => {
    expect(normalizeAuroraStyle({ grid: 999 }).grid).toBe(AURORA_STYLE_LIMITS.grid.max);
    expect(normalizeAuroraStyle({ grid: 1 }).grid).toBe(AURORA_STYLE_LIMITS.grid.min);
    expect(normalizeAuroraStyle({ grid: 12.6 }).grid).toBe(13);
    expect(normalizeAuroraStyle({}).grid).toBe(DEFAULT_AURORA_STYLE.grid);
  });
});

describe('normalizeAuroraConfig — defensive', () => {
  it('always yields a complete config from garbage', () => {
    expect(normalizeAuroraConfig(null)).toEqual(defaultAuroraConfig());
    expect(normalizeAuroraConfig({} as never)).toEqual(defaultAuroraConfig());
  });

  it('keeps valid slices and repairs invalid ones', () => {
    const c = normalizeAuroraConfig({
      palette: { bullish: { core: '#abcdef', edge: 'nope' } } as never,
      motion: { intensity: 1.5 } as never,
      shape: { height: 300 } as never,
    });
    expect(c.palette.bullish.core).toBe('#abcdef');
    expect(c.palette.bullish.edge).toBe(DEFAULT_AURORA_PALETTE.bullish.edge);
    expect(c.motion.intensity).toBe(1.5);
    expect(c.motion.speed).toBe(DEFAULT_AURORA_MOTION.speed);
    expect(c.shape.height).toBe(300);
  });
});

describe('load / save / reset round-trip', () => {
  it('round-trips a config through localStorage', () => {
    const c = defaultAuroraConfig();
    c.motion.speed = 1.75;
    c.shape.height = 320;
    saveAuroraConfig(c);
    expect(values.has(AURORA_CONFIG_KEY)).toBe(true);
    expect(loadAuroraConfig()).toEqual(c);
  });

  it('migrates a legacy v1 palette with default motion/shape when no v2 exists', () => {
    values.set(AURORA_PALETTE_KEY, JSON.stringify({ bullish: { core: '#123456', edge: '#000000' } }));
    const c = loadAuroraConfig();
    expect(c.palette.bullish.core).toBe('#123456');
    expect(c.motion).toEqual(DEFAULT_AURORA_MOTION);
    expect(c.shape).toEqual(DEFAULT_AURORA_SHAPE);
    expect(c.style).toEqual(DEFAULT_AURORA_STYLE);
  });

  it('reset clears both v2 config and the legacy v1 palette', () => {
    saveAuroraConfig(defaultAuroraConfig());
    values.set(AURORA_PALETTE_KEY, '{}');
    resetAuroraConfig();
    expect(values.has(AURORA_CONFIG_KEY)).toBe(false);
    expect(values.has(AURORA_PALETTE_KEY)).toBe(false);
  });

  it('is inert without a window (SSR)', () => {
    vi.unstubAllGlobals();
    expect(() => saveAuroraConfig(defaultAuroraConfig())).not.toThrow();
    expect(loadAuroraConfig()).toEqual(defaultAuroraConfig());
  });
});
