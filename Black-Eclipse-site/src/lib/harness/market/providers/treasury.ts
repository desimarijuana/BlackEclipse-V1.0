// US Treasury + corporate-bond index adapter — keyless via the FRED public CSV
// (`fredgraph.csv`, no key required). Normalized into the canonical BondData
// shape. A FRED API key is optional and only raises limits.
//
// Treasury yields are per-tenor; corporate entries are ICE BofA index yields /
// option-adjusted spreads (real, keyless). A per-ISSUE corporate bond requires a
// premium vendor and is reported honestly as unavailable by the gateway.

import { safeGet } from "@/lib/connectors/security";
import { resolveProviderKey } from "@/lib/provider-keys";
import { rateLimitFromHeaders } from "../rate-limit";
import { ProviderError, type MarketDataRequest, type MarketProvider } from "../types";

interface SeriesSpec {
  series: string;
  seriesType: "treasury" | "corporate";
  issuer: string;
  rating?: string;
  // "yield" (default) or "spread" — determines which BondData field is set.
  measure?: "yield" | "spread";
}

const SERIES: Record<string, SeriesSpec> = {
  US1M: { series: "DGS1MO", seriesType: "treasury", issuer: "US Treasury" },
  US3M: { series: "DGS3MO", seriesType: "treasury", issuer: "US Treasury" },
  US6M: { series: "DGS6MO", seriesType: "treasury", issuer: "US Treasury" },
  US1Y: { series: "DGS1", seriesType: "treasury", issuer: "US Treasury" },
  US2Y: { series: "DGS2", seriesType: "treasury", issuer: "US Treasury" },
  US3Y: { series: "DGS3", seriesType: "treasury", issuer: "US Treasury" },
  US5Y: { series: "DGS5", seriesType: "treasury", issuer: "US Treasury" },
  US7Y: { series: "DGS7", seriesType: "treasury", issuer: "US Treasury" },
  US10Y: { series: "DGS10", seriesType: "treasury", issuer: "US Treasury" },
  US20Y: { series: "DGS20", seriesType: "treasury", issuer: "US Treasury" },
  US30Y: { series: "DGS30", seriesType: "treasury", issuer: "US Treasury" },
  // ICE BofA corporate indices (effective yield + option-adjusted spread).
  US_CORP_IG: { series: "BAMLC0A0CMEY", seriesType: "corporate", issuer: "ICE BofA US Corporate", rating: "Investment Grade" },
  US_CORP_HY: { series: "BAMLH0A0HYM2EY", seriesType: "corporate", issuer: "ICE BofA US High Yield", rating: "High Yield" },
  US_CORP_AAA: { series: "BAMLC0A1CAAAEY", seriesType: "corporate", issuer: "ICE BofA US Corporate", rating: "AAA" },
  US_CORP_BBB: { series: "BAMLC0A4CBBBEY", seriesType: "corporate", issuer: "ICE BofA US Corporate", rating: "BBB" },
  US_CORP_IG_OAS: { series: "BAMLC0A0CM", seriesType: "corporate", issuer: "ICE BofA US Corporate", rating: "Investment Grade", measure: "spread" },
  US_CORP_HY_OAS: { series: "BAMLH0A0HYM2", seriesType: "corporate", issuer: "ICE BofA US High Yield", rating: "High Yield", measure: "spread" },
};

function specFor(request: MarketDataRequest): SeriesSpec {
  const symbol = request.symbol.toUpperCase().replace(/[^A-Z0-9_]/g, "");
  if (SERIES[symbol]) return SERIES[symbol];
  // An explicit FRED series id (e.g. DGS10) is accepted directly.
  if (/^[A-Z]{2,6}[A-Z0-9]*$/.test(symbol) && symbol.length >= 4) {
    return { series: symbol, seriesType: "treasury", issuer: "FRED" };
  }
  return SERIES.US10Y;
}

async function fetchBond(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const spec = specFor(request);
  // The api_key is optional for fredgraph.csv; pass it when configured.
  const key = await resolveProviderKey("FRED_API_KEY").catch(() => null);
  const keyParam = key && key.trim() ? `&api_key=${encodeURIComponent(key.trim())}` : "";
  const url = `https://fred.stlouisfed.org/graph/fredgraph.csv?id=${encodeURIComponent(spec.series)}${keyParam}`;
  const res = await safeGet({ url, timeoutMs: 15000, maxBytes: 8 * 1024 * 1024 });
  const rateLimit = rateLimitFromHeaders("treasury", res.headers);
  if (res.status >= 400) {
    throw new ProviderError(`treasury HTTP ${res.status}`, "PROVIDER_UNAVAILABLE", res.status >= 500, res.status);
  }
  const lines = res.text.trim().split(/\r?\n/);
  if (lines.length < 2) {
    return { status: "UNAVAILABLE", error: `no observations for ${spec.series}` };
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
    throw new ProviderError(`no usable observations for ${spec.series}`, "DATA_NOT_AVAILABLE", false);
  }
  const isSpread = spec.measure === "spread";
  return {
    status: "OK",
    provider: "treasury",
    symbol: request.symbol,
    rateLimit,
    // A spread is not a yield; keep them distinct so a spread is never read as a
    // rate.
    yield: isSpread ? null : latestValue,
    spread: isSpread ? latestValue : null,
    price: null,
    maturity: null,
    tenor: SERIES[request.symbol.toUpperCase().replace(/[^A-Z0-9_]/g, "")] ? request.symbol.toUpperCase() : spec.series,
    seriesType: spec.seriesType,
    issuer: spec.issuer,
    rating: spec.rating ?? null,
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
