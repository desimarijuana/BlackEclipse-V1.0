// ── Deterministic company technical analysis (Workstream E, Section I) ───────
// All values are computed from the ACTUAL historical series using the shared
// indicator library (`chart/indicators/registry`). Nothing here is produced by
// a model, and every field is a function of the input bars alone. The section
// UI renders `observed` conditions; interpretations are labelled separately.

import { sma, rsi, macd, atr } from '@/lib/chart/indicators/registry';
import type { PriceBar } from '@/lib/chart/types';

export interface TechnicalSnapshot {
  /** Number of bars the snapshot was computed from. */
  bars: number;
  /** Date of the newest bar (YYYY-MM-DD), when known. */
  asOf: string | null;
  /** Last close at computation time. */
  last: number | null;
  sma20: number | null;
  sma50: number | null;
  sma200: number | null;
  rsi14: number | null;
  rsiState: 'overbought' | 'oversold' | 'neutral' | 'unknown';
  macd: number | null;
  macdSignal: number | null;
  macdHist: number | null;
  macdState: 'bullish' | 'bearish' | 'unknown';
  /** Annualized realized volatility % (252 trading days). */
  volatilityPct: number | null;
  atr14: number | null;
  /** Max drawdown % (negative) over the series. */
  maxDrawdownPct: number | null;
  /** Period returns % (null when the series is too short). */
  return1w: number | null;
  return1m: number | null;
  return3m: number | null;
  /** Average volume, recent 10 bars vs the full window (ratio; null if no volume). */
  volumeTrend: number | null;
  trend: 'uptrend' | 'downtrend' | 'sideways' | 'unknown';
  /** Recent support/resistance estimates: 20-bar min/max of close. */
  support: number | null;
  resistance: number | null;
}

function lastDefined<T>(arr: (T | null)[]): T | null {
  for (let i = arr.length - 1; i >= 0; i--) if (arr[i] != null) return arr[i] as T;
  return null;
}

function pctReturn(closes: number[], back: number): number | null {
  if (closes.length <= back) return null;
  const last = closes[closes.length - 1];
  const base = closes[closes.length - 1 - back];
  if (!base || base <= 0) return null;
  return +(((last - base) / base) * 100).toFixed(2);
}

function dailyReturns(xs: number[]): number[] {
  const out: number[] = [];
  for (let i = 1; i < xs.length; i++) if (xs[i - 1] > 0) out.push(xs[i] / xs[i - 1] - 1);
  return out;
}

function stdev(xs: number[]): number {
  if (xs.length < 2) return 0;
  const mean = xs.reduce((a, b) => a + b, 0) / xs.length;
  return Math.sqrt(xs.reduce((a, x) => a + (x - mean) ** 2, 0) / (xs.length - 1));
}

function maxDrawdown(series: number[]): number | null {
  if (series.length < 2) return null;
  let peak = series[0];
  let mdd = 0;
  for (const x of series) {
    if (x > peak) peak = x;
    if (peak > 0) mdd = Math.min(mdd, x / peak - 1);
  }
  return +(mdd * 100).toFixed(2);
}

const EMPTY: TechnicalSnapshot = {
  bars: 0, asOf: null, last: null,
  sma20: null, sma50: null, sma200: null,
  rsi14: null, rsiState: 'unknown',
  macd: null, macdSignal: null, macdHist: null, macdState: 'unknown',
  volatilityPct: null, atr14: null, maxDrawdownPct: null,
  return1w: null, return1m: null, return3m: null, volumeTrend: null,
  trend: 'unknown', support: null, resistance: null,
};

/** Compute the technical snapshot from real OHLCV bars. Returns an all-null
 *  snapshot (never fabricated) when there is not enough data. */
export function computeTechnical(bars: PriceBar[] | null | undefined): TechnicalSnapshot {
  if (!Array.isArray(bars) || bars.length === 0) return EMPTY;
  const clean = bars.filter((b) => Number.isFinite(b.close) && b.close > 0);
  if (clean.length < 2) return EMPTY;
  const closes = clean.map((b) => b.close);
  const last = closes[closes.length - 1];
  const asOf = clean[clean.length - 1]?.date ?? null;

  const s20 = lastDefined(sma(closes, 20));
  const s50 = lastDefined(sma(closes, 50));
  const s200 = lastDefined(sma(closes, 200));
  const r14 = lastDefined(rsi(closes, 14));
  const m = macd(closes, 12, 26, 9);
  const macdVal = lastDefined(m.macd);
  const macdSig = lastDefined(m.signal);
  const macdHist = lastDefined(m.hist);

  // ATR needs OHLC; pass compatible candles.
  const candles = clean.map((b) => ({
    date: b.date,
    open: b.open ?? b.close,
    high: b.high ?? b.close,
    low: b.low ?? b.close,
    close: b.close,
    volume: b.volume ?? null,
  })) as PriceBar[];
  const atr14v = lastDefined(atr(candles, 14));

  const r = dailyReturns(closes);
  const volatilityPct = r.length >= 2 ? +(stdev(r) * Math.sqrt(252) * 100).toFixed(2) : null;

  const vols = clean.map((b) => b.volume ?? 0);
  const hasVol = vols.some((v) => v > 0);
  let volumeTrend: number | null = null;
  if (hasVol && vols.length >= 20) {
    const recent = vols.slice(-10).reduce((a, b) => a + b, 0) / 10;
    const base = vols.slice(-Math.min(vols.length, 50)).reduce((a, b) => a + b, 0) / Math.min(vols.length, 50);
    if (base > 0) volumeTrend = +(recent / base).toFixed(2);
  }

  let trend: TechnicalSnapshot['trend'] = 'unknown';
  if (s50 != null) {
    if (last > s50 * 1.01 && (s200 == null || s50 > s200)) trend = 'uptrend';
    else if (last < s50 * 0.99 && (s200 == null || s50 < s200)) trend = 'downtrend';
    else trend = 'sideways';
  }

  const recent20 = closes.slice(-20);
  const support = recent20.length >= 5 ? Math.min(...recent20) : null;
  const resistance = recent20.length >= 5 ? Math.max(...recent20) : null;

  return {
    bars: clean.length,
    asOf,
    last,
    sma20: s20, sma50: s50, sma200: s200,
    rsi14: r14,
    rsiState: r14 == null ? 'unknown' : r14 >= 70 ? 'overbought' : r14 <= 30 ? 'oversold' : 'neutral',
    macd: macdVal, macdSignal: macdSig, macdHist: macdHist,
    macdState: macdHist == null ? 'unknown' : macdHist >= 0 ? 'bullish' : 'bearish',
    volatilityPct,
    atr14: atr14v,
    maxDrawdownPct: maxDrawdown(closes),
    return1w: pctReturn(closes, 5),
    return1m: pctReturn(closes, 21),
    return3m: pctReturn(closes, 63),
    volumeTrend,
    trend,
    support,
    resistance,
  };
}
