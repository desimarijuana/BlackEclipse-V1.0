// Crypto fetcher — uses free public endpoints (no key, no rate-limit issues
// for light usage). Falls back gracefully if the endpoint is unreachable.
//
// The request/parse logic now lives in the universal connector layer
// (`src/lib/connectors/providers/crypto.ts`). This module is kept as the
// `FetchResult`-shaped facade the scraper chain depends on, so the fallback
// chain in `fetchers/index.ts` is unchanged.

import type { FetchResult } from "../types";
import { cryptoConnector, parseBinanceTicker, toBinancePair } from "@/lib/connectors/providers/crypto";

export { parseBinanceTicker, toBinancePair };

/**
 * Fetch a crypto quote from Binance's free public 24hr ticker endpoint.
 * The symbol is expected to be the base asset (e.g. "BTC" → "BTCUSDT").
 */
export async function fetchCryptoQuote(symbol: string): Promise<FetchResult> {
  const result = await cryptoConnector.fetch({ capability: "PRICE", params: { symbol } });
  if (result.ok && result.data) {
    const quote = result.data as { price: number; changePct: number; volume?: number };
    return { status: "ok", quote: { symbol, ...quote }, source: "crypto" };
  }
  // Map connector errors back onto the scraper's failure vocabulary.
  const message = result.error?.message ?? "Crypto fetch failed";
  if (message.includes("timed out")) return { status: "timeout", error: message, source: "crypto" };
  if (message.includes("HTTP 403") || message.includes("HTTP 429")) {
    return { status: "blocked", error: message, source: "crypto" };
  }
  if (message.startsWith("HTTP ")) return { status: "network_error", error: message, source: "crypto" };
  return { status: "network_error", error: message, source: "crypto" };
}
