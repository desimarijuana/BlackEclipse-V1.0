// ── Journal calendar intensity ───────────────────────────────────────────────
// Pure colour-intensity mapping for the calendar heatmaps. Kept out of the
// component files so it can be unit-tested without a JSX transform and reused by
// both the mini strip and the full-year heatmap.

export type IntensitySign = 'pos' | 'neg' | 'zero';

export interface Intensity {
  /** 0 = flat/breakeven; 1–4 = increasing magnitude. */
  level: 0 | 1 | 2 | 3 | 4;
  sign: IntensitySign;
}

/**
 * Map a day's net R to a signed intensity bucket.
 *
 * Sign is decided by the raw value (a −0.001R day is a LOSS, not flat), and the
 * level by absolute magnitude so a +4R day reads stronger than a +0.3R day
 * instead of both rendering as one flat green.
 */
export function intensityFor(netR: number): Intensity {
  if (netR === 0) return { level: 0, sign: 'zero' };
  const sign: IntensitySign = netR > 0 ? 'pos' : 'neg';
  const abs = Math.abs(netR);
  if (abs >= 3) return { level: 4, sign };
  if (abs >= 2) return { level: 3, sign };
  if (abs >= 1) return { level: 2, sign };
  return { level: 1, sign };
}
