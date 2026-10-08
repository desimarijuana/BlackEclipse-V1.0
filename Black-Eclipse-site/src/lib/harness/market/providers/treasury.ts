// US Treasury adapter — keyless Treasury yields via the FRED public CSV
// (`fredgraph.csv`, no key required). Normalized into the canonical BondData
// shape. A FRED API key is optional and only raises limits.

import { safeGet } from "@/lib/connectors/security";
import { resolveProviderKey } from "@/lib/provider-keys";
import { ProviderError, type MarketDataRequest, type MarketProvider } from "../types";

const SERIES: Record<string, string> = {
  US1M: "DGS1MO", US3M: "DGS3MO", US6M: "DGS6MO",
  US1Y: "DGS1", US2Y: "DGS2", US3Y: "DGS3", US5Y: "DGS5",
  US7Y: "DGS7", US10Y: "DGS10", US20Y: "DGS20", US30Y: "DGS30",
};

function seriesFor(request: MarketDataRequest): string {
  const symbol = request.symbol.toUpperCase().replace(/[^A-Z0-9]/g, "");
  if (SERIES[symbol]) return SERIES[symbol];
  // An explicit FRED series id (e.g. DGS10) is accepted directly.
  if (/^[A-Z]{2,6}\d*[A-Z]*$/.test(symbol) && symbol.length >= 4) return symbol;
  return "DGS10";
}

function tenorFor(request: MarketDataRequest): string | null {
  const symbol = request.symbol.toUpperCase().replace(/[^A-Z0-9]/g, "");
  return SERIES[symbol] ? symbol : null;
}

async function fetchBond(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const seriesId = seriesFor(request);
  // The api_key is optional for fredgraph.csv; pass it when configured.
  const key = await resolveProviderKey("FRED_API_KEY").catch(() => null);
  const keyParam = key && key.trim() ? `&api_key=${encodeURIComponent(key.trim())}` : "";
  const url = `https://fred.stlouisfed.org/graph/fredgraph.csv?id=${encodeURIComponent(seriesId)}${keyParam}`;
  const res = await safeGet({ url, timeoutMs: 15000, maxBytes: 8 * 1024 * 1024 });
  if (res.status >= 400) {
    throw new ProviderError(`treasury HTTP ${res.status}`, "PROVIDER_UNAVAILABLE", res.status >= 500, res.status);
  }
  const lines = res.text.trim().split(/\r?\n/);
  if (lines.length < 2) {
    return { status: "UNAVAILABLE", error: `no observations for ${seriesId}` };
  }
  let latestDate: string | null = null;
  let latestValue: number | null = null;
  for (let i = lines.length - 1; i >= 1; i--) {
    const [date, value] = lines[i].split(",");
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      latestDate = date;
      latestValue = parsed;
      break;
    }
  }
  if (latestValue == null) {
    throw new ProviderError(`no usable observations for ${seriesId}`, "DATA_NOT_AVAILABLE", false);
  }
  const tenor = tenorFor(request);
  return {
    status: "OK",
    provider: "treasury",
    symbol: request.symbol,
    yield: latestValue,
    price: null,
    maturity: null,
    tenor: tenor ?? seriesId,
    seriesType: "treasury",
    issuer: "US Treasury",
    currency: "USD",
    // The observation's own date (a daily close); never a live tick.
    observationTime: latestDate ? new Date(`${latestDate}T00:00:00Z`).toISOString() : null,
    observationSource: "provider_asof",
  };
}

export const treasuryProvider: MarketProvider = {
  id: "treasury",
  capabilityIds: ["bonds"],
  async fetch(request) {
    if (request.capability !== "bonds") {
      throw new ProviderError(`treasury does not serve ${request.capability}`, "UNSUPPORTED_CAPABILITY", false);
    }
    return fetchBond(request);
  },
};
