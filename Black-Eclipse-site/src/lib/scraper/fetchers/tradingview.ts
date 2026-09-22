// TradingView scanner fetcher — the PRIMARY whole-market quote strategy.
//
// One POST to scanner.tradingview.com/<country>/scan returns the ENTIRE market
// (price, market_cap, P/E, EPS, sector, industry, 52w high/low, beta, volume,
// change, dividend) in ~1 second. This replaces the slow per-symbol yfinance
// bridge for whole-universe refreshes.
//
// Country slugs + exchange filters mirror the market-screener skill (verified):
//   - `germany` is polluted with ~35k secondary-venue dupes → filter XETR
//   - `saudi_arabia` → filter TADAWUL
//   - `canada` carries TSX/TSXV/CSE/NEO (all kept, deduped by symbol)
//   - `india` carries NSE+BSE (deduped, NSE preferred)
//   - `japan` carries TSE + regional (deduped, TSE preferred)
//
// Response shape: { totalCount, data: [ { s: "EXCH:CODE", d: [col0, col1, ...] } ] }

import type { FetchResult, Quote, ScanRow } from "../types";
import { toErrorLike } from "../types";

// Country/market id → TradingView scanner slug.
// Only markets routed through TradingView need an entry. Markets absent from
// this map fall back to the yfinance bridge (e.g. US stays on yfinance).
export const MARKET_SLUG: Record<string, string> = {
  CN: "china",
  CA: "canada",
  DE: "germany",
  IN: "india",
  TW: "taiwan",
  HK: "hongkong",
  JP: "japan",
  KR: "korea",
  FR: "france",
  AU: "australia",
  SG: "singapore",
  SA: "ksa", // TradingView slug for Saudi Arabia (TADAWUL); 'saudi_arabia' 404s
  QA: "qatar",
  KW: "kuwait",
  CH: "switzerland",
  PK: "pakistan",
  TR: "turkey",
};

// Exchange filters per market (comma-separated) to cut duplicate-venue noise.
// Empty string = no filter (scan covers the whole country cleanly).
export const MARKET_EXCHANGE_FILTER: Record<string, string> = {
  DE: "XETR", // drop ~35k GETTEX/Tradegate secondary-venue dupes
  SA: "TADAWUL",
};

// TradingView country → the exchange codes that are "real" primary listings.
// Used to dedupe dual listings, preferring the most liquid venue (mirrors the
// market-screener skill's dedup rule).
export const PREFERRED_EXCHANGE: Record<string, string[]> = {
  IN: ["NSE", "BSE"],
  CA: ["TSX", "TSXV", "CSE", "NEO"],
  JP: ["TSE"],
};

/** Columns requested from the scanner, in order. Index = position in `d[]`. */
const COLUMNS = [
  "name", // 0 — ticker-ish; many markets return the bare ticker here
  "description", // 1 — the human-readable company name (e.g. "786 Investments Limited")
  "close", // 2
  "market_cap_basic", // 3
  "type", // 4
  "currency", // 5
  "sector", // 6
  "industry", // 7
  "volume", // 8
  "price_earnings_ttm", // 9
  "earnings_per_share_basic_ttm", // 10
  "dividend_yield_recent", // 11
  "price_52_week_high", // 12
  "price_52_week_low", // 13
  "beta_1_year", // 14
  "change", // 15
];

// Map a bare symbol to its Yahoo suffix per market (kept in sync with
// fetchers/yfinance.ts MARKET_SUFFIX so downstream gap-filling works).
export const MARKET_SUFFIX: Record<string, string> = {
  CN: ".SS", // refined per-prefix in yahooSymbol()
  CA: ".TO",
  DE: ".DE",
  IN: ".NS",
  TW: ".TW",
  HK: ".HK",
  JP: ".T",
  KR: ".KS",
  FR: ".PA",
  AU: ".AX",
  SG: ".SI",
  SA: ".SR",
  QA: ".QA",
  KW: ".KW",
  CH: ".SW",
  PK: ".PSX",
  TR: ".IS",
};

/**
 * Convert an absolute price change into a percentage.
 *
 * The TradingView scanner's `change` column is ABSOLUTE (e.g. -1.25), not a
 * percentage. JDDS stores `changePct` everywhere, so derive it from
 * (close − change) = previous close, guarding against divide-by-zero and
 * sign flips when a price crosses zero.
 */
export function changePctFromAbsolute(close: number, change: number): number {
  if (!Number.isFinite(close) || !Number.isFinite(change) || close === 0) return 0;
  const prevClose = close - change;
  if (!Number.isFinite(prevClose) || prevClose === 0) return 0;
  return +((change / Math.abs(prevClose)) * 100).toFixed(4);
}

/** Resolve a bare symbol to its Yahoo ticker (for the yfinance fallback path). */
export function yahooSymbol(symbol: string, market: string): string {
  const suffix = MARKET_SUFFIX[market] ?? "";
  const sym = symbol.trim();
  // China: 6xxxxx -> .SS, 0/3xxxxx -> .SZ, 4/8xxxxx -> .BJ
  if (market === "CN" && /^\d{6}$/.test(sym)) {
    if (sym.startsWith("0") || sym.startsWith("3")) return `${sym}.SZ`;
    if (sym.startsWith("4") || sym.startsWith("8")) return `${sym}.BJ`;
    return `${sym}.SS`;
  }
  if (!suffix) return sym;
  if (sym.endsWith(suffix)) return sym;
  return `${sym}${suffix}`;
}

/** Strip an exchange prefix like "SEHK:" or "TWSE:" from a raw code. */
function bareSymbol(raw: string): string {
  const parts = raw.split(":");
  return parts[parts.length - 1].trim();
}

/**
 * Run a TradingView scan for a market. Returns up to `range` rows.
 * Throws on HTTP/network failure; returns an empty array on a clean 200 with
 * no data (market not covered).
 */
export async function scanMarket(
  market: string,
  range = 20000
): Promise<ScanRow[]> {
  const slug = MARKET_SLUG[market];
  if (!slug) return [];

  const filter = MARKET_EXCHANGE_FILTER[market];
  const query: Record<string, unknown> = { types: ["stock"] };
  // Exchange filtering uses the scan `filter` array (left/operation/right),
  // NOT `query.exchange` which the scanner ignores. E.g. DE → XETR only.
  const scanFilter = filter
    ? [{ left: "exchange", operation: "equal", right: filter }]
    : [];

  const payload = {
    symbols: { tickers: [], query },
    columns: COLUMNS,
    filter: scanFilter,
    sort: { sortBy: "name", sortOrder: "asc" },
    range: [0, range],
  };

  const res = await fetch(`https://scanner.tradingview.com/${slug}/scan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    // Allow the whole market to return. Very large markets (CA ~4.7k, DE ~35k
    // rows before the XETR filter) can exceed 60s, so use a generous timeout.
    signal: AbortSignal.timeout(180000),
  });

  if (!res.ok) {
    throw new Error(`TradingView scan ${market} failed: HTTP ${res.status}`);
  }

  const json = (await res.json()) as {
    totalCount?: number;
    data?: Array<{ s: string; d: unknown[] }>;
  };

  const rows: ScanRow[] = [];
  for (const item of json.data || []) {
    const d = item.d || [];
    const type = String(d[4] ?? "stock");
    // Only keep real stocks (drop funds/bonds/indices/ETFs).
    if (type !== "stock") continue;
    const price = Number(d[2]);
    if (!price || price <= 0) continue;
    const rawSym = bareSymbol(item.s);
    // `description` (col 1) carries the real company name; the `name` column
    // often just repeats the ticker (e.g. PSX "786", HKEX "1", TSE "1301"),
    // which rendered numeric junk in the screener. Fall back to the ticker
    // only when the description is missing.
    const displayName = String(d[1] ?? "").trim() || String(d[0] ?? "").trim() || rawSym;
    rows.push({
      symbol: rawSym,
      exchange: item.s.split(":")[0],
      name: displayName,
      price,
      // `change` (col 15) is absolute — convert to the % JDDS stores.
      changePct: changePctFromAbsolute(price, Number(d[15]) || 0),
      marketCap: numOrUndef(d[3]),
      volume: numOrUndef(d[8]),
      peRatio: numOrUndef(d[9]),
      eps: numOrUndef(d[10]),
      dividendYield: numOrUndef(d[11]),
      fiftyTwoWeekHigh: numOrUndef(d[12]),
      fiftyTwoWeekLow: numOrUndef(d[13]),
      beta: numOrUndef(d[14]),
      sector: strOrNull(d[6]),
      industry: strOrNull(d[7]),
      yahooSymbol: yahooSymbol(rawSym, market),
    });
  }

  return rows;
}

// ─── Cached whole-market scans ──────────────────────────────────────────
// A full scan costs one large HTTP round-trip (up to ~180s for big markets).
// The adaptive fallback chain used to trigger a FRESH scan for every missed
// symbol — a burst of delisted tickers could fan out into dozens of identical
// multi-minute requests. These helpers make per-symbol lookups reuse a recent
// scan, dedupe concurrent callers onto one in-flight request, and bound how
// many scans may run at once.

const SCAN_CACHE_TTL_MS = 10 * 60 * 1000;
const MAX_CONCURRENT_SCANS = 2;

interface CacheEntry {
  rows: ScanRow[];
  at: number;
}
const scanCache = new Map<string, CacheEntry>();
const scanInFlight = new Map<string, Promise<ScanRow[]>>();
let activeScans = 0;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Whole-market scan with short-TTL caching and in-flight dedup.
 * Universe syncs that REQUIRE fresh data should call scanMarket() directly;
 * everything else (per-symbol lookups, UI probes) should use this.
 */
export async function getCachedMarketScan(market: string): Promise<ScanRow[]> {
  const cached = scanCache.get(market);
  if (cached && Date.now() - cached.at < SCAN_CACHE_TTL_MS) return cached.rows;

  const inFlight = scanInFlight.get(market);
  if (inFlight) return inFlight;

  const task = (async () => {
    // Concurrency cap: queue instead of hammering the scanner endpoint.
    while (activeScans >= MAX_CONCURRENT_SCANS) {
      await sleep(1000);
    }
    activeScans++;
    try {
      const rows = await scanMarket(market);
      scanCache.set(market, { rows, at: Date.now() });
      return rows;
    } finally {
      activeScans--;
      scanInFlight.delete(market);
    }
  })();
  scanInFlight.set(market, task);
  return task;
}

/** Markets whose primary source is TradingView (used by refresh/sync paths). */
export function isTradingViewMarket(market: string): boolean {
  return MARKET_SLUG[market] !== undefined;
}

/**
 * Per-symbol quote via a cached whole-market scan (used by the adaptive
 * fallback chain when a specific symbol isn't in JDDS yet). Uses the shared
 * scan cache + concurrency cap so a burst of misses cannot fan out into a
 * storm of full-market requests.
 */
export async function fetchTradingViewQuote(
  symbol: string,
  market: string
): Promise<FetchResult> {
  if (!isTradingViewMarket(market)) {
    return { status: "empty", error: "market not TV-covered", source: "tradingview" };
  }
  try {
    const rows = await getCachedMarketScan(market);
    const found = rows.find(
      (r) =>
        r.symbol === symbol ||
        r.yahooSymbol === symbol ||
        r.symbol === symbol.split(".")[0]
    );
    if (!found) {
      return { status: "empty", error: "symbol not in scan", source: "tradingview" };
    }
    const quote: Quote = {
      symbol,
      name: found.name,
      price: found.price,
      changePct: found.changePct,
      marketCap: found.marketCap,
      volume: found.volume,
      // TV scans one market, so the row IS from this market — record it so the
      // bridge's identity check can confirm the venue.
      market: market.trim().toUpperCase(),
    };
    return { status: "ok", quote, source: "tradingview" };
  } catch (err) {
    const e = toErrorLike(err);
    return { status: "network_error", error: e.message || "TV scan failed", source: "tradingview" };
  }
}

function numOrUndef(v: unknown): number | undefined {
  const n = Number(v);
  return Number.isFinite(n) && n !== 0 ? n : undefined;
}

function strOrNull(v: unknown): string | null {
  if (typeof v !== "string") return null;
  const s = v.trim();
  return s && s.toLowerCase() !== "nan" ? s : null;
}
