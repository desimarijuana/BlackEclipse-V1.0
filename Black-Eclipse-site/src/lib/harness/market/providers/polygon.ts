// Polygon.io adapter (keyed) — US equities quote, top-of-book (NBBO), trades,
// and aggregates. Reuses the SSRF-hardened `safeGet` and the encrypted vault
// (`resolveProviderKey`). Without a key it reports AUTHENTICATION_FAILED honestly.

import { safeGet } from "@/lib/connectors/security";
import { resolveProviderKey } from "@/lib/provider-keys";
import { rateLimitFromHeaders, type RateLimitInfo } from "../rate-limit";
import { ProviderError, type MarketDataRequest, type MarketProvider } from "../types";

const BASE = process.env.POLYGON_BASE || "https://api.polygon.io";

const INTERVAL: Record<string, { mult: number; span: string }> = {
  "1m": { mult: 1, span: "minute" }, "5m": { mult: 5, span: "minute" },
  "15m": { mult: 15, span: "minute" }, "30m": { mult: 30, span: "minute" },
  "1h": { mult: 1, span: "hour" }, "4h": { mult: 4, span: "hour" },
  "1d": { mult: 1, span: "day" }, "1w": { mult: 1, span: "week" }, "1mo": { mult: 1, span: "month" },
};

async function polygonGet(path: string): Promise<{ data: Record<string, unknown>; rateLimit?: RateLimitInfo }> {
  const key = await resolveProviderKey("POLYGON_API_KEY").catch(() => null);
  if (!key || !key.trim()) {
    throw new ProviderError("polygon requires POLYGON_API_KEY", "AUTHENTICATION_FAILED", false, 401);
  }
  const sep = path.includes("?") ? "&" : "?";
  const url = `${BASE}${path}${sep}apiKey=${encodeURIComponent(key.trim())}`;
  const res = await safeGet({ url, timeoutMs: 12000, maxBytes: 12 * 1024 * 1024, headers: { Accept: "application/json" } });
  const rateLimit = rateLimitFromHeaders("polygon", res.headers);
  if (res.status === 401 || res.status === 403) throw new ProviderError("polygon authentication failed", "AUTHENTICATION_FAILED", false, res.status);
  if (res.status === 429) throw new ProviderError("polygon rate limited", "RATE_LIMITED", true, 429);
  if (res.status >= 400) throw new ProviderError(`polygon HTTP ${res.status}`, "PROVIDER_UNAVAILABLE", res.status >= 500, res.status);
  try {
    const data = JSON.parse(res.text) as Record<string, unknown>;
    if (data.status === "ERROR") throw new ProviderError(String(data.error ?? "polygon error"), "PROVIDER_UNAVAILABLE", false);
    return { data, rateLimit };
  } catch (err) {
    if (err instanceof ProviderError) throw err;
    throw new ProviderError("polygon parse failure", "DATA_NOT_AVAILABLE", false);
  }
}

function num(v: unknown): number | null {
  const n = typeof v === "string" ? Number(v) : typeof v === "number" ? v : NaN;
  return Number.isFinite(n) ? n : null;
}

async function fetchQuote(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const { data, rateLimit } = await polygonGet(`/v2/snapshot/locale/us/markets/stocks/tickers/${encodeURIComponent(request.symbol)}`);
  const t = data.ticker as Record<string, unknown> | undefined;
  if (!t) throw new ProviderError(`no snapshot for ${request.symbol}`, "DATA_NOT_AVAILABLE", false);
  const day = (t.day as Record<string, unknown>) ?? {};
  const prev = (t.prevDay as Record<string, unknown>) ?? {};
  const lastQuote = (t.lastQuote as Record<string, unknown>) ?? {};
  const price = num(day.c) ?? num(lastQuote.p) ?? num((t.lastTrade as Record<string, unknown>)?.p);
  if (price == null) throw new ProviderError(`no price for ${request.symbol}`, "DATA_NOT_AVAILABLE", false);
  return {
    status: "OK", provider: "polygon", symbol: request.symbol, rateLimit,
    price: {
      price,
      changePct: num(t.todaysChangePerc),
      previousClose: num(prev.c),
      open: num(day.o), dayHigh: num(day.h), dayLow: num(day.l), volume: num(day.v),
      bid: num(lastQuote.p), ask: num(lastQuote.P),
    },
    observationTime: t.updated ? new Date(t.updated as number).toISOString() : null,
    observationSource: "provider_asof",
  };
}

async function fetchOrderbook(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const { data, rateLimit } = await polygonGet(`/v2/last/nbbo/${encodeURIComponent(request.symbol)}`);
  const r = data.results as Record<string, unknown> | undefined;
  if (!r) throw new ProviderError(`no NBBO for ${request.symbol}`, "DATA_NOT_AVAILABLE", false);
  const bid = num(r.p);
  const ask = num(r.P);
  const bids = bid != null ? [[bid, num(r.s) ?? 0]] : [];
  const asks = ask != null ? [[ask, num(r.S) ?? 0]] : [];
  if (bids.length === 0 && asks.length === 0) {
    throw new ProviderError(`empty NBBO for ${request.symbol}`, "DATA_NOT_AVAILABLE", false);
  }
  return {
    status: "OK", provider: "polygon", symbol: request.symbol, rateLimit,
    bids, asks, bestBid: bid, bestAsk: ask, exchange: "US NBBO",
    bookState: "snapshot",
    observationTime: r.t ? new Date((r.t as number) / 1_000_000).toISOString() : null,
    observationSource: "provider_asof",
  };
}

async function fetchTrades(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const limit = Math.min(1000, Math.max(1, request.limit || 100));
  const { data, rateLimit } = await polygonGet(`/v3/trades/${encodeURIComponent(request.symbol)}?limit=${limit}&order=desc&sort=timestamp`);
  const results = (data.results as Array<Record<string, unknown>>) ?? [];
  if (results.length === 0) throw new ProviderError(`no trades for ${request.symbol}`, "DATA_NOT_AVAILABLE", false);
  const trades = results.map((t) => ({
    id: t.id ?? null,
    timestamp: t.sip_timestamp ? new Date(Number(t.sip_timestamp) / 1_000_000).toISOString() : null,
    price: num(t.price), quantity: num(t.size),
    // Polygon's trade record does not state the aggressor; do NOT infer it here.
    side: null as null,
    sideInferred: false,
  }));
  return {
    status: "OK", provider: "polygon", symbol: request.symbol, rateLimit,
    trades, exchange: "US",
    observationTime: trades[0]?.timestamp ?? null, observationSource: "provider_asof",
  };
}

async function fetchSeries(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const spec = INTERVAL[request.interval || "1d"] ?? INTERVAL["1d"];
  const now = Date.now();
  const from = request.start ? Date.parse(request.start) : now - 365 * 86400_000;
  const to = request.end ? Date.parse(request.end) : now;
  const path = `/v2/aggs/ticker/${encodeURIComponent(request.symbol)}/range/${spec.mult}/${spec.span}/${from}/${to}?adjusted=true&sort=asc&limit=50000`;
  const { data, rateLimit } = await polygonGet(path);
  const results = (data.results as Array<Record<string, unknown>>) ?? [];
  if (results.length === 0) throw new ProviderError(`no aggregates for ${request.symbol}`, "DATA_NOT_AVAILABLE", false);
  const bars = results.map((r) => ({
    timestamp: new Date(r.t as number).toISOString().slice(0, 10),
    open: num(r.o), high: num(r.h), low: num(r.l), close: num(r.c), volume: num(r.v), vwap: num(r.vw),
  }));
  return {
    status: "OK", provider: "polygon", symbol: request.symbol, rateLimit,
    interval: request.interval || "1d", adjusted: true, series: bars,
    asOf: bars[bars.length - 1].timestamp, observationTime: null, observationSource: "provider_asof",
  };
}

export const polygonProvider: MarketProvider = {
  id: "polygon",
  capabilityIds: ["quote", "orderbook", "trades", "historical", "ohlcv"],
  async fetch(request) {
    switch (request.capability) {
      case "quote":
        return fetchQuote(request);
      case "orderbook":
        return fetchOrderbook(request);
      case "trades":
        return fetchTrades(request);
      case "historical":
      case "ohlcv":
        return fetchSeries(request);
      default:
        throw new ProviderError(`polygon does not serve ${request.capability}`, "UNSUPPORTED_CAPABILITY", false);
    }
  },
};
