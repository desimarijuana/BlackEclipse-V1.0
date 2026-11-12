// Market-data adapter registry + dispatcher (TS side).
//
// The Python gateway sends ONE `market_data` bridge call with a target
// `provider`; this dispatcher runs that provider's adapter and returns the
// normalized payload. If no provider is named it tries the capability's
// providers in order. Routing/fallback/health live in Python (the ProviderRouter
// + MarketStore); this file is pure adapter execution over ONE transport.

import type { DataBridgeResult } from "@/lib/harness/data-bridge/data-bridge-types";
import { ProviderError, type MarketDataRequest, type MarketProvider } from "./types";
import { yahooProvider } from "./providers/yahoo";
import { binanceProvider } from "./providers/binance";
import { coingeckoProvider } from "./providers/coingecko";
import { stooqProvider } from "./providers/stooq";
import { treasuryProvider } from "./providers/treasury";
import { ecbFxProvider } from "./providers/ecb-fx";
import { polygonProvider } from "./providers/polygon";
import { finnhubProvider } from "./providers/finnhub";
import { defillamaProvider } from "./providers/defillama";
import { etherscanProvider } from "./providers/etherscan";
import { hyperliquidProvider } from "./providers/hyperliquid";
import { coinglassProvider } from "./providers/coinglass";
import { solscanProvider } from "./providers/solscan";

const PROVIDERS: MarketProvider[] = [
  yahooProvider,
  binanceProvider,
  polygonProvider,
  finnhubProvider,
  coingeckoProvider,
  defillamaProvider,
  etherscanProvider,
  solscanProvider,
  coinglassProvider,
  hyperliquidProvider,
  stooqProvider,
  treasuryProvider,
  ecbFxProvider,
];

export function listMarketProviders(): Array<{ id: string; capabilities: string[] }> {
  return PROVIDERS.map((p) => ({ id: p.id, capabilities: p.capabilityIds }));
}

export function getMarketProvider(id: string): MarketProvider | undefined {
  return PROVIDERS.find((p) => p.id === id);
}

function toRequest(params: Record<string, unknown>): MarketDataRequest {
  const providerSymbols =
    params.providerSymbols && typeof params.providerSymbols === "object"
      ? (params.providerSymbols as Record<string, string>)
      : undefined;
  const capability = String(params.capability ?? "quote");
  const rawSymbol = String(params.symbol ?? "");
  return {
    capability,
    // Account addresses are case-sensitive to some explorers (`0X…` is not the
    // same as `0x…`), so an on-chain request keeps the caller's casing.
    symbol: capability === "onchain" ? rawSymbol : rawSymbol.toUpperCase(),
    instrumentId: typeof params.instrumentId === "string" ? params.instrumentId : undefined,
    assetType: typeof params.assetType === "string" ? params.assetType : undefined,
    market: typeof params.market === "string" ? params.market : undefined,
    providerSymbols,
    start: typeof params.start === "string" ? params.start : undefined,
    end: typeof params.end === "string" ? params.end : undefined,
    interval: typeof params.interval === "string" ? params.interval : undefined,
    limit: typeof params.limit === "number" ? params.limit : undefined,
    depth: typeof params.depth === "number" ? params.depth : undefined,
    window: typeof params.window === "string" ? params.window : undefined,
    exchange: typeof params.exchange === "string" ? params.exchange : undefined,
    expiration: typeof params.expiration === "string" ? params.expiration : undefined,
    greeks: params.greeks === true,
    seriesType: typeof params.seriesType === "string" ? params.seriesType : undefined,
    history: typeof params.history === "number" ? params.history : undefined,
    address: typeof params.address === "string" ? params.address : undefined,
    chain: typeof params.chain === "string" ? params.chain : undefined,
  };
}

/**
 * Dispatch one market-data capability to a provider adapter.
 *
 * When `params.provider` names a provider it is the ONLY adapter tried (the
 * Python router owns fallback). When it is absent, adapters are tried in
 * registration order and the first OK payload wins.
 */
export async function fetchMarketData(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const request = toRequest(params);
  if (!request.symbol) {
    return { status: "UNAVAILABLE", failureClass: "invalid_request", error: "symbol is required" };
  }
  const named = typeof params.provider === "string" ? getMarketProvider(String(params.provider)) : undefined;
  const candidates = named
    ? [named]
    : PROVIDERS.filter((p) => p.capabilityIds.includes(request.capability));
  if (candidates.length === 0) {
    return {
      status: "UNAVAILABLE",
      failureClass: "not_covered",
      error: `no adapter serves capability '${request.capability}'`,
    };
  }

  let lastError: ProviderError | null = null;
  for (const provider of candidates) {
    try {
      const payload = await provider.fetch(request);
      if (payload && payload.status === "OK") {
        return {
          ...payload,
          provider: provider.id,
          // The health ledger is not used for market_data (the Python router +
          // MarketStore own provider health); this context is informational.
          healthContext: { source: provider.id, market: request.market ?? "*", assetClass: request.assetType ?? "*" },
        } as unknown as DataBridgeResult;
      }
    } catch (err) {
      lastError = err instanceof ProviderError ? err : new ProviderError(String(err));
    }
  }
  const code = lastError?.code ?? "DATA_NOT_AVAILABLE";
  return {
    status: "UNAVAILABLE",
    provider: candidates[0]?.id,
    error: lastError?.message ?? `no provider returned data for ${request.symbol}`,
    failureClass: code === "SYMBOL_NOT_FOUND" ? "not_found" : code === "RATE_LIMITED" ? "rate_limited" : "no_data",
    diagnostics: lastError ? [{ category: lastError.code, httpStatus: lastError.httpStatus, retryable: lastError.retryable, detail: lastError.message }] : undefined,
  } as DataBridgeResult;
}
