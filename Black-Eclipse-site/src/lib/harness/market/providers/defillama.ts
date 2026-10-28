// DefiLlama adapter — DeFi protocol and chain TVL (keyless).
//
// `tvl` accepts either a protocol ticker (AAVE, UNI, LDO…) or a chain name
// (Ethereum, Solana, Arbitrum…). A protocol is resolved to a DefiLlama slug via
// a small known map, then by a one-time search over the protocol catalog. A
// value is only returned when DefiLlama actually reports it; otherwise the
// adapter throws so the gateway can report UNAVAILABLE honestly.

import { safeGet } from "@/lib/connectors/security";
import { rateLimitFromHeaders, type RateLimitInfo } from "../rate-limit";
import { ProviderError, type MarketDataRequest, type MarketProvider } from "../types";

const BASE = process.env.DEFILLAMA_BASE || "https://api.llama.fi";

// Common ticker → DefiLlama protocol slug.
const PROTOCOL_SLUGS: Record<string, string> = {
  AAVE: "aave", UNI: "uniswap", LDO: "lido", MKR: "maker", CRV: "curve-dex",
  GMX: "gmx", SNX: "synthetix", COMP: "compound", PENDLE: "pendle",
  EIGEN: "eigenlayer", ETHFI: "ether.fi", ONDO: "ondo-finance", JUP: "jupiter",
  RAY: "raydium", CAKE: "pancakeswap", SUSHI: "sushi", BAL: "balancer",
  YFI: "yearn-finance", GRT: "the-graph", INJ: "injective", DYDX: "dydx",
};

let protocolCache: Array<{ slug: string; symbol?: string; name?: string }> | null = null;

async function getJson(url: string): Promise<{ data: unknown; rateLimit?: RateLimitInfo }> {
  const res = await safeGet({
    url,
    timeoutMs: 15000,
    maxBytes: 8 * 1024 * 1024,
    headers: { Accept: "application/json" },
  });
  const rateLimit = rateLimitFromHeaders("defillama", res.headers);
  if (res.status === 429) throw new ProviderError("defillama rate limited", "RATE_LIMITED", true, 429);
  if (res.status >= 400) throw new ProviderError(`defillama HTTP ${res.status}`, "PROVIDER_UNAVAILABLE", res.status >= 500, res.status);
  try {
    return { data: JSON.parse(res.text), rateLimit };
  } catch {
    throw new ProviderError("defillama parse failure", "DATA_NOT_AVAILABLE", false);
  }
}

async function resolveSlug(symbol: string): Promise<string | null> {
  const upper = symbol.toUpperCase();
  if (PROTOCOL_SLUGS[upper]) return PROTOCOL_SLUGS[upper];
  if (!protocolCache) {
    const { data } = await getJson(`${BASE}/protocols`);
    if (!Array.isArray(data)) return null;
    protocolCache = data.map((p) => {
      const row = p as Record<string, unknown>;
      return {
        slug: String(row.slug ?? ""),
        symbol: typeof row.symbol === "string" ? row.symbol : undefined,
        name: typeof row.name === "string" ? row.name : undefined,
      };
    });
  }
  const bySymbol = protocolCache.find((p) => p.symbol?.toUpperCase() === upper);
  if (bySymbol) return bySymbol.slug;
  const byName = protocolCache.find((p) => p.name?.toUpperCase() === upper);
  return byName?.slug ?? null;
}

function isoFromUnix(value: unknown): string | null {
  const seconds = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(seconds) || seconds <= 0) return null;
  return new Date(seconds * 1000).toISOString();
}

async function fetchProtocolTvl(request: MarketDataRequest): Promise<Record<string, unknown> | null> {
  const slug = await resolveSlug(request.symbol);
  if (!slug) return null;
  const { data, rateLimit } = await getJson(`${BASE}/protocol/${encodeURIComponent(slug)}`);
  const row = data as Record<string, unknown>;
  const series = Array.isArray(row.tvl) ? (row.tvl as Array<Record<string, unknown>>) : [];
  if (series.length === 0) throw new ProviderError(`defillama has no tvl series for ${slug}`, "DATA_NOT_AVAILABLE", false);
  const latest = series[series.length - 1];
  const previous = series.length > 1 ? series[series.length - 2] : null;
  const tvlUsd = typeof latest.totalLiquidityUSD === "number" ? latest.totalLiquidityUSD : null;
  const prevUsd = previous && typeof previous.totalLiquidityUSD === "number" ? previous.totalLiquidityUSD : null;
  const chainTvls: Record<string, number> = {};
  const rawChainTvls = row.currentChainTvls;
  if (rawChainTvls && typeof rawChainTvls === "object") {
    for (const [chain, value] of Object.entries(rawChainTvls as Record<string, unknown>)) {
      if (typeof value === "number") chainTvls[chain] = value;
    }
  }
  return {
    status: "OK",
    provider: "defillama",
    symbol: request.symbol,
    protocol: slug,
    chain: request.chain ?? null,
    tvlUsd,
    change24hPct: tvlUsd !== null && prevUsd ? ((tvlUsd - prevUsd) / prevUsd) * 100 : null,
    chainTvls,
    rateLimit,
    observationTime: isoFromUnix(latest.date),
    observationSource: "provider_asof",
  };
}

async function fetchChainTvl(request: MarketDataRequest): Promise<Record<string, unknown> | null> {
  const { data, rateLimit } = await getJson(`${BASE}/v2/chains`);
  if (!Array.isArray(data)) return null;
  const wanted = request.symbol.toUpperCase();
  const hit = (data as Array<Record<string, unknown>>).find(
    (row) => String(row.name ?? "").toUpperCase() === wanted,
  );
  if (!hit) return null;
  return {
    status: "OK",
    provider: "defillama",
    symbol: request.symbol,
    chain: String(hit.name),
    tvlUsd: typeof hit.tvl === "number" ? hit.tvl : null,
    rateLimit,
    observationTime: null,
    observationSource: "provider_asof",
  };
}

async function fetchTvl(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const chainFirst = request.chain ? await fetchChainTvl({ ...request, symbol: request.chain }) : null;
  if (chainFirst) return chainFirst;
  const protocol = await fetchProtocolTvl(request);
  if (protocol) return protocol;
  const chain = await fetchChainTvl(request);
  if (chain) return chain;
  throw new ProviderError(`defillama has no protocol or chain tvl for ${request.symbol}`, "SYMBOL_NOT_FOUND", false);
}

export const defillamaProvider: MarketProvider = {
  id: "defillama",
  capabilityIds: ["tvl"],
  async fetch(request) {
    switch (request.capability) {
      case "tvl":
        return fetchTvl(request);
      default:
        throw new ProviderError(`defillama does not serve ${request.capability}`, "UNSUPPORTED_CAPABILITY", false);
    }
  },
};
