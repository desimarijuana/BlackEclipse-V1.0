// Binance public market-data adapter (crypto).
//
// Keyless public REST endpoints, reached through the SSRF-hardened `safeGet`.
// Covers spot quotes/klines/depth/trades and USDT-M futures funding + open
// interest. The provider symbol map supplies the exchange ticker (`BTCUSDT`).

import { safeGet } from "@/lib/connectors/security";
import { ProviderError, type MarketDataRequest, type MarketProvider } from "../types";

const SPOT = process.env.BINANCE_SPOT_BASE || "https://api.binance.com";
const FUTURES = process.env.BINANCE_FUTURES_BASE || "https://fapi.binance.com";

const INTERVAL_MAP: Record<string, string> = {
  "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
  "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w", "1mo": "1M",
};

function tickerFor(request: MarketDataRequest): string {
  return (request.providerSymbols?.binance || `${request.symbol.replace("-", "")}`).toUpperCase();
}

async function getJson(url: string): Promise<unknown> {
  const res = await safeGet({ url, timeoutMs: 12000, maxBytes: 6 * 1024 * 1024, headers: { Accept: "application/json" } });
  if (res.status === 429 || res.status === 418) {
    throw new ProviderError(`binance rate limited (HTTP ${res.status})`, "RATE_LIMITED", true, res.status);
  }
  if (res.status >= 400) {
    throw new ProviderError(`binance HTTP ${res.status}`, "PROVIDER_UNAVAILABLE", res.status >= 500, res.status);
  }
  try {
    return JSON.parse(res.text);
  } catch {
    throw new ProviderError("binance parse failure", "DATA_NOT_AVAILABLE", false);
  }
}

function num(v: unknown): number | null {
  const n = typeof v === "string" ? Number(v) : typeof v === "number" ? v : NaN;
  return Number.isFinite(n) ? n : null;
}

async function fetchQuote(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const symbol = tickerFor(request);
  const data = (await getJson(`${SPOT}/api/v3/ticker/24hr?symbol=${symbol}`)) as Record<string, unknown>;
  const price = num(data.lastPrice);
  if (price == null) throw new ProviderError(`no quote for ${symbol}`, "DATA_NOT_AVAILABLE", false);
  return {
    status: "OK",
    provider: "binance",
    symbol: request.symbol,
    price: {
      price,
      changePct: num(data.priceChangePercent),
      previousClose: num(data.prevClosePrice),
      open: num(data.openPrice),
      dayHigh: num(data.highPrice),
      dayLow: num(data.lowPrice),
      volume: num(data.volume),
    },
    marketStatus: "open",
    asOf: new Date().toISOString(),
    observationTime: new Date((data.closeTime as number) ?? Date.now()).toISOString(),
    observationSource: "provider_asof",
    cadenceSeconds: 60,
  };
}

async function fetchSeries(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const symbol = tickerFor(request);
  const interval = INTERVAL_MAP[request.interval || "1d"] || "1d";
  let url = `${SPOT}/api/v3/klines?symbol=${symbol}&interval=${interval}&limit=${Math.min(1000, request.limit || 500)}`;
  if (request.start) url += `&startTime=${Date.parse(request.start)}`;
  if (request.end) url += `&endTime=${Date.parse(request.end)}`;
  const data = await getJson(url);
  if (!Array.isArray(data) || data.length === 0) {
    throw new ProviderError(`no klines for ${symbol}`, "DATA_NOT_AVAILABLE", false);
  }
  const bars = (data as unknown[][]).map((k) => ({
    timestamp: new Date(k[0] as number).toISOString(),
    open: num(k[1]), high: num(k[2]), low: num(k[3]), close: num(k[4]),
    volume: num(k[5]), vwap: null,
  }));
  return {
    status: "OK",
    provider: "binance",
    symbol: request.symbol,
    interval: request.interval || "1d",
    adjusted: false,
    series: bars,
    asOf: bars[bars.length - 1]?.timestamp ?? null,
    observationTime: null,
    observationSource: "provider_asof",
  };
}

async function fetchOrderbook(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const symbol = tickerFor(request);
  const depth = Math.min(100, Math.max(5, request.depth || 20));
  const data = (await getJson(`${SPOT}/api/v3/depth?symbol=${symbol}&limit=${depth}`)) as Record<string, unknown>;
  const bids = ((data.bids as unknown[][]) ?? []).map((l) => [num(l[0]), num(l[1])]);
  const asks = ((data.asks as unknown[][]) ?? []).map((l) => [num(l[0]), num(l[1])]);
  if (bids.length === 0 && asks.length === 0) {
    throw new ProviderError(`empty book for ${symbol}`, "DATA_NOT_AVAILABLE", false);
  }
  return {
    status: "OK",
    provider: "binance",
    symbol: request.symbol,
    bids, asks,
    sequence: num(data.lastUpdateId),
    bookState: "snapshot",
    exchange: "BINANCE",
    observationTime: new Date().toISOString(),
    observationSource: "provider_asof",
  };
}

async function fetchTrades(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const symbol = tickerFor(request);
  const limit = Math.min(1000, Math.max(1, request.limit || 100));
  const data = await getJson(`${SPOT}/api/v3/trades?symbol=${symbol}&limit=${limit}`);
  if (!Array.isArray(data) || data.length === 0) {
    throw new ProviderError(`no trades for ${symbol}`, "DATA_NOT_AVAILABLE", false);
  }
  const trades = (data as Array<Record<string, unknown>>).map((t) => ({
    id: t.id ?? null,
    timestamp: new Date((t.time as number) ?? Date.now()).toISOString(),
    price: num(t.price),
    quantity: num(t.qty),
    // Binance reports buyer-maker; the taker (aggressor) side is the complement.
    side: t.isBuyerMaker ? "sell" : "buy",
    sideInferred: false,
  }));
  return {
    status: "OK",
    provider: "binance",
    symbol: request.symbol,
    trades,
    exchange: "BINANCE",
    observationTime: trades[0]?.timestamp ?? null,
    observationSource: "provider_asof",
  };
}

async function fetchFunding(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const symbol = tickerFor(request);
  const data = (await getJson(`${FUTURES}/fapi/v1/premiumIndex?symbol=${symbol}`)) as Record<string, unknown>;
  const rate = num(data.lastFundingRate);
  if (rate == null) throw new ProviderError(`no funding for ${symbol}`, "DATA_NOT_AVAILABLE", false);
  let historical: Array<Record<string, unknown>> = [];
  if (request.history && request.history > 0) {
    const rows = await getJson(`${FUTURES}/fapi/v1/fundingRate?symbol=${symbol}&limit=${Math.min(1000, request.history)}`);
    if (Array.isArray(rows)) {
      historical = rows.map((r: Record<string, unknown>) => ({
        timestamp: new Date((r.fundingTime as number) ?? 0).toISOString(),
        rate: num(r.fundingRate),
      }));
    }
  }
  return {
    status: "OK",
    provider: "binance",
    symbol: request.symbol,
    fundingRate: rate,
    fundingIntervalHours: 8,
    nextFundingTime: data.nextFundingTime ? new Date(data.nextFundingTime as number).toISOString() : null,
    predictedFunding: num(data.lastFundingRate),
    historical,
    exchange: "BINANCE",
    observationTime: new Date().toISOString(),
    observationSource: "provider_asof",
  };
}

async function fetchOpenInterest(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const symbol = tickerFor(request);
  const data = (await getJson(`${FUTURES}/fapi/v1/openInterest?symbol=${symbol}`)) as Record<string, unknown>;
  const oi = num(data.openInterest);
  if (oi == null) throw new ProviderError(`no open interest for ${symbol}`, "DATA_NOT_AVAILABLE", false);
  return {
    status: "OK",
    provider: "binance",
    symbol: request.symbol,
    openInterest: oi,
    openInterestUsd: null,
    oiChange: null,
    oiChangePct: null,
    window: request.window ?? "24h",
    exchange: "BINANCE",
    observationTime: new Date((data.time as number) ?? Date.now()).toISOString(),
    observationSource: "provider_asof",
  };
}

export const binanceProvider: MarketProvider = {
  id: "binance",
  capabilityIds: ["quote", "historical", "ohlcv", "orderbook", "trades", "funding", "open_interest"],
  async fetch(request) {
    switch (request.capability) {
      case "quote":
        return fetchQuote(request);
      case "historical":
      case "ohlcv":
        return fetchSeries(request);
      case "orderbook":
        return fetchOrderbook(request);
      case "trades":
        return fetchTrades(request);
      case "funding":
        return fetchFunding(request);
      case "open_interest":
        return fetchOpenInterest(request);
      default:
        throw new ProviderError(`binance does not serve ${request.capability}`, "UNSUPPORTED_CAPABILITY", false);
    }
  },
};
