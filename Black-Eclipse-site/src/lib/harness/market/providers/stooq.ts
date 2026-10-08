// Stooq adapter — keyless daily bars, a history fallback for equities/FX/indices
// when the Yahoo bridge/binary is unavailable. One SSRF-hardened GET, CSV parse.

import { safeGet } from "@/lib/connectors/security";
import { rateLimitFromHeaders } from "../rate-limit";
import { ProviderError, type MarketDataRequest, type MarketProvider } from "../types";

function stooqSymbol(request: MarketDataRequest): string {
  const mapped = request.providerSymbols?.stooq;
  if (mapped) return mapped.toLowerCase();
  const market = (request.market || "US").toUpperCase();
  const base = request.symbol.toLowerCase();
  if (market === "US") return `${base}.us`;
  if (market === "UK") return `${base}.uk`;
  if (market === "DE") return `${base}.de`;
  if (market === "JP") return `${base}.jp`;
  return `${base}.us`;
}

async function fetchSeries(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const interval = request.interval || "1d";
  if (!["1d", "1w", "1mo"].includes(interval)) {
    throw new ProviderError("stooq supports daily/weekly/monthly only", "INVALID_INTERVAL", false);
  }
  const i = interval === "1w" ? "w" : interval === "1mo" ? "m" : "d";
  const symbol = stooqSymbol(request);
  const url = `https://stooq.com/q/d/l/?s=${encodeURIComponent(symbol)}&i=${i}`;
  const res = await safeGet({ url, timeoutMs: 12000, maxBytes: 6 * 1024 * 1024 });
  const rateLimit = rateLimitFromHeaders("stooq", res.headers);
  if (res.status >= 400) {
    throw new ProviderError(`stooq HTTP ${res.status}`, "PROVIDER_UNAVAILABLE", res.status >= 500, res.status);
  }
  const lines = res.text.trim().split(/\r?\n/);
  if (lines.length < 2 || !lines[0].toLowerCase().startsWith("date")) {
    throw new ProviderError(`no history for ${symbol}`, "DATA_NOT_AVAILABLE", false);
  }
  const bars = lines.slice(1).map((line) => {
    const [date, open, high, low, close, volume] = line.split(",");
    return {
      timestamp: date,
      open: Number(open), high: Number(high), low: Number(low),
      close: Number(close), volume: Number(volume), vwap: null,
    };
  }).filter((b) => Number.isFinite(b.close) && b.close > 0);
  if (bars.length === 0) throw new ProviderError(`empty series for ${symbol}`, "DATA_NOT_AVAILABLE", false);
  return {
    status: "OK", provider: "stooq", symbol: request.symbol, rateLimit, interval, adjusted: false,
    series: bars, asOf: bars[bars.length - 1].timestamp,
    observationTime: null, observationSource: "unknown",
  };
}

async function fetchQuote(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const series = await fetchSeries({ ...request, capability: "historical", interval: "1d" });
  const bars = series.series as Array<Record<string, unknown>>;
  const last = bars[bars.length - 1];
  const prev = bars[bars.length - 2];
  const price = Number(last.close);
  const prevClose = Number(prev?.close);
  return {
    status: "OK", provider: "stooq", symbol: request.symbol,
    price: { price, previousClose: prevClose || null, changePct: prevClose ? ((price - prevClose) / prevClose) * 100 : null },
    asOf: last.timestamp, observationTime: null, observationSource: "unknown",
  };
}

export const stooqProvider: MarketProvider = {
  id: "stooq",
  capabilityIds: ["historical", "ohlcv", "quote"],
  async fetch(request) {
    if (request.capability === "historical" || request.capability === "ohlcv") return fetchSeries(request);
    if (request.capability === "quote") return fetchQuote(request);
    throw new ProviderError(`stooq does not serve ${request.capability}`, "UNSUPPORTED_CAPABILITY", false);
  },
};
