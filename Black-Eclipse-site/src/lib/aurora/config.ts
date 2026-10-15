// ── Aurora config ────────────────────────────────────────────────────────────
// The full, user-editable Aurora customization: the sentiment palette (colors)
// PLUS the motion, shape and RENDER-STYLE knobs that used to be hardcoded in the
// shader.
//
// The sentiment MODEL is still untouched — `resolveAuroraVisuals()` keeps
// producing the baseline amplitude/speed/blend for a score, and these values are
// applied as MULTIPLIERS on top of that output (a new shader uniform,
// uNoiseScale, controls wave frequency; `style` selects a render branch). So a
// user can make the glow calmer, faster, wider or dot-matrixed without ever
// changing how sentiment maps to color.
//
// Persistence is client-side (localStorage), matching the palette convention. The
// v2 key supersedes the old palette-only v1 key; `loadAuroraConfig` migrates a
// legacy v1 palette forward so existing users keep their colors.

'use client';

import {
  defaultAuroraPalette,
  loadAuroraPalette,
  parseAuroraPalette,
  resetAuroraPalette,
  type AuroraPalette,
} from './theme';

export const AURORA_CONFIG_KEY = 'be_aurora_config_v2';

/** How the glow moves. Each value is a MULTIPLIER on the sentiment-driven base. */
export interface AuroraMotion {
  /** Amplitude multiplier — ribbon height/energy. 1 = shipped. */
  intensity: number;
  /** Time multiplier — animation speed. 1 = shipped. */
  speed: number;
  /** Easing factor toward the incoming score. Higher = snappier. 0.04 = shipped. */
  response: number;
}

/** The glow's physical shape. */
export interface AuroraShape {
  /** Band height in px (the container the shader fills). 224 = shipped `h-56`. */
  height: number;
  /** Blend multiplier — the softness/width of the ribbon falloff. 1 = shipped. */
  softness: number;
  /** Wave frequency. Higher = more, thinner ribbons. 2 = shipped. */
  noiseScale: number;
}

/** How the sentiment color field is RENDERED. Never changes the model, only the look. */
export type AuroraStyleId = 'ribbon' | 'dots' | 'scanlines' | 'pillars' | 'blocks';

export interface AuroraStyle {
  id: AuroraStyleId;
  /** Cell / line / bar size in px for the stylized modes. Ribbon ignores it. */
  grid: number;
}

/** The complete Aurora customization. `palette` is unchanged from the palette era. */
export interface AuroraConfig {
  palette: AuroraPalette;
  motion: AuroraMotion;
  shape: AuroraShape;
  style: AuroraStyle;
}

export const AURORA_STYLE_IDS: AuroraStyleId[] = ['ribbon', 'dots', 'scanlines', 'pillars', 'blocks'];

/** Ready-made style chips shown in Settings (label/hint; icons live in the UI). */
export const AURORA_STYLES: { id: AuroraStyleId; label: string; hint: string }[] = [
  { id: 'ribbon', label: 'Ribbon', hint: 'The flowing aurora curtain' },
  { id: 'dots', label: 'Dot matrix', hint: 'LED grid lit by the glow' },
  { id: 'scanlines', label: 'Scanlines', hint: 'CRT lines over the ribbon' },
  { id: 'pillars', label: 'Pillars', hint: 'Vertical bars, height by intensity' },
  { id: 'blocks', label: 'Blocks', hint: 'Chunky retro pixel bands' },
];

export const DEFAULT_AURORA_MOTION: AuroraMotion = {
  intensity: 1,
  speed: 1,
  response: 0.04,
};

export const DEFAULT_AURORA_SHAPE: AuroraShape = {
  height: 224,
  softness: 1,
  noiseScale: 2,
};

export const DEFAULT_AURORA_STYLE: AuroraStyle = {
  id: 'ribbon',
  grid: 22,
};

/** Slider bounds (min/max/step) for the Settings UI and normalization clamps. */
export const AURORA_MOTION_LIMITS = {
  intensity: { min: 0.3, max: 2, step: 0.05 },
  speed: { min: 0.2, max: 2.5, step: 0.05 },
  response: { min: 0.01, max: 0.3, step: 0.01 },
} as const;

export const AURORA_SHAPE_LIMITS = {
  height: { min: 96, max: 384, step: 8 },
  softness: { min: 0.3, max: 1.8, step: 0.05 },
  noiseScale: { min: 1, max: 4, step: 0.1 },
} as const;

export const AURORA_STYLE_LIMITS = {
  grid: { min: 6, max: 64, step: 1 },
} as const;

/** Independent clones (never share a mutable reference with the defaults). */
export function defaultAuroraMotion(): AuroraMotion {
  return { ...DEFAULT_AURORA_MOTION };
}

export function defaultAuroraShape(): AuroraShape {
  return { ...DEFAULT_AURORA_SHAPE };
}

export function defaultAuroraStyle(): AuroraStyle {
  return { ...DEFAULT_AURORA_STYLE };
}

export function defaultAuroraConfig(): AuroraConfig {
  return {
    palette: defaultAuroraPalette(),
    motion: defaultAuroraMotion(),
    shape: defaultAuroraShape(),
    style: defaultAuroraStyle(),
  };
}

function clampNum(value: unknown, min: number, max: number, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value)
    ? Math.min(max, Math.max(min, value))
    : fallback;
}

/** Clamp every motion knob into its valid range, filling missing values. */
export function normalizeAuroraMotion(raw?: Partial<AuroraMotion> | null): AuroraMotion {
  const l = AURORA_MOTION_LIMITS;
  return {
    intensity: clampNum(raw?.intensity, l.intensity.min, l.intensity.max, DEFAULT_AURORA_MOTION.intensity),
    speed: clampNum(raw?.speed, l.speed.min, l.speed.max, DEFAULT_AURORA_MOTION.speed),
    response: clampNum(raw?.response, l.response.min, l.response.max, DEFAULT_AURORA_MOTION.response),
  };
}

/** Clamp every shape knob into its valid range, filling missing values. */
export function normalizeAuroraShape(raw?: Partial<AuroraShape> | null): AuroraShape {
  const l = AURORA_SHAPE_LIMITS;
  return {
    height: Math.round(clampNum(raw?.height, l.height.min, l.height.max, DEFAULT_AURORA_SHAPE.height)),
    softness: clampNum(raw?.softness, l.softness.min, l.softness.max, DEFAULT_AURORA_SHAPE.softness),
    noiseScale: clampNum(raw?.noiseScale, l.noiseScale.min, l.noiseScale.max, DEFAULT_AURORA_SHAPE.noiseScale),
  };
}

/** Validate the style id against the known set and clamp the cell size. */
export function normalizeAuroraStyle(raw?: Partial<AuroraStyle> | null): AuroraStyle {
  const l = AURORA_STYLE_LIMITS;
  const id = AURORA_STYLE_IDS.includes(raw?.id as AuroraStyleId)
    ? (raw!.id as AuroraStyleId)
    : DEFAULT_AURORA_STYLE.id;
  return {
    id,
    grid: Math.round(clampNum(raw?.grid, l.grid.min, l.grid.max, DEFAULT_AURORA_STYLE.grid)),
  };
}

/** Validate a stored/partial config defensively; never throws, never partial. */
export function normalizeAuroraConfig(raw?: Partial<AuroraConfig> | null): AuroraConfig {
  return {
    palette: parseAuroraPalette(raw?.palette),
    motion: normalizeAuroraMotion(raw?.motion),
    shape: normalizeAuroraShape(raw?.shape),
    style: normalizeAuroraStyle(raw?.style),
  };
}

/**
 * Load the saved config. Falls back to the legacy palette-only v1 value (with
 * default motion/shape) so existing users keep their colors on first run after
 * this change.
 */
export function loadAuroraConfig(): AuroraConfig {
  if (typeof window === 'undefined') return defaultAuroraConfig();
  try {
    const raw = localStorage.getItem(AURORA_CONFIG_KEY);
    if (!raw) {
      return {
        palette: loadAuroraPalette(),
        motion: defaultAuroraMotion(),
        shape: defaultAuroraShape(),
        style: defaultAuroraStyle(),
      };
    }
    return normalizeAuroraConfig(JSON.parse(raw) as Partial<AuroraConfig>);
  } catch {
    return defaultAuroraConfig();
  }
}

export function saveAuroraConfig(config: AuroraConfig): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(AURORA_CONFIG_KEY, JSON.stringify(normalizeAuroraConfig(config)));
    window.dispatchEvent(new CustomEvent('eclipse:aurora-palette-change'));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

export function resetAuroraConfig(): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(AURORA_CONFIG_KEY);
    // Drop the legacy v1 palette too, so a reset is truly a reset.
    resetAuroraPalette();
    window.dispatchEvent(new CustomEvent('eclipse:aurora-palette-change'));
  } catch {
    /* ignore */
  }
}
