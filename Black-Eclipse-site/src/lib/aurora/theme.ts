// ── Aurora color theme ───────────────────────────────────────────────────────
// Presentation-layer customization for the Aurora glow (Settings › Aurora).
// Keeps the *sentiment* model untouched: users only recolor the three sentiment
// states, and `resolveAuroraVisuals(score, palette)` interpolates between them
// exactly as it does with the shipped default.
//
// Persistence is client-side (localStorage), matching the sidebar/currency
// conventions — no server round-trip, no DB schema change.

'use client';

import {
  DEFAULT_AURORA_PALETTE,
  normalizePalette,
  type AuroraColorPair,
  type AuroraMarketState,
  type AuroraPalette,
} from '@/lib/aurora-sentiment';

export type { AuroraColorPair, AuroraMarketState, AuroraPalette };

export const AURORA_PALETTE_KEY = 'be_aurora_palette_v1';

/** A named, ready-to-apply look shown as a preset in Settings. */
export interface AuroraPreset {
  id: string;
  label: string;
  description: string;
  palette: AuroraPalette;
}

/**
 * Shipped presets. The first is the default brand identity; the rest are
 * tasteful variations that stay inside the dark-terminal aesthetic.
 */
export const AURORA_PRESETS: AuroraPreset[] = [
  {
    id: 'eclipse',
    label: 'Eclipse',
    description: 'The default green-on-black brand glow.',
    palette: DEFAULT_AURORA_PALETTE,
  },
  {
    id: 'emerald',
    label: 'Emerald',
    description: 'Deeper, cooler green with a teal bearish shift.',
    palette: {
      bullish: { core: '#34d399', edge: '#022c22' },
      neutral: { core: '#2f7d5a', edge: '#001b12' },
      bearish: { core: '#ff6b6b', edge: '#3f0d0d' },
    },
  },
  {
    id: 'gold',
    label: 'Gold',
    description: 'Amber bullish glow with a rust bearish shift.',
    palette: {
      bullish: { core: '#ffd166', edge: '#3a2a05' },
      neutral: { core: '#b98b3a', edge: '#241905' },
      bearish: { core: '#ff5c5c', edge: '#3f0d0d' },
    },
  },
  {
    id: 'ice',
    label: 'Ice',
    description: 'Cool cyan bullish glow with a magenta bearish shift.',
    palette: {
      bullish: { core: '#67e8f9', edge: '#062b33' },
      neutral: { core: '#4a8ea3', edge: '#04181f' },
      bearish: { core: '#e879f9', edge: '#2e0733' },
    },
  },
  {
    id: 'crimson',
    label: 'Crimson',
    description: 'Rose-forward glow for a warmer terminal.',
    palette: {
      bullish: { core: '#fb7185', edge: '#3f0d1a' },
      neutral: { core: '#a35565', edge: '#24070e' },
      bearish: { core: '#ff2d55', edge: '#3f0511' },
    },
  },
];

export const STATE_LABELS: Record<AuroraMarketState, string> = {
  bullish: 'Bullish',
  bearish: 'Bearish',
  neutral: 'Neutral',
};

/** The order states are edited in — matches the sentiment gradient. */
export const STATE_ORDER: AuroraMarketState[] = ['bearish', 'neutral', 'bullish'];

const HEX_RE = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i;

/** True for a valid 3- or 6-digit hex color. */
export function isValidHex(value: unknown): value is string {
  return typeof value === 'string' && HEX_RE.test(value.trim());
}

/** Coerce any input to a valid hex (falls back to `fallback`). */
export function safeHex(value: unknown, fallback: string): string {
  return isValidHex(value) ? value.trim().toLowerCase() : fallback;
}

/** Clone the default palette (avoids sharing mutable references). */
export function defaultAuroraPalette(): AuroraPalette {
  return {
    bullish: { ...DEFAULT_AURORA_PALETTE.bullish },
    neutral: { ...DEFAULT_AURORA_PALETTE.neutral },
    bearish: { ...DEFAULT_AURORA_PALETTE.bearish },
  };
}

/**
 * Parse a stored/serialized palette defensively: any missing or malformed color
 * is replaced by the default. Never throws, never returns partial objects.
 */
export function parseAuroraPalette(raw: unknown): AuroraPalette {
  let obj: Partial<AuroraPalette> | null = null;
  if (typeof raw === 'string') {
    try {
      obj = JSON.parse(raw) as Partial<AuroraPalette>;
    } catch {
      obj = null;
    }
  } else if (raw && typeof raw === 'object') {
    obj = raw as Partial<AuroraPalette>;
  }
  return normalizePalette(obj as AuroraPalette | null);
}

export function loadAuroraPalette(): AuroraPalette {
  if (typeof window === 'undefined') return defaultAuroraPalette();
  try {
    const raw = localStorage.getItem(AURORA_PALETTE_KEY);
    if (!raw) return defaultAuroraPalette();
    return parseAuroraPalette(raw);
  } catch {
    return defaultAuroraPalette();
  }
}

export function saveAuroraPalette(palette: AuroraPalette): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(AURORA_PALETTE_KEY, JSON.stringify(normalizePalette(palette)));
    window.dispatchEvent(new CustomEvent('eclipse:aurora-palette-change'));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

export function resetAuroraPalette(): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(AURORA_PALETTE_KEY);
    window.dispatchEvent(new CustomEvent('eclipse:aurora-palette-change'));
  } catch {
    /* ignore */
  }
}

/** True when `palette` matches a shipped preset (used to highlight the chip). */
export function paletteMatchesPreset(palette: AuroraPalette, preset: AuroraPalette): boolean {
  const eq = (a: AuroraColorPair, b: AuroraColorPair) =>
    safeHex(a.core, '').toLowerCase() === safeHex(b.core, '').toLowerCase() &&
    safeHex(a.edge, '').toLowerCase() === safeHex(b.edge, '').toLowerCase();
  return (
    eq(palette.bullish, preset.bullish) &&
    eq(palette.neutral, preset.neutral) &&
    eq(palette.bearish, preset.bearish)
  );
}

export { DEFAULT_AURORA_PALETTE };
