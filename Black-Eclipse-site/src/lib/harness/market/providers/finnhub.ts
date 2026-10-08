// Finnhub adapter (keyed) — equities quote + candles. Real-time trades arrive
// over Finnhub's WebSocket (see the streaming manager), not here. Reuses the
// SSRF-hardened `safeGet` and the encrypted vault. Without a key it reports
// AUTHENTICATION_FAILED honestly.

import { safeGet } from "@/lib/connectors/security";
import { resolveProviderKey } from "@/lib/provider-keys";
import { rateLimitFromHeaders, type RateLimitInfo } from "../rate-limit";
import { ProviderError, type MarketDataRequest, type MarketProvider } from "../types";

const BASE = process.env.FINNHUB_BASE || "https://finnhub.io/api/v1";

const RESOLUTION: Record<string, string> = {
  "1m": "1", "5m": "5", "15m": "15", "30m": "30", "1h": "60",
  "4h": "60", "1d": "D", "1w": "W", "1mo": "M",
};

async function finnhubGet(path: string): Promise<{ data: Record<string, unknown>; rateLimit?: RateLimitInfo }> {
  const key = await resolveProviderKey("FINNHUB_API_KEY").catch(() => null);
  if (!key || !key.trim()) {
    throw new ProviderError("finnhub requires FINNHUB_API_KEY", "AUTHENTICATION_FAILED", false, 401);
  }
  const sep = path.includes("?") ? "&" : "?";
  const url = `${BASE}${path}${sep}token=${encodeURIComponent(key.trim())}`;
  const res = await safeGet({ url, timeoutMs: 12000, maxBytes: 8 * 1024 * 1024, headers: { Accept: "application/json" } });
  const rateLimit = rateLimitFromHeaders("finnhub", res.headers);
  if (res.status === 401 || res.status === 403) throw new ProviderError("finnhub authentication failed or plan-restricted", "AUTHENTICATION_FAILED", false, res.status);
  if (res.status === 429) throw new ProviderError("finnhub rate limited", "RATE_LIMITED", true, 429);
  if (res.status >= 400) throw new ProviderError(`finnhub HTTP ${res.status}`, "PROVIDER_UNAVAILABLE", res.status >= 500, res.status);
  try {
    return { data: JSON.parse(res.text) as Record<string, unknown>, rateLimit };
  } catch {
    throw new ProviderError("finnhub parse failure", "DATA_NOT_AVAILABLE", false);
  }
}

function num(v: unknown): number | null {
  const n = typeof v === "number" ? v : NaN;
  return Number.isFinite(n) ? n : null;
}

async function fetchQuote(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const { data, rateLimit } = await finnhubGet(`/quote?symbol=${encodeURIComponent(request.symbol)}`);
  const price = num(data.c);
  if (price == null || price === 0) {
    throw new ProviderError(`no quote for ${request.symbol}`, "DATA_NOT_AVAILABLE", false);
  }
  return {
    status: "OK", provider: "finnhub", symbol: request.symbol, rateLimit,
    price: {
      price,
      changePct: num(data.dp),
      change: num(data.d),
      previousClose: num(data.pc),
      open: num(data.o), dayHigh: num(data.h), dayLow: num(data.l),
    },
    observationTime: data.t ? new Date((data.t as number) * 1000).toISOString() : null,
    observationSource: "provider_asof",
  };
}

async function fetchSeries(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const resolution = RESOLUTION[request.interval || "1d"] ?? "D";
  const now = Math.floor(Date.now() / 1000);
  const from = request.start ? Math.floor(Date.parse(request.start) / 1000) : now - 365 * 86400;
  const to = request.end ? Math.floor(Date.parse(request.end) / 1000) : now;
  const { data, rateLimit } = await finnhubGet(`/stock/candle?symbol=${encodeURIComponent(request.symbol)}&resolution=${resolution}&from=${from}&to=${to}`);
  if (data.s !== "ok") {
    throw new ProviderError(`no candles for ${request.symbol}`, "DATA_NOT_AVAILABLE", false);
  }
  const t = (data.t as number[]) ?? [];
  const bars = t.map((ts, i) => ({
    timestamp: new Date(ts * 1000).toISOString().slice(0, 10),
    open: num((data.o as number[])[i]), high: num((data.h as number[])[i]),
    low: num((data.l as number[])[i]), close: num((data.c as number[])[i]),
    volume: num((data.v as number[])?.[i]), vwap: null,
  }));
  if (bars.length === 0) throw new ProviderError(`empty candles for ${request.symbol}`, "DATA_NOT_AVAILABLE", false);
  return {
    status: "OK", provider: "finnhub", symbol: request.symbol, rateLimit,
    interval: request.interval || "1d", adjusted: false, series: bars,
    asOf: bars[bars.length - 1].timestamp, observationTime: null, observationSource: "provider_asof",
  };
}

export const finnhubProvider: MarketProvider = {
  id: "finnhub",
  capabilityIds: ["quote", "historical", "ohlcv"],
  async fetch(request) {
    switch (request.capability) {
      case "quote":
        return fetchQuote(request);
      case "historical":
      case "ohlcv":
        return fetchSeries(request);
      default:
        throw new ProviderError(`finnhub does not serve ${request.capability}`, "UNSUPPORTED_CAPABILITY", false);
    }
  },
};
