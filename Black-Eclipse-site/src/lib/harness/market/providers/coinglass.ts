// CoinGlass adapter — futures liquidation and long/short account data.
//
// Verified against the CoinGlass V4 API docs (2026-10): GET only, keyed by the
// `CG-API-KEY` header, and a `{ code: "0", msg, data }` envelope where any code
// other than "0" is an error. No value is invented when the endpoint is
// unavailable or the symbol is absent from the answer.

import { safeGet } from "@/lib/connectors/security";
import { resolveProviderKey } from "@/lib/provider-keys";
import { rateLimitFromHeaders, type RateLimitInfo } from "../rate-limit";
import { ProviderError, type MarketDataRequest, type MarketProvider } from "../types";

const BASE = process.env.COINGLASS_BASE || "https://open-api-v4.coinglass.com";

interface CoinGlassEnvelope {
  code?: string;
  msg?: string;
  data?: unknown;
}

async function getJson(path: string): Promise<{ data: unknown; rateLimit?: RateLimitInfo }> {
  const key = await resolveProviderKey("COINGLASS_API_KEY").catch(() => null);
  if (!key || !key.trim()) {
    throw new ProviderError("coinglass requires COINGLASS_API_KEY", "AUTHENTICATION_FAILED", false, 401);
  }
  const res = await safeGet({
    url: `${BASE}${path}`,
    timeoutMs: 15000,
    maxBytes: 8 * 1024 * 1024,
    headers: { Accept: "application/json", "CG-API-KEY": key.trim() },
  });
  const rateLimit = rateLimitFromHeaders("coinglass", res.headers);
  if (res.status === 429) throw new ProviderError("coinglass rate limited", "RATE_LIMITED", true, 429);
  if (res.status === 401 || res.status === 403) {
    throw new ProviderError("coinglass credential rejected", "AUTHENTICATION_FAILED", false, res.status);
  }
  if (res.status >= 400) throw new ProviderError(`coinglass HTTP ${res.status}`, "PROVIDER_UNAVAILABLE", res.status >= 500, res.status);
  let json: CoinGlassEnvelope;
  try {
    json = JSON.parse(res.text) as CoinGlassEnvelope;
  } catch {
    throw new ProviderError("coinglass parse failure", "DATA_NOT_AVAILABLE", false);
  }
  if (String(json.code) !== "0") {
    const message = String(json.msg ?? "unknown error");
    if (/rate|limit/i.test(message)) throw new ProviderError("coinglass rate limited", "RATE_LIMITED", true, 429);
    if (/key|auth|token/i.test(message)) throw new ProviderError(`coinglass: ${message}`, "AUTHENTICATION_FAILED", false, 401);
    throw new ProviderError(`coinglass: ${message}`, "DATA_NOT_AVAILABLE", false);
  }
  return { data: json.data, rateLimit };
}

function baseOf(request: MarketDataRequest): string {
  const explicit = request.providerSymbols?.coinglass;
  if (explicit) return explicit.toUpperCase();
  return request.symbol.split(/[-/]/)[0].toUpperCase();
}

function pairOf(request: MarketDataRequest): string {
  const explicit = request.providerSymbols?.coinglass;
  if (explicit) return explicit.toUpperCase();
  const base = request.symbol.split(/[-/]/)[0].toUpperCase();
  return `${base}USDT`;
}

function num(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function isoFromMs(value: unknown): string | null {
  const ms = num(value);
  return ms !== null && ms > 0 ? new Date(ms).toISOString() : null;
}

async function fetchLiquidations(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const exchange = request.exchange || "Binance";
  const coin = baseOf(request);
  const { data, rateLimit } = await getJson(
    `/api/futures/liquidation/coin-list?exchange=${encodeURIComponent(exchange)}`,
  );
  if (!Array.isArray(data)) throw new ProviderError("coinglass liquidation shape unexpected", "DATA_NOT_AVAILABLE", false);
  const row = (data as Array<Record<string, unknown>>).find(
    (entry) => String(entry.symbol ?? "").toUpperCase() === coin,
  );
  if (!row) throw new ProviderError(`coinglass has no liquidation data for ${coin} on ${exchange}`, "SYMBOL_NOT_FOUND", false);
  const windows: Record<string, Record<string, number | null>> = {};
  for (const window of ["1h", "4h", "12h", "24h"]) {
    windows[window] = {
      totalUsd: num(row[`liquidation_usd_${window}`]),
      longUsd: num(row[`long_liquidation_usd_${window}`]),
      shortUsd: num(row[`short_liquidation_usd_${window}`]),
    };
  }
  return {
    status: "OK",
    provider: "coinglass",
    symbol: coin,
    exchange,
    window: "24h",
    totalUsd: windows["24h"].totalUsd,
    longUsd: windows["24h"].longUsd,
    shortUsd: windows["24h"].shortUsd,
    windows,
    rateLimit,
    observationTime: new Date().toISOString(),
    observationSource: "retrieval_clock",
  };
}

async function fetchLongShort(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const exchange = request.exchange || "Binance";
  const pair = pairOf(request);
  const interval = request.interval || "1h";
  const limit = Math.min(Math.max(request.limit ?? 48, 1), 1000);
  const { data, rateLimit } = await getJson(
    `/api/futures/global-long-short-account-ratio/history`
      + `?exchange=${encodeURIComponent(exchange)}&symbol=${encodeURIComponent(pair)}`
      + `&interval=${encodeURIComponent(interval)}&limit=${limit}`,
  );
  if (!Array.isArray(data) || data.length === 0) {
    throw new ProviderError(`coinglass has no long/short data for ${pair} on ${exchange}`, "SYMBOL_NOT_FOUND", false);
  }
  const series = (data as Array<Record<string, unknown>>).map((row) => ({
    timestamp: isoFromMs(row.time),
    longPercent: num(row.global_account_long_percent),
    shortPercent: num(row.global_account_short_percent),
    ratio: num(row.global_account_long_short_ratio),
  }));
  const latest = series[series.length - 1];
  return {
    status: "OK",
    provider: "coinglass",
    symbol: pair,
    exchange,
    interval,
    longPercent: latest.longPercent,
    shortPercent: latest.shortPercent,
    longShortRatio: latest.ratio,
    series,
    rateLimit,
    observationTime: latest.timestamp,
    observationSource: "provider_asof",
  };
}

export const coinglassProvider: MarketProvider = {
  id: "coinglass",
  capabilityIds: ["liquidations", "long_short"],
  async fetch(request) {
    switch (request.capability) {
      case "liquidations":
        return fetchLiquidations(request);
      case "long_short":
        return fetchLongShort(request);
      default:
        throw new ProviderError(`coinglass does not serve ${request.capability}`, "UNSUPPORTED_CAPABILITY", false);
    }
  },
};
