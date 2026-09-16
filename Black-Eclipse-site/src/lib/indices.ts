// ── Index registry — the chart/search source of truth for market indices ─────
// Indices are NOT `Asset` rows: they live in `IndexQuote` (latest point) and are
// otherwise fetched live. Two consequences shaped this module:
//
//   1. Indices are addressed by YAHOO TICKERS (^GSPC, ^NSEI, ^FTSE, 000001.SS),
//      not by the bare TradingView ids (SPX, DJI, NIFTY) the search registry
//      used. Feeding `SPX` to the data path returned nothing because Yahoo has
//      no `SPX` instrument. `resolveIndex()` bridges both directions.
//   2. Yahoo no longer carries PSX indices (`^KSE100` 404s), so the Pakistan
//      benchmarks are `provider: 'psx'` and served from the exchange's own
//      historical endpoint. See `fetchers/psx-index.ts`.
//
// Pure data + pure helpers only — no I/O — so this is safe to bundle
// client-side (the search registry imports it) and to unit-test.

/** Where an index's price history actually comes from. */
export type IndexProvider = 'yahoo' | 'psx';

export interface IndexDef {
  /**
   * Canonical symbol used across the app: the Yahoo ticker where Yahoo serves
   * it, otherwise the exchange's own identifier. This is what goes into a
   * destination's `params.symbol`, so the chart needs no second lookup.
   */
  symbol: string;
  name: string;
  /** Home market id (US, IN, UK, PK, …). */
  market: string;
  /**
   * Names that mean THIS index in a chart context, matched case- and
   * caret-insensitively (`SPX`, `spx`, `^SPX` → `^GSPC`). Only aliases whose
   * dominant meaning is the index belong here — see `searchOnly` for the rest.
   */
  aliases: string[];
  /**
   * Aliases that match this index in a SEARCH BOX but must never be resolved
   * implicitly, because they collide with real listed instruments
   * (`DAX` → Global X DAX ETF, `STI` → Solidion Technology, `SSE` → SSE plc,
   * `000001` → a Shanghai-listed stock). Autocomplete still surfaces the index;
   * a chart request for the bare ticker keeps meaning the instrument.
   */
  searchOnly?: string[];
  provider: IndexProvider;
  /** Display currency code for the index's level. */
  currency: string;
}

/**
 * The indices worth surfacing on a chart, grouped by market. Ordered so the
 * headline benchmark for each market comes first.
 *
 * Coverage rule: only include an index whose history a provider can ACTUALLY
 * serve today (verified against the live endpoints). Indices Yahoo has dropped
 * and no other source covers (^VNINDEX, ^DFMGI, ^EGX30, ^NGXALLSH, ^IMOEX.ME,
 * ^JALSH, ^XU100, ^KOSDAQ) are deliberately absent rather than listed as broken.
 */
export const INDEX_DEFS: IndexDef[] = [
  // ── United States ──
  { symbol: '^GSPC', name: 'S&P 500', market: 'US', aliases: ['SPX', 'GSPC', 'S&P 500', 'SP500'], provider: 'yahoo', currency: 'USD' },
  { symbol: '^IXIC', name: 'Nasdaq Composite', market: 'US', aliases: ['IXIC', 'COMP', 'NASDAQ'], provider: 'yahoo', currency: 'USD' },
  { symbol: '^DJI', name: 'Dow Jones Industrial Average', market: 'US', aliases: ['DJI', 'DOW', 'DOW JONES', 'DJIA'], provider: 'yahoo', currency: 'USD' },
  { symbol: '^NDX', name: 'Nasdaq 100', market: 'US', aliases: ['NDX', 'NASDAQ 100'], provider: 'yahoo', currency: 'USD' },
  { symbol: '^RUT', name: 'Russell 2000', market: 'US', aliases: ['RUT', 'RUSSELL', 'RUSSELL 2000'], provider: 'yahoo', currency: 'USD' },
  { symbol: '^VIX', name: 'CBOE Volatility Index', market: 'US', aliases: ['VIX'], provider: 'yahoo', currency: 'USD' },

  // ── United Kingdom ──
  { symbol: '^FTSE', name: 'FTSE 100', market: 'UK', aliases: ['FTSE', 'UKX', 'FTSE100', 'FTSE 100'], provider: 'yahoo', currency: 'GBP' },
  { symbol: '^FTMC', name: 'FTSE 250', market: 'UK', aliases: ['FTSE250', 'FTSE 250'], searchOnly: ['MCX'], provider: 'yahoo', currency: 'GBP' },

  // ── Europe ──
  { symbol: '^GDAXI', name: 'DAX', market: 'DE', aliases: ['GDAXI', 'DAX 40'], searchOnly: ['DAX'], provider: 'yahoo', currency: 'EUR' },
  { symbol: '^FCHI', name: 'CAC 40', market: 'FR', aliases: ['CAC40', 'FCHI', 'CAC 40'], searchOnly: ['CAC'], provider: 'yahoo', currency: 'EUR' },
  { symbol: '^AEX', name: 'AEX', market: 'NL', aliases: ['AEX'], provider: 'yahoo', currency: 'EUR' },
  { symbol: '^STOXX50E', name: 'Euro Stoxx 50', market: 'EU', aliases: ['STOXX50', 'SX5E', 'EURO STOXX 50'], provider: 'yahoo', currency: 'EUR' },

  // ── India ──
  { symbol: '^NSEI', name: 'Nifty 50', market: 'IN', aliases: ['NIFTY', 'NIFTY50', 'NSEI', 'NIFTY 50'], provider: 'yahoo', currency: 'INR' },
  { symbol: '^BSESN', name: 'BSE Sensex', market: 'IN', aliases: ['SENSEX', 'BSESN', 'BSE SENSEX'], provider: 'yahoo', currency: 'INR' },
  { symbol: '^NSEBANK', name: 'Bank Nifty', market: 'IN', aliases: ['BANKNIFTY', 'NSEBANK'], provider: 'yahoo', currency: 'INR' },

  // ── Pakistan (Yahoo dropped these — served by the PSX endpoint) ──
  { symbol: '^KSE100', name: 'KSE 100', market: 'PK', aliases: ['KSE100', 'KSE-100', 'PSX100', 'KSE 100'], provider: 'psx', currency: 'PKR' },
  { symbol: '^KSE30', name: 'KSE 30', market: 'PK', aliases: ['KSE30', 'KSE-30', 'KSE 30'], provider: 'psx', currency: 'PKR' },
  { symbol: '^KMI30', name: 'KMI 30', market: 'PK', aliases: ['KMI30', 'KMI-30', 'KMI 30'], provider: 'psx', currency: 'PKR' },

  // ── Asia-Pacific ──
  { symbol: '^N225', name: 'Nikkei 225', market: 'JP', aliases: ['NIKKEI', 'N225', 'NIKKEI225', 'NIKKEI 225'], provider: 'yahoo', currency: 'JPY' },
  { symbol: '^HSI', name: 'Hang Seng', market: 'HK', aliases: ['HANGSENG', 'HANG SENG'], searchOnly: ['HSI'], provider: 'yahoo', currency: 'HKD' },
  { symbol: '^HSCE', name: 'Hang Seng China Enterprises', market: 'HK', aliases: ['HSCE', 'HSCEI'], provider: 'yahoo', currency: 'HKD' },
  { symbol: '^KS11', name: 'KOSPI', market: 'KR', aliases: ['KOSPI', 'KS11'], provider: 'yahoo', currency: 'KRW' },
  { symbol: '^TWII', name: 'TAIEX Weighted', market: 'TW', aliases: ['TAIEX'], searchOnly: ['TWII'], provider: 'yahoo', currency: 'TWD' },
  { symbol: '^STI', name: 'Straits Times', market: 'SG', aliases: ['STRAITS TIMES'], searchOnly: ['STI'], provider: 'yahoo', currency: 'SGD' },
  { symbol: '^KLSE', name: 'FTSE Bursa Malaysia KLCI', market: 'MY', aliases: ['KLCI', 'KLSE'], provider: 'yahoo', currency: 'MYR' },
  { symbol: '^JKSE', name: 'Jakarta Composite', market: 'ID', aliases: ['JKSE', 'IHSG'], provider: 'yahoo', currency: 'IDR' },
  { symbol: '^AXJO', name: 'S&P/ASX 200', market: 'AU', aliases: ['ASX200', 'AXJO', 'ASX 200', 'S&P/ASX 200'], provider: 'yahoo', currency: 'AUD' },
  { symbol: '000001.SS', name: 'Shanghai Composite', market: 'CN', aliases: ['SSEC', 'SHANGHAI', 'SHANGHAI COMPOSITE'], searchOnly: ['000001'], provider: 'yahoo', currency: 'CNY' },
  { symbol: '399001.SZ', name: 'Shenzhen Component', market: 'CN', aliases: ['SZSE', 'SHENZHEN', 'SHENZHEN COMPONENT'], searchOnly: ['399001'], provider: 'yahoo', currency: 'CNY' },

  // ── Americas / Middle East ──
  { symbol: '^GSPTSE', name: 'S&P/TSX Composite', market: 'CA', aliases: ['GSPTSE', 'S&P/TSX', 'S&P/TSX COMPOSITE'], searchOnly: ['TSX'], provider: 'yahoo', currency: 'CAD' },
  { symbol: '^BVSP', name: 'Ibovespa', market: 'BR', aliases: ['IBOV', 'IBOVESPA', 'BVSP'], provider: 'yahoo', currency: 'BRL' },
  { symbol: '^MXX', name: 'IPC Mexico', market: 'MX', aliases: ['MXX', 'IPC MEXICO'], searchOnly: ['IPC'], provider: 'yahoo', currency: 'MXN' },
  { symbol: '^TASI.SR', name: 'Tadawul All Share', market: 'SA', aliases: ['TASI', 'TADAWUL', 'TADAWUL ALL SHARE'], provider: 'yahoo', currency: 'SAR' },
];

/**
 * Normalize a symbol for matching: uppercase, strip separator punctuation, but
 * PRESERVE a leading caret. The caret is load-bearing — `^STI` (Straits Times)
 * and `STI` (Solidion Technology) are different instruments — so it must not be
 * discarded globally. Caret-insensitivity is instead handled by registering the
 * caret-prefixed key for each implicit alias (see `BY_KEY` below).
 */
function normalizeKey(raw: string): string {
  return raw.trim().toUpperCase().replace(/[\s._-]+/g, '');
}

const BY_KEY = new Map<string, IndexDef>();
for (const def of INDEX_DEFS) {
  // The canonical symbol matches as written (e.g. `^STI`, `000001.SS`).
  const canonical = normalizeKey(def.symbol);
  if (!BY_KEY.has(canonical)) BY_KEY.set(canonical, def);

  // Implicit aliases match with AND without a caret, so `SPX`, `^SPX` and
  // `GSPC` all reach the S&P 500. A bare alias can only enter this map if the
  // index owns it outright — collision-prone tickers live in `searchOnly`.
  for (const alias of def.aliases) {
    for (const key of [normalizeKey(alias), `^${normalizeKey(alias)}`]) {
      if (!BY_KEY.has(key)) BY_KEY.set(key, def);
    }
  }
}

/**
 * Resolve a user-supplied symbol to an index definition, or undefined when it is
 * not a known index. Case-insensitive, and caret-insensitive for the aliases
 * that are unambiguously the index (`SPX`, `spx`, `^SPX` → `^GSPC`).
 *
 * Deliberately conservative: aliases that collide with real listed instruments
 * live in `searchOnly` and are NOT resolved here, so charting `DAX` still means
 * the Global X DAX ETF and only an explicit `^GDAXI` (or a search pick) selects
 * the index.
 */
export function resolveIndex(symbol: string | null | undefined): IndexDef | undefined {
  if (!symbol) return undefined;
  return BY_KEY.get(normalizeKey(symbol));
}

/** True when the symbol is an index served by the PSX endpoint. */
export function isPsxIndex(symbol: string): boolean {
  return resolveIndex(symbol)?.provider === 'psx';
}

/** Currency for a resolved index, or undefined when it is not an index. */
export function indexCurrency(symbol: string): string | undefined {
  return resolveIndex(symbol)?.currency;
}

/**
 * Find indices matching a free-text query, best-first. Searches the name and
 * BOTH alias lists (implicit + `searchOnly`), so typing "DAX" or "000001"
 * surfaces the index in autocomplete without changing what those tickers
 * resolve to on a chart.
 */
export function searchIndices(query: string, limit = 6): IndexDef[] {
  const q = normalizeKey(query).replace(/^\^/, '');
  if (!q) return [];
  const scored: Array<{ def: IndexDef; score: number }> = [];
  for (const def of INDEX_DEFS) {
    // The caret is stripped for SEARCH so typing "^GSPC" still matches.
    const keys = [def.symbol, ...def.aliases, ...(def.searchOnly ?? [])]
      .map((k) => normalizeKey(k).replace(/^\^/, ''));
    let score = 0;
    for (const k of keys) {
      if (k === q) score = Math.max(score, 100);
      else if (k.startsWith(q)) score = Math.max(score, 60);
      else if (k.includes(q)) score = Math.max(score, 30);
    }
    const name = normalizeKey(def.name);
    if (name.includes(q)) score = Math.max(score, 40);
    if (score > 0) scored.push({ def, score });
  }
  return scored.sort((a, b) => b.score - a.score).slice(0, limit).map(s => s.def);
}
