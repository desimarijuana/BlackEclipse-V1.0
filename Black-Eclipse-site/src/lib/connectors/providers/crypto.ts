// ── Built-in connector: Crypto (Binance public ticker) ──────────────────────
// Phase-2 proof of concept. Wraps the exact request/parse logic that used to
// live in `src/lib/scraper/fetchers/crypto.ts`, so migrating the scraper chain
// to this connector produces byte-identical `FetchResult`s.
//
// No API key is required and the endpoint is fixed, so this connector takes no
// configuration. Requests still go through `safeGet` for uniform timeout/size
// handling (the URL is a constant, trusted destination).

import type { FetchResult, Quote } from "../../scraper/types";
import { toErrorLike } from "../../scraper/types";
import { safeGet, OutboundError } from "../security";
import type { ConnectorRequest, ConnectorResult, DataConnector, TestResult } from "../types";
import { isDataSourceEnabled } from "@/lib/data-source-preferences";

export const CRYPTO_CONNECTOR_ID = "builtin:crypto";

const BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/24hr";

/** Normalize a base asset to Binance's `<BASE>USDT` pair. */
export function toBinancePair(symbol: string): string {
  const base = symbol.trim().toUpperCase();
  return base.endsWith("USDT") ? base : `${base}USDT`;
}

interface BinanceTicker {
  lastPrice?: string;
  priceChangePercent?: string;
  volume?: string;
  quoteVolume?: string;
}

/** Pure parse step — shared by the legacy fetcher and the connector. */
export function parseBinanceTicker(symbol: string, data: BinanceTicker | null | undefined): FetchResult {
  const price = parseFloat(data?.lastPrice || "0");
  const changePct = parseFloat(data?.priceChangePercent || "0");
  // Two DIFFERENT 24h volumes, both reported: quote notional (USD/USDT) and
  // base-asset units. `volume` keeps its historical meaning (quote notional);
  // the base units ride alongside so a caller can state which one it means.
  const volumeQuote = parseFloat(data?.quoteVolume || "0");
  const volumeBase = parseFloat(data?.volume || "0");
  if (!Number.isNaN(price) && price > 0) {
    const quote: Quote = { symbol, price, changePct, volume: volumeQuote, volumeQuote };
    if (!Number.isNaN(volumeBase) && volumeBase > 0) quote.volumeBase = volumeBase;
    return { status: "ok", quote, source: "crypto" };
  }
  return { status: "empty", error: "No valid price in ticker", source: "crypto" };
}

async function run(symbol: string): Promise<FetchResult> {
  if (!(await isDataSourceEnabled("binance"))) {
    return { status: "blocked", error: "Binance is disabled in setup", source: "crypto" };
  }
  const pair = toBinancePair(symbol);
  try {
    const res = await safeGet({ url: `${BINANCE_TICKER}?symbol=${pair}`, timeoutMs: 8_000 });
    if (res.status < 200 || res.status >= 300) {
      if (res.status === 403 || res.status === 429) {
        return { status: "blocked", error: `HTTP ${res.status}`, source: "crypto" };
      }
      return { status: "network_error", error: `HTTP ${res.status}`, source: "crypto" };
    }
    return parseBinanceTicker(symbol, JSON.parse(res.text) as BinanceTicker);
  } catch (err: unknown) {
    if (err instanceof OutboundError && err.code === "timeout") {
      return { status: "timeout", error: err.message, source: "crypto" };
    }
    const e = toErrorLike(err);
    if (e.name === "AbortError") {
      return { status: "timeout", error: e.message || "Crypto fetch timed out", source: "crypto" };
    }
    return { status: "network_error", error: e.message || "Crypto fetch failed", source: "crypto" };
  }
}

export const cryptoConnector: DataConnector = {
  id: CRYPTO_CONNECTOR_ID,
  name: "Binance (crypto)",
  description: "Free public 24h ticker for crypto pairs. No API key required.",
  capabilities: ["PRICE"],
  kind: "builtin",
  isConfigured: () => true,

  async test(params: Record<string, string> = {}): Promise<TestResult> {
    const symbol = params.symbol || "BTC";
    const result = await run(symbol);
    if (result.status === "ok" && result.quote) {
      return { ok: true, state: "CONNECTED", message: `Connected — ${result.quote.price} for ${symbol}` };
    }
    const state = result.status === "blocked" ? "RATE_LIMITED" : "ERROR";
    return { ok: false, state, message: result.error || "Crypto connector failed" };
  },

  async fetch(request: ConnectorRequest): Promise<ConnectorResult> {
    const retrievedAt = new Date().toISOString();
    if (request.capability !== "PRICE") {
      return {
        ok: false,
        error: { code: "unsupported_capability", message: `crypto provides PRICE, not ${request.capability}` },
        provenance: "UNAVAILABLE",
        source: "crypto",
        retrievedAt,
      };
    }
    const symbol = request.params?.symbol;
    if (!symbol) {
      return {
        ok: false,
        error: { code: "missing_param", message: "symbol is required" },
        provenance: "UNAVAILABLE",
        source: "crypto",
        retrievedAt,
      };
    }
    const result = await run(symbol);
    if (result.status === "ok" && result.quote) {
      return { ok: true, data: result.quote, provenance: "LIVE", source: "crypto", retrievedAt };
    }
    return {
      ok: false,
      error: { code: "network", message: result.error || "Crypto fetch failed" },
      provenance: "UNAVAILABLE",
      source: "crypto",
      retrievedAt,
    };
  },
};
