// Hyperliquid adapter — read-only perps funding and open interest.
//
// The public `info` endpoint is POST-only, so this adapter calls the hardened
// `safePost` transport (same SSRF/DNS-pinning/size-cap posture as `safeGet`).
// It deliberately does NOT serve quote/order book: those would be a PERP book
// offered as a crypto-spot fallback, and the instrument master does not carry a
// spot/perp distinction. Funding and open interest are unambiguous perp metrics.
// Nothing here signs, deposits or trades: it is a read of public market state.

import { safePost } from "@/lib/connectors/security";
import { rateLimitFromHeaders, type RateLimitInfo } from "../rate-limit";
import { ProviderError, type MarketDataRequest, type MarketProvider } from "../types";

const BASE = process.env.HYPERLIQUID_INFO_URL || "https://api.hyperliquid.xyz/info";

// Hyperliquid funds hourly.
const FUNDING_INTERVAL_HOURS = 1;

interface HyperliquidContext {
  funding?: string;
  openInterest?: string;
  markPx?: string;
  midPx?: string;
}

interface HyperliquidMeta {
  universe?: Array<{ name?: string }>;
}

async function postInfo(payload: Record<string, unknown>): Promise<{ data: unknown; rateLimit?: RateLimitInfo }> {
  const res = await safePost({
    url: BASE,
    body: JSON.stringify(payload),
    timeoutMs: 12000,
    maxBytes: 8 * 1024 * 1024,
  });
  const rateLimit = rateLimitFromHeaders("hyperliquid", res.headers);
  if (res.status === 429) throw new ProviderError("hyperliquid rate limited", "RATE_LIMITED", true, 429);
  if (res.status >= 400) throw new ProviderError(`hyperliquid HTTP ${res.status}`, "PROVIDER_UNAVAILABLE", res.status >= 500, res.status);
  try {
    return { data: JSON.parse(res.text), rateLimit };
  } catch {
    throw new ProviderError("hyperliquid parse failure", "DATA_NOT_AVAILABLE", false);
  }
}

function coinOf(request: MarketDataRequest): string {
  const explicit = request.providerSymbols?.hyperliquid;
  if (explicit) return explicit.toUpperCase();
  return request.symbol.split(/[-/]/)[0].toUpperCase();
}

function num(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

async function contextFor(coin: string): Promise<{ ctx: HyperliquidContext; rateLimit?: RateLimitInfo }> {
  const { data, rateLimit } = await postInfo({ type: "metaAndAssetCtxs" });
  if (!Array.isArray(data) || data.length < 2) {
    throw new ProviderError("hyperliquid metaAndAssetCtxs shape unexpected", "DATA_NOT_AVAILABLE", false);
  }
  const meta = data[0] as HyperliquidMeta;
  const ctxs = data[1] as HyperliquidContext[];
  const names = (meta.universe ?? []).map((u) => u.name?.toUpperCase());
  const index = names.indexOf(coin);
  if (index < 0 || !ctxs[index]) {
    throw new ProviderError(`hyperliquid has no perp market for ${coin}`, "SYMBOL_NOT_FOUND", false);
  }
  return { ctx: ctxs[index], rateLimit };
}

async function fetchFunding(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const coin = coinOf(request);
  const { ctx, rateLimit } = await contextFor(coin);
  const rate = num(ctx.funding);
  if (rate === null) throw new ProviderError(`hyperliquid has no funding for ${coin}`, "DATA_NOT_AVAILABLE", false);
  let historical: Array<Record<string, unknown>> = [];
  if ((request.history ?? 0) > 0) {
    const startTime = Date.now() - Math.min(request.history ?? 0, 500) * 3600_000;
    const { data } = await postInfo({ type: "fundingHistory", coin, startTime });
    if (Array.isArray(data)) {
      historical = data.slice(-(request.history ?? 0)).map((row) => {
        const r = row as Record<string, unknown>;
        return {
          fundingRate: num(r.fundingRate),
          timestamp: typeof r.time === "number" ? new Date(r.time).toISOString() : null,
        };
      });
    }
  }
  return {
    status: "OK",
    provider: "hyperliquid",
    symbol: request.symbol,
    fundingRate: rate,
    fundingIntervalHours: FUNDING_INTERVAL_HOURS,
    nextFundingTime: null,
    historical,
    rateLimit,
    observationTime: new Date().toISOString(),
    observationSource: "retrieval_clock",
  };
}

async function fetchOpenInterest(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const coin = coinOf(request);
  const { ctx, rateLimit } = await contextFor(coin);
  const oi = num(ctx.openInterest);
  if (oi === null) throw new ProviderError(`hyperliquid has no open interest for ${coin}`, "DATA_NOT_AVAILABLE", false);
  const mark = num(ctx.markPx) ?? num(ctx.midPx);
  return {
    status: "OK",
    provider: "hyperliquid",
    symbol: request.symbol,
    openInterest: oi,
    openInterestUsd: mark !== null ? oi * mark : null,
    rateLimit,
    observationTime: new Date().toISOString(),
    observationSource: "retrieval_clock",
  };
}

export const hyperliquidProvider: MarketProvider = {
  id: "hyperliquid",
  capabilityIds: ["funding", "open_interest"],
  async fetch(request) {
    switch (request.capability) {
      case "funding":
        return fetchFunding(request);
      case "open_interest":
        return fetchOpenInterest(request);
      default:
        throw new ProviderError(`hyperliquid does not serve ${request.capability}`, "UNSUPPORTED_CAPABILITY", false);
    }
  },
};
