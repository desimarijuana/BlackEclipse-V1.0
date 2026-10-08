// Yahoo Finance provider adapter (market data).
//
// Reuses the existing yfinance Python bridge (`fetchYahooBatchRaw` for full
// OHLCV series) and the direct Yahoo chart HTTP helper (`fetchYahooChartSeries`)
// — there is NO second Yahoo implementation. The bridge gives multi-market
// equities/FX; the chart helper is the keyless fallback.

import { fetchYahooBatchRaw } from "@/lib/scraper/fetchers/yfinance";
import { fetchYahooChartSeries } from "@/lib/scraper/yahoo-chart";
import { resolveProviderKey } from "@/lib/provider-keys";
import { safeGet } from "@/lib/connectors/security";
import { ProviderError, type MarketDataRequest, type MarketProvider } from "../types";

type QuoteRow = { price: number; changePct?: number | null; volume?: number | null; marketCap?: number | null; prevClose?: number | null };

const RANGE_MAP: Record<string, string> = {
  "1m": "1d", "5m": "5d", "15m": "1mo", "30m": "1mo", "1h": "3mo",
  "4h": "6mo", "1d": "1y", "1w": "5y", "1mo": "max",
};

function rangeFor(interval: string, start?: string): string {
  if (start) return "max";
  return RANGE_MAP[interval] ?? "1y";
}

async function yahooSymbol(request: MarketDataRequest): Promise<string> {
  const mapped = request.providerSymbols?.yahoo;
  return (mapped || request.symbol).toUpperCase();
}

async function fetchQuote(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const ticker = await yahooSymbol(request);
  const data = await fetchYahooBatchRaw([ticker], request.market || "US");
  const key = Object.keys(data.quotes ?? {})[0];
  const row: QuoteRow | undefined = key ? data.quotes?.[key] : undefined;
  if (!row || !row.price) {
    throw new ProviderError(`no quote for ${ticker}`, "DATA_NOT_AVAILABLE", false);
  }
  return {
    status: "OK",
    provider: "yahoo",
    symbol: request.symbol,
    price: {
      price: row.price,
      changePct: row.changePct ?? null,
      previousClose: row.prevClose ?? null,
      volume: row.volume ?? null,
      marketCap: row.marketCap ?? null,
    },
    asOf: new Date().toISOString(),
    // the scraper does not report a market time; never fabricate one
    observationTime: null,
    observationSource: "unknown",
  };
}

async function fetchSeries(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const ticker = await yahooSymbol(request);
  const interval = request.interval || "1d";
  const range = rangeFor(interval, request.start);
  let rows: Array<Record<string, unknown>> | undefined;
  try {
    const data = await fetchYahooBatchRaw([ticker], request.market || "US", interval, range);
    const key = Object.keys(data.history ?? {})[0];
    rows = key ? (data.history?.[key] as Array<Record<string, unknown>>) : undefined;
  } catch {
    rows = undefined;
  }
  if (!rows || rows.length < 2) {
    const chart = await fetchYahooChartSeries(ticker, range, interval);
    if (!chart) throw new ProviderError(`no history for ${ticker}`, "DATA_NOT_AVAILABLE", false);
    rows = chart.bars.map((b) => ({
      date: b.date, open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume,
    }));
  }
  const bars = (rows || [])
    .filter((r) => r.close != null)
    .map((r) => ({
      timestamp: String(r.date ?? r.timestamp ?? ""),
      open: r.open ?? null,
      high: r.high ?? null,
      low: r.low ?? null,
      close: r.close ?? null,
      volume: r.volume ?? null,
      vwap: null,
    }));
  if (bars.length === 0) throw new ProviderError(`empty series for ${ticker}`, "DATA_NOT_AVAILABLE", false);
  return {
    status: "OK",
    provider: "yahoo",
    symbol: request.symbol,
    interval,
    adjusted: request.interval === "1d",
    series: bars,
    asOf: bars[bars.length - 1].timestamp,
    observationTime: null,
    observationSource: "unknown",
  };
}

async function fetchMarketCap(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const q = await fetchQuote(request);
  const block = q.price as { price?: number; marketCap?: number } | undefined;
  if (!block?.marketCap) throw new ProviderError("no market cap", "DATA_NOT_AVAILABLE", false);
  return {
    status: "OK",
    provider: "yahoo",
    symbol: request.symbol,
    marketCap: block.marketCap,
    price: block.price ?? null,
    sharesOutstanding: null,
    sharesBasis: "unknown",
    observationTime: null,
    observationSource: "unknown",
  };
}

async function fetchVolume(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const ticker = await yahooSymbol(request);
  const data = await fetchYahooBatchRaw([ticker], request.market || "US");
  const key = Object.keys(data.quotes ?? {})[0];
  const row: QuoteRow | undefined = key ? data.quotes?.[key] : undefined;
  if (!row || row.volume == null) throw new ProviderError("no volume", "DATA_NOT_AVAILABLE", false);
  return {
    status: "OK",
    provider: "yahoo",
    symbol: request.symbol,
    totalVolume: row.volume,
    averageVolume: null,
    relativeVolume: null,
    volumeChange: null,
    window: request.window ?? "1d",
    observationTime: null,
    observationSource: "unknown",
  };
}

async function fetchOptions(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const ticker = await yahooSymbol(request);
  const base = process.env.YAHOO_OPTIONS_BASE || "https://query2.finance.yahoo.com/v7/finance/options";
  const url = `${base}/${encodeURIComponent(ticker)}`;
  const res = await safeGet({ url, timeoutMs: 12000, maxBytes: 4 * 1024 * 1024, headers: { Accept: "application/json" } });
  if (res.status >= 400) throw new ProviderError(`yahoo options HTTP ${res.status}`, "PROVIDER_UNAVAILABLE", res.status >= 500, res.status);
  let json: { optionChain?: { result?: Array<Record<string, unknown>> } };
  try {
    json = JSON.parse(res.text);
  } catch {
    throw new ProviderError("yahoo options parse failure", "DATA_NOT_AVAILABLE", false);
  }
  const result = json.optionChain?.result?.[0];
  if (!result) throw new ProviderError("no options chain", "DATA_NOT_AVAILABLE", false);
  const quote = (result.quote as Record<string, unknown>) ?? {};
  const options = (result.options as Array<Record<string, unknown>>) ?? [];
  const contracts: Array<Record<string, unknown>> = [];
  const expirations: string[] = ((result.expirationDates as number[]) ?? []).map((s) =>
    new Date(s * 1000).toISOString().slice(0, 10),
  );
  const targetExp = request.expiration;
  for (const opt of options) {
    const exp = new Date(((opt.expirationDate as number) ?? 0) * 1000).toISOString().slice(0, 10);
    if (targetExp && exp !== targetExp) continue;
    for (const [kind, list] of [["call", opt.calls], ["put", opt.puts]] as const) {
      for (const c of (list as Array<Record<string, unknown>>) ?? []) {
        contracts.push({
          expiration: exp,
          strike: c.strike ?? null,
          type: kind,
          bid: c.bid ?? null,
          ask: c.ask ?? null,
          last: c.lastPrice ?? null,
          volume: c.volume ?? null,
          openInterest: c.openInterest ?? null,
          impliedVolatility: c.impliedVolatility ?? null,
          greeksSource: null,
          ivSource: "provider",
        });
      }
    }
  }
  if (contracts.length === 0) throw new ProviderError("empty options chain", "DATA_NOT_AVAILABLE", false);
  return {
    status: "OK",
    provider: "yahoo",
    symbol: request.symbol,
    underlying: request.symbol,
    underlyingPrice: quote.regularMarketPrice ?? null,
    expirations,
    contracts,
    observationTime: null,
    observationSource: "unknown",
  };
}

// Yahoo FX: the canonical ticker already encodes the pair (`EURUSD=X`).
async function fetchFx(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const block = await fetchQuote(request);
  const price = (block.price as { price?: number })?.price ?? null;
  return {
    status: "OK",
    provider: "yahoo",
    symbol: request.symbol,
    base: request.providerSymbols?.fx?.slice(0, 3) ?? request.symbol.slice(0, 3),
    quote: request.providerSymbols?.fx?.slice(3, 6) ?? request.symbol.slice(3, 6),
    mid: price,
    rate: price,
    cross: false,
    observationTime: null,
    observationSource: "unknown",
  };
}

export const yahooProvider: MarketProvider = {
  id: "yahoo",
  capabilityIds: ["quote", "historical", "ohlcv", "volume", "market_cap", "options", "fx"],
  async fetch(request) {
    switch (request.capability) {
      case "quote":
        return fetchQuote(request);
      case "historical":
        return fetchSeries(request);
      case "ohlcv":
        return fetchSeries(request);
      case "volume":
        return fetchVolume(request);
      case "market_cap":
        return fetchMarketCap(request);
      case "options":
        return fetchOptions(request);
      case "fx":
        return fetchFx(request);
      default:
        throw new ProviderError(`yahoo does not serve ${request.capability}`, "UNSUPPORTED_CAPABILITY", false);
    }
  },
};

/** Whether a Yahoo credential (optional) is configured — informational only. */
export async function yahooConfigured(): Promise<boolean> {
  const key = await resolveProviderKey("FINANCIALMODELINGPREP_API_KEY").catch(() => null);
  void key;
  return true; // Yahoo is keyless
}
