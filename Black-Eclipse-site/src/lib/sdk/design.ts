// ── Eclipse SDK — design patch merge ─────────────────────────────────────────
// A design call is a PATCH, not a full theme dump: callers may send only
// `{ colors: { primary } }` or `{ glass: { blur } }`. Nested groups are merged
// over the current theme; `normalizeTheme` then clamps/validates every value so
// an SDK caller can never persist an invalid token. Server-safe (no DOM).

import { DEFAULT_ECLIPSE_THEME, normalizeTheme, type EclipseTheme } from '@/lib/theme/tokens';

type Dict = Record<string, unknown>;

function isRecord(value: unknown): value is Dict {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

/** Merge a partial theme patch over a base theme. Unknown keys are ignored by
 *  `normalizeTheme` (the shape is closed), and invalid colors fall back to the
 *  base value rather than breaking the app. */
export function mergeThemePatch(base: EclipseTheme, patch: unknown): EclipseTheme {
  if (!isRecord(patch)) return normalizeTheme(base);
  const next: Dict = { ...base };
  for (const [key, value] of Object.entries(patch)) {
    if (!(key in DEFAULT_ECLIPSE_THEME)) continue;
    const current = (base as unknown as Dict)[key];
    if (isRecord(value) && isRecord(current)) {
      next[key] = { ...current, ...value };
    } else if (value !== undefined) {
      next[key] = value;
    }
  }
  return normalizeTheme(next);
}

/** The theme a design call starts from: the saved app-wide theme or the shipped default. */
export function baseDesignTheme(saved: EclipseTheme | null | undefined): EclipseTheme {
  return normalizeTheme(saved ?? DEFAULT_ECLIPSE_THEME);
}
