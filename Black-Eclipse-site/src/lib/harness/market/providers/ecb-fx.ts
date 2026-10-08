// ECB FX adapter — keyless daily reference rates (euro foreign exchange). Used
// as a fallback when Yahoo FX is unavailable and as a cross-conversion source.
// One SSRF-hardened GET to the ECB daily XML feed.

import { safeGet } from "@/lib/connectors/security";
import { ProviderError, type MarketDataRequest, type MarketProvider } from "../types";

const URL = process.env.ECB_FX_URL || "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml";

let cache: { at: number; rates: Record<string, number>; date: string | null } | null = null;

async function rates(): Promise<{ rates: Record<string, number>; date: string | null }> {
  if (cache && Date.now() - cache.at < 3600_000) return cache;
  const res = await safeGet({ url: URL, timeoutMs: 15000, maxBytes: 2 * 1024 * 1024 });
  if (res.status >= 400) throw new ProviderError(`ecb HTTP ${res.status}`, "PROVIDER_UNAVAILABLE", res.status >= 500, res.status);
  const map: Record<string, number> = { EUR: 1 };
  const dateMatch = res.text.match(/time=['"](\d{4}-\d{2}-\d{2})['"]/);
  const re = /currency=['"]([A-Z]{3})['"]\s+rate=['"]([\d.]+)['"]/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(res.text)) !== null) {
    map[m[1]] = Number(m[2]);
  }
  if (Object.keys(map).length < 2) throw new ProviderError("ecb parse failure", "DATA_NOT_AVAILABLE", false);
  cache = { at: Date.now(), rates: map, date: dateMatch?.[1] ?? null };
  return cache;
}

async function fetchFx(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const base = (request.providerSymbols?.fx?.slice(0, 3) || request.symbol.slice(0, 3)).toUpperCase();
  const quote = (request.providerSymbols?.fx?.slice(3, 6) || request.symbol.slice(3, 6)).toUpperCase();
  const { rates: r, date } = await rates();
  // ECB publishes EUR-based rates. Convert base→quote via EUR.
  const baseRate = r[base];
  const quoteRate = r[quote];
  if (!baseRate || !quoteRate) {
    throw new ProviderError(`ecb does not publish ${base} or ${quote}`, "DATA_NOT_AVAILABLE", false);
  }
  // 1 unit of base = (quoteRate/baseRate)? No: rates are per EUR. EUR/base and EUR/quote.
  // base→quote = (EUR→quote) / (EUR→base) = quoteRate / baseRate.
  const rate = quoteRate / baseRate;
  return {
    status: "OK",
    provider: "fx",
    symbol: `${base}${quote}`,
    base,
    quote,
    mid: rate,
    rate,
    cross: base !== "EUR" && quote !== "EUR",
    derivation: base !== "EUR" && quote !== "EUR" ? `cross via EUR: (EUR/${quote})/(EUR/${base})` : null,
    marketStatus: "closed",
    observationTime: date ? new Date(`${date}T00:00:00Z`).toISOString() : null,
    observationSource: "provider_asof",
  };
}

export const ecbFxProvider: MarketProvider = {
  id: "fx",
  capabilityIds: ["fx"],
  async fetch(request) {
    if (request.capability !== "fx") {
      throw new ProviderError(`fx provider does not serve ${request.capability}`, "UNSUPPORTED_CAPABILITY", false);
    }
    return fetchFx(request);
  },
};
