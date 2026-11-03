// ── Journal calendar intensity ───────────────────────────────────────────────
// Pure colour-intensity mapping for the calendar heatmap. Kept out of the
// component files so it can be unit-tested without a JSX transform and reused by
// the mini contribution strip.

export type IntensitySign = 'pos' | 'neg' | 'zero';

export interface Intensity {
  /** 0 = flat/breakeven; 1–4 = increasing magnitude. */
  level: 0 | 1 | 2 | 3 | 4;
  sign: IntensitySign;
}

/**
 * Map a day's result to a signed intensity bucket.
 *
 * Sign is decided by the raw value (a −0.001R day is a LOSS, not flat), and the
 * level by absolute magnitude so a +4R day reads stronger than a +0.3R day
 * instead of both rendering as one flat green. `thresholds` are the level 2/3/4
 * boundaries; the R defaults are overridden for currency-based shading.
 */
export function intensityFor(
  value: number,
  thresholds: [number, number, number] = [1, 2, 3],
): Intensity {
  if (value === 0) return { level: 0, sign: 'zero' };
  const sign: IntensitySign = value > 0 ? 'pos' : 'neg';
  const abs = Math.abs(value);
  if (abs >= thresholds[2]) return { level: 4, sign };
  if (abs >= thresholds[1]) return { level: 3, sign };
  if (abs >= thresholds[0]) return { level: 2, sign };
  return { level: 1, sign };
}
