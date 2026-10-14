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
