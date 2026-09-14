// ── Aurora sentiment model ───────────────────────────────────────────────────
// Pure, dependency-free logic that converts BlackEclipse's market + news
// sentiment into the continuous [-1, +1] score and visual parameters the Aurora
// WebGL component renders.
//
// SOURCE OF TRUTH
//   · Market sentiment comes from live equity-index performance (average %
//     change, index breadth, sector breadth) gathered by the Market Overview
//     screen. `marketSentimentFromIndices` excludes hedge instruments and
//     normalizes the raw percent reading into [-1, +1].
//   · News sentiment comes from `/api/news` `newsScore` — a tier-weighted 24h
//     bullish-vs-bearish ratio already in [-1, +1] (clamped defensively here).
//   · `combineSentiment` blends them 60% market / 40% news. Missing sides are
//     dropped and the remaining weight is renormalized, so Aurora stays correct
//     when one feed is unavailable. Both missing → 0 (neutral), never bullish.
//
// The score is a *sentiment reading*, not a price. Aurora only ever receives a
// normalized value; smoothing/animation lives in the component's rAF loop so no
// finance logic leaks into the visual layer.

export type AuroraMarketState = 'bullish' | 'bearish' | 'neutral';

export interface AuroraSentiment {
  /** Combined score in [-1, +1] (rounded to 3dp for stable comparisons). */
  score: number;
  /** Semantic bucket derived from the thresholds. */
  state: AuroraMarketState;
  /** Score magnitude in [0, 1] — color/motion intensity. */
  intensity: number;
}

export interface AuroraVisuals {
  state: AuroraMarketState;
  colorStops: [string, string, string];
  amplitude: number;
  speed: number;
  blend: number;
}

export interface CombineOptions {
  marketWeight?: number;
  newsWeight?: number;
}

// ── Tunables ─────────────────────────────────────────────────────────────────

/** Market/news blend for the combined score (kept in one place for tests). */
export const AURORA_MARKET_WEIGHT = 0.6;
export const AURORA_NEWS_WEIGHT = 0.4;

/** State thresholds. |score| below these stays neutral (avoids false precision). */
export const AURORA_BULLISH_THRESHOLD = 0.35;
export const AURORA_BEARISH_THRESHOLD = -0.35;

/** Daily % move that reads as a "fully" bullish/bearish equity market. */
const MARKET_PERCENT_SCALE = 1.5;

// Anchor palettes — preserved from the original Aurora identity.
// Neutral is a *subdued green* (not purple): Aurora stays within the brand's
// green-on-black language at rest and only shifts red when sentiment turns
// negative. Bullish brightens the same hue toward the original accent.
const BULL_STOPS: [string, string, string] = ['#022c22', '#7aff78', '#022c22'];
const BEAR_STOPS: [string, string, string] = ['#450a0a', '#ff3e3e', '#450a0a'];
const NEUTRAL_STOPS: [string, string, string] = ['#02170f', '#3d9e63', '#02170f'];

// Crypto + commodities move as risk hedges; averaged in they inverted the
// signal (gold up on a risk-off day painted the glow green while stocks bled).
const HEDGES = new Set([
  'BTC-USD', 'ETH-USD', 'SOL-USD', 'XRP-USD', 'DOGE-USD', 'BNB-USD',
  'GC=F', 'SI=F', 'CL=F', 'BZ=F',
]);

// ── Small numeric/color helpers ──────────────────────────────────────────────

function clampSigned(x: number): number {
  return x < -1 ? -1 : x > 1 ? 1 : x;
}

function finiteOrNull(x: number | null | undefined): number | null {
  return typeof x === 'number' && Number.isFinite(x) ? clampSigned(x) : null;
}

function smoothstep(t: number): number {
  const c = t < 0 ? 0 : t > 1 ? 1 : t;
  return c * c * (3 - 2 * c);
}

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '');
  const n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function rgbToHex(rgb: [number, number, number]): string {
  const part = (v: number) => {
    const c = Math.max(0, Math.min(255, Math.round(v)));
    return c.toString(16).padStart(2, '0');
  };
  return `#${part(rgb[0])}${part(rgb[1])}${part(rgb[2])}`;
}

/** Linear RGB interpolation between two hex colors (`t` in [0, 1]). */
export function mixHex(a: string, b: string, t: number): string {
  const k = smoothstep(t);
  const [ar, ag, ab] = hexToRgb(a);
  const [br, bg, bb] = hexToRgb(b);
  return rgbToHex([ar + (br - ar) * k, ag + (bg - ag) * k, ab + (bb - ab) * k]);
}

function mixStops(
  a: [string, string, string],
  b: [string, string, string],
  t: number,
): [string, string, string] {
  return [mixHex(a[0], b[0], t), mixHex(a[1], b[1], t), mixHex(a[2], b[2], t)];
}

// ── Market sentiment ─────────────────────────────────────────────────────────

interface IndexLike {
  symbol: string;
  price: number;
  changePercent: number;
}

interface SectorLike {
  change: number;
}

/**
 * Normalize a raw percent-unit market reading (avg % change + breadth nudges)
 * into [-1, +1]. `tanh` compresses outliers: ±1.5% is a strong day (~0.76).
 */
export function normalizeMarketSentiment(rawPercent: number): number {
  if (!Number.isFinite(rawPercent)) return 0;
  return clampSigned(Math.tanh(rawPercent / MARKET_PERCENT_SCALE));
}

/**
 * Continuous normalized market sentiment from live index + sector data.
 *
 * Returns `null` when there is no priced index data — callers must treat that
 * as UNAVAILABLE and fall back to neutral, never to bullish.
 */
export function marketSentimentFromIndices(
  indices: ReadonlyArray<IndexLike> | null | undefined,
  sectors: ReadonlyArray<SectorLike> | null | undefined,
): number | null {
  const priced = (indices ?? []).filter(
    (i) => i && Number.isFinite(i.price) && i.price > 0 && Number.isFinite(i.changePercent),
  );
  if (priced.length === 0) return null;

  const equity = priced.filter((i) => !HEDGES.has(i.symbol));
  const pool = equity.length > 0 ? equity : priced;

  const avg = pool.reduce((sum, i) => sum + i.changePercent, 0) / pool.length;
  const breadthUp = pool.filter((i) => i.changePercent > 0).length / pool.length;

  const pricedSectors = (sectors ?? []).filter((s) => s && Number.isFinite(s.change));
  const secUp =
    pricedSectors.length > 0
      ? pricedSectors.filter((s) => s.change > 0).length / pricedSectors.length
      : 0.5;

  // Index average dominates (percent units); breadth/sector are ±0.5-scale nudges.
  const raw = avg + (breadthUp - 0.5) * 0.6 + (secUp - 0.5) * 0.3;
  return normalizeMarketSentiment(raw);
}

// ── Combined sentiment ───────────────────────────────────────────────────────

/**
 * Blend market + news sentiment into [-1, +1].
 *
 * Null / undefined / NaN / out-of-range inputs are handled safely: an
 * unavailable side is dropped and the surviving weight is renormalized. Both
 * sides missing → 0 (neutral). This is why a missing feed can never produce a
 * false bullish reading.
 */
export function combineSentiment(
  market: number | null | undefined,
  news: number | null | undefined,
  opts: CombineOptions = {},
): number {
  const mw = opts.marketWeight ?? AURORA_MARKET_WEIGHT;
  const nw = opts.newsWeight ?? AURORA_NEWS_WEIGHT;
  const m = finiteOrNull(market);
  const n = finiteOrNull(news);

  if (m === null && n === null) return 0;
  if (m === null) return n as number;
  if (n === null) return m;

  const total = mw + nw;
  if (total <= 0) return 0;
  return clampSigned((m * mw + n * nw) / total);
}

/** Classify a combined score into the coarse Aurora state. */
export function classifyAuroraState(score: number): AuroraMarketState {
  const s = finiteOrNull(score) ?? 0;
  if (s >= AURORA_BULLISH_THRESHOLD) return 'bullish';
  if (s <= AURORA_BEARISH_THRESHOLD) return 'bearish';
  return 'neutral';
}

/** One-shot convenience: combine + classify. */
export function auroraSentiment(
  market: number | null | undefined,
  news: number | null | undefined,
  opts: CombineOptions = {},
): AuroraSentiment {
  const score = Math.round(combineSentiment(market, news, opts) * 1000) / 1000;
  return { score, state: classifyAuroraState(score), intensity: Math.abs(score) };
}

// ── Score → visuals ──────────────────────────────────────────────────────────

/**
 * Map a continuous score to the Aurora palette and motion parameters.
 *
 *   -1.0  deep red          (fast, tall)  →  bearish
 *    0.0  subdued green     (slow, calm)  →  neutral
 *   +1.0  bright green      (fast, tall)  →  bullish
 *
 * Colors interpolate smoothly (no green/red switch), and motion stays subtle:
 * amplitude 1.2→1.8, speed 1.2→2.0 as |score| goes 0→1.
 */
export function resolveAuroraVisuals(score: number): AuroraVisuals {
  const s = finiteOrNull(score) ?? 0;
  const intensity = Math.abs(s);
  const colorStops =
    s >= 0
      ? mixStops(NEUTRAL_STOPS, BULL_STOPS, s)
      : mixStops(NEUTRAL_STOPS, BEAR_STOPS, -s);
  return {
    state: classifyAuroraState(s),
    colorStops,
    amplitude: 1.2 + 0.6 * intensity,
    speed: 1.2 + 0.8 * intensity,
    blend: 0.95,
  };
}

/**
 * Exponential-smoothing step (`alpha` in [0,1]). Exposed so non-RAF consumers
 * (and tests) can reproduce the same easing the Aurora component applies.
 */
export function stepSentiment(current: number, target: number, alpha: number): number {
  const c = finiteOrNull(current) ?? 0;
  const t = finiteOrNull(target) ?? 0;
  const a = alpha < 0 ? 0 : alpha > 1 ? 1 : alpha;
  return clampSigned(c + (t - c) * a);
}
