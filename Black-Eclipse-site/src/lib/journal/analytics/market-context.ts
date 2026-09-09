// ── Market Context — auto-associate market conditions with a trade ───────────
// Computes trend, VWAP, EMA, ADX, ATR, regime and volatility from a price
// series around the trade's entry. Decoupled from any provider — it just
// consumes OHLCV bars.

import type { PricePoint } from "./mfe-mae";

export interface MarketContextResult {
  trend: "Bullish" | "Bearish" | "Neutral";
  vwap: "above" | "below" | null;
  ema50AboveEma200: boolean | null;
  adx: number | null;
  atr: number | null;
  regime: "Trending" | "Ranging";
  volatility: "low" | "medium" | "high";
  session: string | null;
}

/** Simple moving average. */
function sma(values: number[], period: number): number | null {
  if (values.length < period) return null;
  const slice = values.slice(-period);
  return slice.reduce((s, v) => s + v, 0) / period;
}

/** Exponential moving average. */
function ema(values: number[], period: number): number | null {
  if (values.length < period) return null;
  const k = 2 / (period + 1);
  let e = values.slice(0, period).reduce((s, v) => s + v, 0) / period;
  for (let i = period; i < values.length; i++) {
    e = values[i] * k + e * (1 - k);
  }
  return e;
}

/** Average True Range. */
function atr(bars: PricePoint[], period: number): number | null {
  if (bars.length < period + 1) return null;
  const trs: number[] = [];
  for (let i = 1; i < bars.length; i++) {
    const prevClose = bars[i - 1].close;
    const high = bars[i].high ?? bars[i].close;
    const low = bars[i].low ?? bars[i].close;
    const tr = Math.max(high - low, Math.abs(high - prevClose), Math.abs(low - prevClose));
    trs.push(tr);
  }
  if (trs.length < period) return null;
  return trs.slice(-period).reduce((s, v) => s + v, 0) / period;
}

/** Average Directional Index (simplified). */
function adx(bars: PricePoint[], period: number): number | null {
  if (bars.length < period * 2) return null;
  let plusDM = 0, minusDM = 0, trSum = 0;
  for (let i = 1; i < bars.length; i++) {
    const high = bars[i].high ?? bars[i].close;
    const low = bars[i].low ?? bars[i].close;
    const prevHigh = bars[i - 1].high ?? bars[i - 1].close;
    const prevLow = bars[i - 1].low ?? bars[i - 1].close;
    const upMove = high - prevHigh;
    const downMove = prevLow - low;
    plusDM += upMove > downMove && upMove > 0 ? upMove : 0;
    minusDM += downMove > upMove && downMove > 0 ? downMove : 0;
    trSum += Math.max(high - low, Math.abs(high - prevHigh), Math.abs(low - prevLow));
  }
  if (trSum <= 0) return null;
  const plusDI = (plusDM / trSum) * 100;
  const minusDI = (minusDM / trSum) * 100;
  const dx = plusDI + minusDI > 0 ? (Math.abs(plusDI - minusDI) / (plusDI + minusDI)) * 100 : 0;
  return dx;
}

/** Volume-weighted average price over the lookback window. */
function vwap(bars: PricePoint[], period: number): number | null {
  const slice = bars.slice(-period);
  let pv = 0, v = 0;
  for (const b of slice) {
    const vol = b.volume ?? 0;
    const typical = (b.high ?? b.close) + (b.low ?? b.close) + b.close;
    pv += (typical / 3) * vol;
    v += vol;
  }
  return v > 0 ? pv / v : null;
}

/**
 * Compute market context for a trade from the price series leading up to entry.
 *
 * @param series  chronological price bars
 * @param entryPrice the trade's entry price
 * @param entryTime ISO entry time
 */
export function computeMarketContext(
  series: PricePoint[],
  entryPrice: number,
  entryTime: string,
): MarketContextResult {
  const entryTs = Date.parse(entryTime);
  // Bars up to and including the entry.
  const upToEntry = series.filter((b) => {
    const ts = Date.parse(b.date);
    return !Number.isNaN(ts) && (!entryTs || ts <= entryTs);
  });
  if (upToEntry.length < 20) {
    return { trend: "Neutral", vwap: null, ema50AboveEma200: null, adx: null, atr: null, regime: "Ranging", volatility: "medium", session: null };
  }

  const closes = upToEntry.map((b) => b.close);
  const last = closes[closes.length - 1];

  // Trend: EMA50 vs EMA200, or price vs SMA50.
  const e50 = ema(closes, 50);
  const e200 = ema(closes, 200);
  const s50 = sma(closes, 50);
  const ema50AboveEma200 = e50 != null && e200 != null ? e50 > e200 : null;
  const trend: MarketContextResult["trend"] =
    e50 != null && e200 != null
      ? e50 > e200 ? "Bullish" : e50 < e200 ? "Bearish" : "Neutral"
      : s50 != null
        ? last > s50 ? "Bullish" : last < s50 ? "Bearish" : "Neutral"
        : "Neutral";

  // VWAP position.
  const vw = vwap(upToEntry, 20);
  const vwapPos: MarketContextResult["vwap"] = vw != null ? (last >= vw ? "above" : "below") : null;

  // ADX + ATR.
  const adxVal = adx(upToEntry, 14);
  const atrVal = atr(upToEntry, 14);
  const regime: MarketContextResult["regime"] = adxVal != null && adxVal >= 25 ? "Trending" : "Ranging";

  // Volatility: ATR as % of price.
  let volatility: MarketContextResult["volatility"] = "medium";
  if (atrVal != null && last > 0) {
    const atrPct = (atrVal / last) * 100;
    volatility = atrPct > 2 ? "high" : atrPct < 0.8 ? "low" : "medium";
  }

  // Session from entry hour (UTC).
  const d = new Date(entryTs);
  const h = d.getUTCHours();
  const session = h >= 0 && h < 7 ? "Asia" : h >= 7 && h < 13 ? "London" : h >= 13 && h < 21 ? "New York" : "Sydney";

  return { trend, vwap: vwapPos, ema50AboveEma200, adx: adxVal, atr: atrVal, regime, volatility, session };
}
