// ── Price-history transports ────────────────────────────────────────────────
// The FIRST transport is the batched yfinance bridge: one Python process that
// returns the whole series (good for batches, fine offline). This module is the
// SECOND transport: the DIRECT Yahoo v8 chart request that already backs
// `/api/price-history` — the same provider data through one plain HTTP request
// with no Python. It is reached only when the bridge is off or returns no
// series, so a machine without the Python stack still gets history.
//
// Provenance stays honest: the provider id is `yfinance` (the app's provider
// label for Yahoo data, shared with the price-history route) and the transport
// is named separately (`yahoo-chart`), never conflated with the bridge.

import {
  fetchYahooChartSeries,
  timestampWithinWindow,
  windowBounds,
  yahooChartCandidates,
  type Bar,
} from "@/lib/scraper/yahoo-chart";

export interface HistoryFallback {
  series: Bar[];
  ticker: string;
  provider: string;
  transport: "yahoo-chart";
}

/**
 * Try the direct chart transport across the per-market Yahoo candidate chain
 * (thin venues have fallback suffixes). Returns the first series with at least
 * two real bars, or null — never a fabricated or partial single point. When a
 * window is given it is sent to the provider AND enforced on the bars, so a
 * caller can never receive head/tail-truncated full history in place of its
 * requested span.
 */
export async function fetchHistorySeriesFallback(
  symbol: string,
  market: string,
  range: string,
  interval: string,
  window?: { start?: string; end?: string },
): Promise<HistoryFallback | null> {
  const bounds = windowBounds(window?.start, window?.end);
  const windowArg = window && (window.start || window.end) ? window : undefined;
  for (const ticker of yahooChartCandidates(symbol, market)) {
    const chart = windowArg
      ? await fetchYahooChartSeries(ticker, range, interval, windowArg)
      : await fetchYahooChartSeries(ticker, range, interval);
    if (chart && chart.bars.length >= 2) {
      const series = chart.bars.filter((b) => timestampWithinWindow(b.date, bounds));
      if (series.length >= 2) {
        return { series, ticker, provider: "yfinance", transport: "yahoo-chart" };
      }
    }
  }
  return null;
}

/**
 * A symbol the instrument master does not hold, but Yahoo serves: an index
 * (`^VIX`), a future (`GC=F`) or a currency index (`DX-Y.NYB`).
 *
 * These are MARKET DATA, not equities: there is no instrument row for them,
 * and refusing them is a coverage gap, not a safety rule. They are fetched
 * straight from Yahoo and labelled as market data - never as a stored
 * instrument, and never as an equity identity.
 */
export function isMarketDataSymbol(symbol: string): boolean {
  const value = symbol.trim().toUpperCase();
  if (!value) return false;
  if (value.startsWith("^")) return true;                 // an index
  if (/^[A-Z0-9.]+=[A-Z]$/.test(value)) return true;       // a future
  if (value.startsWith("DX-")) return true;                // a currency index
  return false;
}

/** The coarse class a market-data symbol carries. */
export function marketDataAssetClass(symbol: string): "index" | "commodity" | "fx" {
  const value = symbol.trim().toUpperCase();
  if (value.startsWith("DX-")) return "fx";
  if (value.includes("=")) return "commodity";
  return "index";
}

/**
 * The history of a market-data symbol, straight from Yahoo.
 *
 * The same direct chart transport the equity path falls back to, without the
 * instrument-master gate: an index or a future has no master row, and the
 * provider serves it fine.
 */
export async function fetchMarketDataHistory(
  symbol: string,
  range: string,
  interval: string,
  window?: { start?: string; end?: string },
): Promise<HistoryFallback | null> {
  const bounds = windowBounds(window?.start, window?.end);
  const windowArg = window && (window.start || window.end) ? window : undefined;
  for (const ticker of yahooChartCandidates(symbol, "US")) {
    const chart = windowArg
      ? await fetchYahooChartSeries(ticker, range, interval, windowArg)
      : await fetchYahooChartSeries(ticker, range, interval);
    if (chart && chart.bars.length >= 2) {
      const series = chart.bars.filter((b) => timestampWithinWindow(b.date, bounds));
      if (series.length >= 2) {
        return { series, ticker, provider: "yfinance", transport: "yahoo-chart" };
      }
    }
  }
  return null;
}

/**
 * The bar sizes Yahoo understands.
 */
const BAR_SIZES = new Set([
  "1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo",
]);

/**
 * The windows Yahoo understands ("1y" = the last year of daily bars).
 */
const HISTORY_WINDOWS = new Set([
  "1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max",
]);

/**
 * Read a history request's BAR SIZE and WINDOW.
 *
 * These are DIFFERENT fields and conflating them was a real bug: `period` was
 * read as the interval, so a request for `period: "1y"` asked the provider for
 * a "1y bar" - not a bar size at all. The request came back EMPTY, and a
 * multi-year history read as "no data" (or, when it did answer, as a handful
 * of monthly bars).
 *
 * The rules:
 *   * `interval` is a BAR SIZE ("1d").
 *   * `period` / `range` is a WINDOW ("1y", "5y", "max").
 *   * a value that is BOTH ("1d", "1mo", "3mo") is a WINDOW: a caller asking
 *     for "1mo" wants a month of bars, not monthly bars.
 *   * a bar-size-ONLY value ("1h", "5m", "1wk") in `period` is a BAR SIZE.
 */
export function resolveHistoryParams(params: Record<string, unknown>): {
  interval: string;
  window: string;
  start?: string;
  end?: string;
} {
  const rawInterval = String(params.interval ?? "").trim().toLowerCase();
  const rawPeriod = String(params.period ?? "").trim().toLowerCase();
  const rawRange = String(params.range ?? "").trim().toLowerCase();
  const barSizeOnly = new Set([
    "1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1wk",
  ]);
  const interval = BAR_SIZES.has(rawInterval)
    ? rawInterval
    : barSizeOnly.has(rawPeriod)
      ? rawPeriod
      : "1d";
  const window = HISTORY_WINDOWS.has(rawPeriod)
    ? rawPeriod
    : HISTORY_WINDOWS.has(rawRange)
      ? rawRange
      : "1y";
  return {
    interval,
    window,
    ...(typeof params.start === "string" ? { start: params.start } : {}),
    ...(typeof params.end === "string" ? { end: params.end } : {}),
  };
}
