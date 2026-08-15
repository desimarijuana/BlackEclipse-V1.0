// Crypto fetcher — uses free public endpoints (no key, no rate-limit issues
// for light usage). Falls back gracefully if the endpoint is unreachable.

import type { FetchResult, Quote } from "../types";
import { toErrorLike } from "../types";

// Binance public 24hr ticker — no API key required for public endpoints.
const BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/24hr";

/**
 * Fetch a crypto quote from Binance's free public 24hr ticker endpoint.
 * The symbol is expected to be the base asset (e.g. "BTC" → "BTCUSDT").
 */
export async function fetchCryptoQuote(symbol: string): Promise<FetchResult> {
  const base = symbol.trim().toUpperCase();
  const pair = base.endsWith("USDT") ? base : `${base}USDT`;

  try {
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), 8000);
    const res = await fetch(`${BINANCE_TICKER}?symbol=${pair}`, {
      signal: controller.signal,
    });
    clearTimeout(t);

    if (!res.ok) {
      if (res.status === 403 || res.status === 429) {
        return { status: "blocked", error: `HTTP ${res.status}`, source: "crypto" };
      }
      return { status: "network_error", error: `HTTP ${res.status}`, source: "crypto" };
    }

    const data = await res.json();
    const price = parseFloat(data?.lastPrice || "0");
    const changePct = parseFloat(data?.priceChangePercent || "0");
    const volume = parseFloat(data?.quoteVolume || "0");

    if (!isNaN(price) && price > 0) {
      const quote: Quote = { symbol, price, changePct, volume };
      return { status: "ok", quote, source: "crypto" };
    }
    return { status: "empty", error: "No valid price in ticker", source: "crypto" };
  } catch (err: unknown) {
    const e = toErrorLike(err);
    const msg = e.message || "Crypto fetch failed";
    if (e.name === "AbortError") {
      return { status: "timeout", error: msg, source: "crypto" };
    }
    return { status: "network_error", error: msg, source: "crypto" };
  }
}
