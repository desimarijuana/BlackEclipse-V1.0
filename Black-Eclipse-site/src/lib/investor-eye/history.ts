// ── Investor Eye — market history backfill (Phase 4.3) ───────────────────────
// Historical analogues were permanently `UNAVAILABLE` because the `Candles`
// table was empty. Rather than build a second market-data path, this reuses the
// EXISTING alerts feed (`updateCandleCache` → the yfinance OHLC bridge) to warm
// the candle cache for the index instruments Investor Eye cares about.
//
// Honest by construction: a symbol with no usable history is simply absent, and
// the analogues view keeps reporting UNAVAILABLE for it — never a synthetic
// series.

import { prisma } from '@/lib/db';
import { updateCandleCache } from '@/lib/alerts/dataFeeds';
import { toMarketId } from '@/lib/markets';

export const IE_HISTORY_TIMEFRAME = '1d';
export const IE_HISTORY_LOOKBACK = 260; // ~1 trading year

/**
 * The index instruments shown on the map, keyed by the JDDS market they belong
 * to. Mirrors the symbol set in `state.ts` (MARKET_INDEX) so the history lines
 * up with the observations the layers already render.
 */
const HISTORY_UNIVERSE: Array<{ market: string; symbol: string }> = [
  { market: 'US', symbol: '^GSPC' },
  { market: 'US', symbol: '^IXIC' },
  { market: 'US', symbol: '^DJI' },
  { market: 'US', symbol: 'GC=F' },
  { market: 'US', symbol: 'CL=F' },
  { market: 'US', symbol: 'BTC-USD' },
  { market: 'CA', symbol: '^GSPTSE' },
  { market: 'MX', symbol: '^MXX' },
  { market: 'BR', symbol: '^BVSP' },
  { market: 'UK', symbol: '^FTSE' },
  { market: 'DE', symbol: '^GDAXI' },
  { market: 'FR', symbol: '^FCHI' },
  { market: 'NL', symbol: '^AEX' },
  { market: 'JP', symbol: '^N225' },
  { market: 'KR', symbol: '^KS11' },
  { market: 'CN', symbol: '000001.SS' },
  { market: 'HK', symbol: '^HSI' },
  { market: 'TW', symbol: '^TWII' },
  { market: 'SG', symbol: '^STI' },
  { market: 'MY', symbol: '^KLSE' },
  { market: 'AU', symbol: '^AXJO' },
  { market: 'IN', symbol: '^NSEI' },
  { market: 'ID', symbol: '^JKSE' },
  { market: 'TH', symbol: '^SET.BK' },
  { market: 'VN', symbol: '^VNINDEX' },
  { market: 'SA', symbol: '^TASI.SR' },
  { market: 'AE', symbol: '^DFMGI' },
  { market: 'ZA', symbol: '^JALSH' },
  { market: 'TR', symbol: '^XU100' },
  { market: 'RU', symbol: '^IMOEX.ME' },
];

let backfilling = false;

export function isBackfilling(): boolean {
  return backfilling;
}

/**
 * Backfill daily candles for the index universe. Bounded and best-effort: it
 * writes through the existing alerts cache path, yields between markets, and
 * never throws (a failure just leaves that symbol without history).
 */
export async function backfillMarketHistory(
  options: { symbols?: string[]; lookback?: number; onProgress?: (msg: string) => void } = {},
): Promise<{ requested: number; written: number; failed: string[] }> {
  if (backfilling) return { requested: 0, written: 0, failed: ['already running'] };
  backfilling = true;
  const lookback = options.lookback ?? IE_HISTORY_LOOKBACK;
  const want = options.symbols ? new Set(options.symbols) : null;
  const universe = want
    ? HISTORY_UNIVERSE.filter((e) => want.has(e.symbol) || want.has(e.market))
    : HISTORY_UNIVERSE;

  let written = 0;
  const failed: string[] = [];

  try {
    // Group by market so each call batches symbols that share a ticker suffix.
    const byMarket = new Map<string, string[]>();
    for (const e of universe) {
      const arr = byMarket.get(e.market) ?? [];
      arr.push(e.symbol);
      byMarket.set(e.market, arr);
    }

    for (const [marketId, symbols] of byMarket) {
      const market = toMarketId(marketId);
      try {
        // `updateCandleCache` handles chunking (≤50/req) and skips invalid
        // bars; it writes the composite-key upsert itself.
        const n = await updateCandleCache(market, symbols, IE_HISTORY_TIMEFRAME, lookback);
        written += n;
        options.onProgress?.(`${market}: ${n} bars`);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        failed.push(`${market}: ${msg}`);
      }
      // Yield so the synchronous SQLite writer never starves HTTP requests.
      await new Promise((r) => setImmediate(r));
    }
  } finally {
    backfilling = false;
  }

  return { requested: universe.length, written, failed };
}

/** How much daily history exists for a symbol (drives honest UI messaging). */
export async function historyCoverage(symbol: string): Promise<{ bars: number; from: string | null; to: string | null }> {
  try {
    const agg = await prisma.candles.aggregate({
      where: { symbol, timeframe: IE_HISTORY_TIMEFRAME },
      _count: true,
      _min: { ts: true },
      _max: { ts: true },
    });
    return {
      bars: agg._count ?? 0,
      from: agg._min.ts?.toISOString() ?? null,
      to: agg._max.ts?.toISOString() ?? null,
    };
  } catch {
    return { bars: 0, from: null, to: null };
  }
}

/** Which of the Investor Eye index symbols currently have usable history. */
export async function historyStatus(): Promise<Array<{ symbol: string; market: string; bars: number }>> {
  const rows = await prisma.candles.groupBy({
    by: ['symbol'],
    where: { timeframe: IE_HISTORY_TIMEFRAME },
    _count: true,
  });
  const bySymbol = new Map(rows.map((r) => [r.symbol, r._count]));
  return HISTORY_UNIVERSE.map((e) => ({ ...e, bars: bySymbol.get(e.symbol) ?? 0 }));
}

export { HISTORY_UNIVERSE };
