// yfinance quote fetcher — pulls live prices from Yahoo Finance's public
// chart endpoint (no API key required) and normalizes them into the shape the
// JDDS Price model expects. Used by the /api/refresh route to keep the market
// screener's prices current.

const CHART_ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart";

const USER_AGENT =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";

// Market id → Yahoo ticker suffix. Empty means the symbol is already Yahoo-ready.
const MARKET_SUFFIX: Record<string, string> = {
  US: "",
  PK: ".PSX",
  IN: ".NS",
  CRYPTO: "-USD",
  CN: ".SS",
  TW: ".TW",
  JP: ".T",
  HK: ".HK",
  KR: ".KS",
  SG: ".SI",
  MY: ".KL",
  AU: ".AX",
  UK: ".L",
  DE: ".DE",
  FR: ".PA",
  NL: ".AS",
  CA: ".TO",
  BR: ".SA",
  MX: ".MX",
  SA: ".SR",
  AE: ".AE",
  ZA: ".JO",
  EG: ".CA",
  NG: ".NG",
  RU: ".ME",
  TR: ".IS",
  ID: ".JK",
  TH: ".BK",
  VN: ".VN",
};

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

/** Resolve a bare symbol to the full Yahoo ticker for a market. */
export function yahooSymbol(symbol: string, market: string): string {
  const suffix = MARKET_SUFFIX[market] ?? "";
  const sym = symbol.trim();
  if (!suffix) return sym;
  if (sym.endsWith(suffix)) return sym;
  return `${sym}${suffix}`;
}

function num(v: unknown): number | null {
  if (v == null || isNaN(Number(v))) return null;
  return Number(v);
}

/**
 * Fetch a live quote for a symbol in a market from Yahoo Finance.
 * Returns null on any failure (network, 404, no price).
 */
export async function fetchYahooQuote(
  symbol: string,
  market: string
): Promise<YahooQuote | null> {
  const fullSymbol = yahooSymbol(symbol, market);
  // Try query2 first (often more permissive than query1 under load), then query1.
  const hosts = ["https://query2.finance.yahoo.com/v8/finance/chart", CHART_ENDPOINT];
  const headers = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json,text/plain,*/*",
    "Referer": `https://finance.yahoo.com/quote/${encodeURIComponent(fullSymbol)}`,
  };

  let res: Response | null = null;
  for (const host of hosts) {
    const chartUrl = `${host}/${encodeURIComponent(fullSymbol)}?range=1d&interval=1d`;
    try {
      res = await fetch(chartUrl, { headers, signal: AbortSignal.timeout(8000) });
      if (res.ok) break;
    } catch {
      res = null;
    }
  }

  if (!res || !res.ok) {
    // Rate-limited / temporary block — wait once and try again.
    if (res && (res.status === 429 || res.status === 403)) {
      await new Promise((r) => setTimeout(r, 1200));
      const chartUrl = `${hosts[0]}/${encodeURIComponent(fullSymbol)}?range=1d&interval=1d`;
      try {
        res = await fetch(chartUrl, { headers, signal: AbortSignal.timeout(8000) });
      } catch {
        return null;
      }
      if (!res.ok) return null;
    } else {
      return null;
    }
  }

  let data: { chart?: { result?: Array<{ meta?: Record<string, unknown> }> } };
  try {
    data = await res.json();
  } catch {
    return null;
  }

  const result = data?.chart?.result?.[0];
  if (!result) return null;

  const meta = result.meta || {};
  const price = num(meta.regularMarketPrice ?? meta.previousClose);
  if (price == null || price <= 0) return null;

  const prevClose = num(meta.chartPreviousClose ?? meta.previousClose);
  const changePct = prevClose && prevClose > 0
    ? ((price - prevClose) / prevClose) * 100
    : 0;

  return {
    symbol: fullSymbol,
    price,
    changePct,
    previousClose: prevClose,
    marketCap: null,
    volume: num(meta.regularMarketVolume),
    peRatio: null,
    forwardPE: null,
    dividendYield: null,
    dayHigh: num(meta.regularMarketDayHigh),
    dayLow: num(meta.regularMarketDayLow),
    open: num(meta.regularMarketOpen),
    fiftyTwoWeekHigh: num(meta.fiftyTwoWeekHigh),
    fiftyTwoWeekLow: num(meta.fiftyTwoWeekLow),
  };
}
