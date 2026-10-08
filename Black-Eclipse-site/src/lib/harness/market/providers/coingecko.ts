// CoinGecko adapter — crypto supply, market cap and quote (keyless public tier;
// a key raises limits). Used for circulating/total/max supply and FDV, which
// Binance's ticker does not expose.

import { safeGet } from "@/lib/connectors/security";
import { resolveProviderKey } from "@/lib/provider-keys";
import { ProviderError, type MarketDataRequest, type MarketProvider } from "../types";

const BASE = process.env.COINGECKO_BASE || "https://api.coingecko.com/api/v3";

// Common symbol → CoinGecko id. A miss falls back to a one-time search call.
const SYMBOL_TO_ID: Record<string, string> = {
  BTC: "bitcoin", ETH: "ethereum", BNB: "binancecoin", SOL: "solana",
  XRP: "ripple", ADA: "cardano", DOGE: "dogecoin", AVAX: "avalanche-2",
  DOT: "polkadot", MATIC: "matic-network", LTC: "litecoin", LINK: "chainlink",
  TRX: "tron", SHIB: "shiba-inu", UNI: "uniswap", ATOM: "cosmos",
  XLM: "stellar", ETC: "ethereum-classic", BCH: "bitcoin-cash",
  FIL: "filecoin", APT: "aptos", ARB: "arbitrum", OP: "optimism",
  NEAR: "near", ICP: "internet-computer", SUI: "sui", INJ: "injective-protocol",
  PEPE: "pepe", TON: "the-open-network", USDT: "tether", USDC: "usd-coin",
};

const idCache = new Map<string, string>();

async function coinId(request: MarketDataRequest): Promise<string> {
  const base = (request.providerSymbols?.coingecko || request.symbol.split("-")[0]).toLowerCase();
  const upper = base.toUpperCase();
  if (SYMBOL_TO_ID[upper]) return SYMBOL_TO_ID[upper];
  if (idCache.has(upper)) return idCache.get(upper)!;
  const url = `${BASE}/search?query=${encodeURIComponent(base)}`;
  const res = await safeGet({ url, timeoutMs: 12000, maxBytes: 2 * 1024 * 1024, headers: { Accept: "application/json" } });
  if (res.status >= 400) throw new ProviderError(`coingecko HTTP ${res.status}`, "PROVIDER_UNAVAILABLE", res.status >= 500, res.status);
  let json: { coins?: Array<{ id: string; symbol: string }> };
  try {
    json = JSON.parse(res.text);
  } catch {
    throw new ProviderError("coingecko parse failure", "DATA_NOT_AVAILABLE", false);
  }
  const hit = json.coins?.find((c) => c.symbol.toUpperCase() === upper) ?? json.coins?.[0];
  if (!hit) throw new ProviderError(`no coingecko id for ${base}`, "SYMBOL_NOT_FOUND", false);
  idCache.set(upper, hit.id);
  return hit.id;
}

async function getJson(url: string): Promise<Record<string, unknown>> {
  const key = await resolveProviderKey("COINGECKO_API_KEY").catch(() => null);
  const headers: Record<string, string> = { Accept: "application/json" };
  if (key && key.trim()) headers["x-cg-demo-api-key"] = key.trim();
  const res = await safeGet({ url, timeoutMs: 12000, maxBytes: 4 * 1024 * 1024, headers });
  if (res.status === 429) throw new ProviderError("coingecko rate limited", "RATE_LIMITED", true, 429);
  if (res.status >= 400) throw new ProviderError(`coingecko HTTP ${res.status}`, "PROVIDER_UNAVAILABLE", res.status >= 500, res.status);
  try {
    return JSON.parse(res.text);
  } catch {
    throw new ProviderError("coingecko parse failure", "DATA_NOT_AVAILABLE", false);
  }
}

async function coin(request: MarketDataRequest): Promise<{ id: string; md: Record<string, unknown> }> {
  const id = await coinId(request);
  const json = await getJson(`${BASE}/coins/${id}?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false`);
  const md = json.market_data as Record<string, unknown>;
  if (!md) throw new ProviderError(`no market data for ${id}`, "DATA_NOT_AVAILABLE", false);
  return { id, md };
}

function usd(block: unknown): number | null {
  if (block && typeof block === "object" && "usd" in (block as Record<string, unknown>)) {
    const v = (block as Record<string, unknown>).usd;
    return typeof v === "number" ? v : null;
  }
  return null;
}

async function fetchSupply(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const { md } = await coin(request);
  const circulation = usd(md.market_cap);
  return {
    status: "OK", provider: "coingecko", symbol: request.symbol,
    circulatingSupply: (md.circulating_supply as number) ?? null,
    totalSupply: (md.total_supply as number) ?? null,
    maxSupply: (md.max_supply as number) ?? null,
    fdv: usd(md.fully_diluted_valuation),
    circulatingMarketCap: circulation,
    observationTime: (md.last_updated as string) ?? null,
    observationSource: "provider_asof",
  };
}

async function fetchMarketCap(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const { md } = await coin(request);
  return {
    status: "OK", provider: "coingecko", symbol: request.symbol,
    marketCap: usd(md.market_cap),
    price: usd(md.current_price),
    sharesOutstanding: (md.circulating_supply as number) ?? null,
    sharesBasis: "current",
    observationTime: (md.last_updated as string) ?? null,
    observationSource: "provider_asof",
  };
}

async function fetchQuote(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const { md } = await coin(request);
  return {
    status: "OK", provider: "coingecko", symbol: request.symbol,
    price: {
      price: usd(md.current_price),
      changePct: (md.price_change_percentage_24h as number) ?? null,
      marketCap: usd(md.market_cap),
      volume: usd(md.total_volume),
      dayHigh: usd(md.high_24h),
      dayLow: usd(md.low_24h),
    },
    observationTime: (md.last_updated as string) ?? null,
    observationSource: "provider_asof",
  };
}

export const coingeckoProvider: MarketProvider = {
  id: "coingecko",
  capabilityIds: ["supply", "market_cap", "quote"],
  async fetch(request) {
    switch (request.capability) {
      case "supply":
        return fetchSupply(request);
      case "market_cap":
        return fetchMarketCap(request);
      case "quote":
        return fetchQuote(request);
      default:
        throw new ProviderError(`coingecko does not serve ${request.capability}`, "UNSUPPORTED_CAPABILITY", false);
    }
  },
};
