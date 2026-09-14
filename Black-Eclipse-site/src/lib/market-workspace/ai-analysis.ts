// ── AI Market View — deterministic technical analysis ────────────────────────
// BlackEclipse's AI layer is DETERMINISTIC: every field is derived from the real
// OHLCV series with pure functions, so it can never hallucinate a price or a
// trend. The summary strings are templated from measured facts (trend, swings,
// momentum, volume, risk, levels) — not an LLM call. When there is no data the
// result is null and the UI shows UNAVAILABLE rather than inventing a view.

import type { PriceBar } from '@/lib/chart/types';
import { ema, rsi, sma } from '@/lib/chart/indicators/registry';

export type Trend = 'Bullish' | 'Bearish' | 'Ranging';
export type Strength = 'Strong' | 'Moderate' | 'Weak';
export type RiskLevel = 'Low' | 'Medium' | 'High';

export interface AiMarketView {
  symbol: string;
  trend: Trend;
  structure: string;
  momentum: Strength;
  volume: string;
  risk: RiskLevel;
  /** Key price levels (support/resistance), descending not guaranteed. */
  levels: number[];
  summary: string;
  /** Whether the underlying series was long enough to trust. */
  confident: boolean;
}

function last<T>(arr: T[]): T | undefined {
  return arr.length ? arr[arr.length - 1] : undefined;
}

function nz(v: number | null | undefined): number | null {
  return v != null && Number.isFinite(v) ? v : null;
}

/**
 * Build a deterministic AI market view from a price series. Pure + synchronous;
 * safe to memoize per symbol.
 */
export function analyzeForAi(symbol: string, bars: PriceBar[]): AiMarketView | null {
  if (!bars || bars.length < 30) return null;
  const closes = bars.map(b => b.close).filter(v => Number.isFinite(v));
  if (closes.length < 30) return null;

  const price = closes[closes.length - 1];
  const ema20 = nz(last(ema(closes, 20)));
  const ema50 = nz(last(ema(closes, 50)));
  const sma200 = bars.length >= 200 ? nz(last(sma(closes, 200))) : null;
  const rsi14 = nz(last(rsi(closes, 14)));

  // ── Trend ────────────────────────────────────────────────────────────────
  let trend: Trend = 'Ranging';
  let trendScore = 0;
  if (ema20 != null && ema50 != null) {
    if (ema20 > ema50) trendScore += 1;
    else if (ema20 < ema50) trendScore -= 1;
  }
  if (sma200 != null) {
    if (price > sma200) trendScore += 1;
    else trendScore -= 1;
  }
  // Slope of the last 20 closes as a tiebreaker.
  const slope = price - closes[Math.max(0, closes.length - 21)];
  if (slope > 0) trendScore += 0.5;
  else if (slope < 0) trendScore -= 0.5;
  if (trendScore >= 1.5) trend = 'Bullish';
  else if (trendScore <= -1.5) trend = 'Bearish';

  // ── Structure (swing highs/lows over the last ~40 bars) ───────────────────
  const structure = describeStructure(bars.slice(-40));

  // ── Momentum ─────────────────────────────────────────────────────────────
  const momentum = describeMomentum(rsi14, trend);

  // ── Volume ───────────────────────────────────────────────────────────────
  const volume = describeVolume(bars);

  // ── Risk (realized volatility of daily returns) ──────────────────────────
  const vol = realizedVol(closes.slice(-60));
  const risk: RiskLevel = vol >= 3 ? 'High' : vol >= 1.5 ? 'Medium' : 'Low';

  // ── Key levels (recent swing pivots + round reference) ───────────────────
  const levels = keyLevels(bars.slice(-90));

  const confident = bars.length >= 60;
  const summary = buildSummary({ symbol, trend, structure, momentum, volume, risk, price, ema20, ema50, rsi14, levels });

  return { symbol, trend, structure, momentum, volume, risk, levels, summary, confident };
}

function describeStructure(bars: PriceBar[]): string {
  if (bars.length < 8) return 'Insufficient data';
  const highs: number[] = [];
  const lows: number[] = [];
  for (let i = 2; i < bars.length - 2; i++) {
    const h = bars[i].high ?? bars[i].close;
    const l = bars[i].low ?? bars[i].close;
    if (h >= (bars[i - 1].high ?? bars[i - 1].close) && h >= (bars[i - 2].high ?? bars[i - 2].close)
      && h >= (bars[i + 1].high ?? bars[i + 1].close) && h >= (bars[i + 2].high ?? bars[i + 2].close)) highs.push(h);
    if (l <= (bars[i - 1].low ?? bars[i - 1].close) && l <= (bars[i - 2].low ?? bars[i - 2].close)
      && l <= (bars[i + 1].low ?? bars[i + 1].close) && l <= (bars[i + 2].low ?? bars[i + 2].close)) lows.push(l);
  }
  const hh = highs.length >= 2 && highs[highs.length - 1] > highs[highs.length - 2];
  const hl = lows.length >= 2 && lows[lows.length - 1] > lows[lows.length - 2];
  const lh = highs.length >= 2 && highs[highs.length - 1] < highs[highs.length - 2];
  const ll = lows.length >= 2 && lows[lows.length - 1] < lows[lows.length - 2];
  if (hh && hl) return 'Higher High / Higher Low';
  if (lh && ll) return 'Lower High / Lower Low';
  if (hh && !hl) return 'Higher Highs, flat lows';
  if (ll && !lh) return 'Lower Lows, flat highs';
  return 'Consolidating range';
}

function describeMomentum(rsi14: number | null, trend: Trend): Strength {
  if (rsi14 == null) return 'Weak';
  const aligned = (trend === 'Bullish' && rsi14 >= 50) || (trend === 'Bearish' && rsi14 <= 50);
  if (rsi14 >= 60 || rsi14 <= 40) return aligned ? 'Strong' : 'Moderate';
  return 'Moderate';
}

function describeVolume(bars: PriceBar[]): string {
  if (bars.length < 21) return 'Insufficient data';
  const recent = bars.slice(-5).map(b => b.volume ?? 0).filter(v => v > 0);
  const base = bars.slice(-25, -5).map(b => b.volume ?? 0).filter(v => v > 0);
  if (recent.length === 0 || base.length === 0) return 'Unavailable';
  const recentAvg = recent.reduce((a, b) => a + b, 0) / recent.length;
  const baseAvg = base.reduce((a, b) => a + b, 0) / base.length;
  if (baseAvg === 0) return 'Unavailable';
  const ratio = recentAvg / baseAvg;
  if (ratio >= 1.3) return 'Above average';
  if (ratio <= 0.7) return 'Below average';
  return 'Average';
}

function realizedVol(closes: number[]): number {
  if (closes.length < 10) return 0;
  const returns: number[] = [];
  for (let i = 1; i < closes.length; i++) {
    if (closes[i - 1] > 0) returns.push((closes[i] / closes[i - 1] - 1) * 100);
  }
  if (returns.length === 0) return 0;
  const mean = returns.reduce((a, b) => a + b, 0) / returns.length;
  const variance = returns.reduce((a, b) => a + (b - mean) ** 2, 0) / returns.length;
  return Math.sqrt(variance); // daily % stddev
}

function keyLevels(bars: PriceBar[]): number[] {
  if (bars.length < 5) return [];
  const highs = bars.map(b => b.high ?? b.close).sort((a, b) => b - a);
  const lows = bars.map(b => b.low ?? b.close).sort((a, b) => a - b);
  const price = bars[bars.length - 1].close;
  const resistance = [...new Set(highs.filter(h => h > price))].slice(0, 2);
  const support = [...new Set(lows.filter(l => l < price).reverse())].slice(-2).reverse();
  return [...new Set([...resistance, ...support])].slice(0, 4);
}

function buildSummary(v: {
  symbol: string; trend: Trend; structure: string; momentum: Strength; volume: string;
  risk: RiskLevel; price: number; ema20: number | null; ema50: number | null; rsi14: number | null; levels: number[];
}): string {
  const parts: string[] = [];
  if (v.trend === 'Bullish') parts.push(`Price is trading above its short-term averages with a bullish EMA alignment.`);
  else if (v.trend === 'Bearish') parts.push(`Price is trading below its short-term averages with a bearish EMA alignment.`);
  else parts.push(`Price is ranging with no clear directional bias across the moving averages.`);

  if (v.structure === 'Higher High / Higher Low') parts.push('The swing structure is making higher highs and higher lows.');
  else if (v.structure === 'Lower High / Lower Low') parts.push('The swing structure is making lower highs and lower lows.');
  else if (v.structure !== 'Insufficient data') parts.push(`Swing structure reads as ${v.structure.toLowerCase()}.`);

  if (v.rsi14 != null) {
    if (v.rsi14 >= 70) parts.push(`Momentum is stretched (RSI ${v.rsi14.toFixed(1)}), so a pause or pullback is possible.`);
    else if (v.rsi14 <= 30) parts.push(`Momentum is oversold (RSI ${v.rsi14.toFixed(1)}), watch for a bounce.`);
    else parts.push(`Momentum is ${v.momentum.toLowerCase()} with RSI at ${v.rsi14.toFixed(1)}.`);
  }

  parts.push(`Volume is ${v.volume.toLowerCase()} versus its recent baseline.`);
  parts.push(`Measured volatility is ${v.risk.toLowerCase()}.`);

  if (v.levels.length >= 2) {
    const below = v.levels.filter(l => l < v.price).sort((a, b) => b - a)[0];
    const above = v.levels.filter(l => l > v.price).sort((a, b) => a - b)[0];
    if (below != null && above != null) parts.push(`Key levels to watch: ${below.toFixed(2)} as support and ${above.toFixed(2)} as resistance.`);
  }

  parts.push('This is a deterministic read of price and volume, not investment advice.');
  return parts.join(' ');
}
