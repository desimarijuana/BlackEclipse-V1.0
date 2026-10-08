// Market Data provider adapter contract (TS side).
//
// The Python Market Data Gateway sends ONE capability request to the bridge;
// this package turns it into provider calls. A provider adapter returns the
// SAME normalized camelCase payload shape the Python normalizers expect, or
// throws/returns null so the gateway can fall back to the next provider.
//
// Exactly ONE HTTP transport is used: every adapter calls `safeGet` (the
// existing SSRF-hardened outbound layer) or an existing scraper helper. No new
// HTTP client, no new secret handling — credentials come from `resolveProviderKey`.

import type { DataBridgeResult } from "@/lib/harness/data-bridge-types";

/** One market-data capability request from the Python gateway. */
export interface MarketDataRequest {
  capability: string;             // quote | historical | ohlcv | volume | orderbook | trades |
                                  // market_cap | supply | funding | open_interest | options | fx | bonds
  symbol: string;                 // canonical symbol
  instrumentId?: string;
  assetType?: string;
  market?: string;
  /** Per-provider symbol map resolved by the Python instrument master. */
  providerSymbols?: Record<string, string>;
  // capability-specific params
  start?: string;
  end?: string;
  interval?: string;
  limit?: number;
  depth?: number;
  window?: string;
  exchange?: string;
  expiration?: string;
  greeks?: boolean;
  seriesType?: string;
  history?: number;
}

/** A provider adapter. `fetch` returns the normalized payload or throws. */
export interface MarketProvider {
  id: string;
  capabilityIds: string[];
  fetch(request: MarketDataRequest): Promise<Record<string, unknown>>;
}

export class ProviderError extends Error {
  constructor(
    message: string,
    readonly code: string = "PROVIDER_UNAVAILABLE",
    readonly retryable = true,
    readonly httpStatus?: number,
  ) {
    super(message);
    this.name = "ProviderError";
  }
}

export function unavailableMarket(reason: string, code = "DATA_NOT_AVAILABLE"): DataBridgeResult {
  return { status: "UNAVAILABLE", failureClass: code === "DATA_NOT_AVAILABLE" ? "no_data" : undefined, error: reason };
}
