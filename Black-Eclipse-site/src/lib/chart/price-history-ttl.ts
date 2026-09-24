// ── Price-history cache TTL by interval ──────────────────────────────────────
// Pure, dependency-free. The chart route and the client subscription manager
// both cache OHLCV series; a single flat TTL made intraday candles lag badly
// (a 1-minute series was reused for 10 minutes, twice over). This maps a Yahoo
// interval to a sensible lifetime: seconds for 1m, minutes for intraday, and
// the long default for daily and above (a day bar does not change intraday).

export const DAILY_HISTORY_TTL_MS = 10 * 60 * 1000;

/** Cache lifetime for a Yahoo chart interval. Unknown intervals get the daily TTL. */
export function ttlForInterval(interval: string): number {
  switch (interval) {
    case "1m": return 30 * 1000;
    case "5m": return 60 * 1000;
    case "15m":
    case "30m": return 2 * 60 * 1000;
    case "60m": return 5 * 60 * 1000;
    default: return DAILY_HISTORY_TTL_MS;
  }
}
