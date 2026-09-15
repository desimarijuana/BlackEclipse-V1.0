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

/** Build a preset from three compact `[core, edge]` tuples. */
function preset(
  id: string,
  label: string,
  description: string,
  bearish: [string, string],
  neutral: [string, string],
  bullish: [string, string],
): AuroraPreset {
  return {
    id,
    label,
    description,
    palette: {
      bearish: { core: bearish[0], edge: bearish[1] },
      neutral: { core: neutral[0], edge: neutral[1] },
      bullish: { core: bullish[0], edge: bullish[1] },
    },
  };
}

/**
 * Shipped presets. The first is the default brand identity; the rest are
 * tasteful variations that stay inside the dark-terminal aesthetic. Every
 * palette is validated in `theme.test.ts` (all six colors must be valid hex),
 * and applying one is guaranteed to drive `resolveAuroraVisuals` to those
 * exact cores at the sentiment extremes.
 */
export const AURORA_PRESETS: AuroraPreset[] = [
  {
    id: 'eclipse',
    label: 'Eclipse',
    description: 'The default green-on-black brand glow.',
    palette: DEFAULT_AURORA_PALETTE,
  },
  preset('emerald', 'Emerald', 'Deeper, cooler green with a soft red bearish shift.',
    ['#ff6b6b', '#3f0d0d'], ['#2f7d5a', '#001b12'], ['#34d399', '#022c22']),
  preset('matrix', 'Matrix', 'Pure phosphor-green terminal, minimal red.',
    ['#ff3b3b', '#3a0505'], ['#0f8a2e', '#001207'], ['#00ff41', '#001a05']),
  preset('ice', 'Ice', 'Cold cyan bullish with a magenta bearish shift.',
    ['#e879f9', '#2e0733'], ['#4a8ea3', '#04181f'], ['#67e8f9', '#062b33']),
  preset('ocean', 'Ocean', 'Deep-sea blue glow with a coral bearish shift.',
    ['#fb7185', '#3a0a14'], ['#2f6f8f', '#041825'], ['#38bdf8', '#07263a']),
  preset('nord', 'Nord', 'Muted arctic frost — slate blue and understated red.',
    ['#bf616a', '#2e1418'], ['#5e81ac', '#141d2b'], ['#88c0d0', '#1b2b33']),
  preset('gold', 'Gold', 'Amber bullish glow with a rust bearish shift.',
    ['#ff5c5c', '#3f0d0d'], ['#b98b3a', '#241905'], ['#ffd166', '#3a2a05']),
  preset('sunset', 'Sunset', 'Warm orange bullish fading into a dusky rose bearish.',
    ['#d64550', '#320a0e'], ['#c96f3a', '#241005'], ['#ffb347', '#3a1e05']),
  preset('volcano', 'Volcano', 'Molten orange glow with a deep crimson drop.',
    ['#e63946', '#33070c'], ['#b3542a', '#240d05'], ['#ff8c42', '#3a1605']),
  preset('copper', 'Copper', 'Brushed copper bullish with an oxidised red bearish.',
    ['#c94f4f', '#320a0a'], ['#a9714b', '#241509'], ['#e8a87c', '#3a2415']),
  preset('crimson', 'Crimson', 'Rose-forward glow for a warmer terminal.',
    ['#ff2d55', '#3f0511'], ['#a35565', '#24070e'], ['#fb7185', '#3f0d1a']),
  preset('rose', 'Rose', 'Pink bullish with a deep rose bearish.',
    ['#e11d48', '#3a0512'], ['#b86f96', '#240b17'], ['#f9a8d4', '#3a1226']),
  preset('neon', 'Neon', 'Electric lime bullish with a hot-pink bearish.',
    ['#ff2bd6', '#2e0526'], ['#22c55e', '#03170a'], ['#39ff14', '#0a1f05']),
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
