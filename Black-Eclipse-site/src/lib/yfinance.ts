// yfinance quote fetcher — pulls live prices from Yahoo Finance through the
// Python yfinance bridge (scripts/yfinance_bridge.py), which batches symbols
// over ONE shared session instead of one HTTP round-trip per symbol, and
// normalizes them into the shape the JDDS Price model expects. Used by the
// /api/refresh route to keep the market screener's prices current.

import { fetchYahooBatchQuote } from "@/lib/scraper/fetchers/yfinance";

// Single source of truth for Yahoo ticker suffixes lives in
// src/lib/scraper/fetchers/yfinance.ts (kept in sync with the Python bridge).
export { MARKET_SUFFIX, yahooSymbol } from "@/lib/scraper/fetchers/yfinance";

export interface YahooQuote {
  symbol: string;
  price: number;
  changePct: number;
  previousClose: number | null;
  marketCap: number | null;
  volume: number | null;
  peRatio: number | null;
  forwardPE: number | null;
  dividendYield: number | null;
  dayHigh: number | null;
  dayLow: number | null;
  open: number | null;
  fiftyTwoWeekHigh: number | null;
  fiftyTwoWeekLow: number | null;
}

/**
 * Fetch a live quote for a symbol in a market from Yahoo Finance via the
 * batched yfinance bridge. Returns null on any failure (no Python, network,
 * 404, no price).
 */
export async function fetchYahooQuote(
  symbol: string,
  market: string
): Promise<YahooQuote | null> {
  try {
    const result = await fetchYahooBatchQuote([symbol], market);
    const first = result[0];
    if (first?.status !== "ok" || !first.quote) return null;
    const q = first.quote;
    return {
      symbol,
      price: q.price,
      changePct: q.changePct,
      previousClose: q.changePct !== 0 ? q.price / (1 + q.changePct / 100) : q.price,
      marketCap: null,
      volume: q.volume ?? null,
      peRatio: null,
      forwardPE: null,
      dividendYield: null,
      dayHigh: null,
      dayLow: null,
      open: null,
      fiftyTwoWeekHigh: null,
      fiftyTwoWeekLow: null,
    };
  } catch {
    return null;
  }
}
