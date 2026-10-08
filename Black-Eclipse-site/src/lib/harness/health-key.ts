// Canonical route keys for the SourceHealth ledger.
//
// A route's health entry is keyed by (source × market × assetClass ×
// capability). The market and asset-class dimensions are normalised to a CLOSED
// vocabulary so the same real route cannot be split across rows by casing
// ("Equity" vs "equity") or an unresolved value ("unknown") — an unnormalised
// key makes per-route success rates wrong and route selection unsound. The
// provider id is likewise collapsed onto one canonical source per provider, so
// production traffic, the health probe and the declared targets all land on the
// SAME row.
//
// The wildcard `*` is reserved for instrument-less capabilities (news/web,
// `market="*"`/`assetClass="*"`) and for a market/class we genuinely cannot
// resolve. An instrument route must never persist a literal `unknown`.

import { COVERAGE } from "./coverage";
import type { AssetClass } from "../instrument-identity";

const KNOWN_MARKETS: ReadonlySet<string> = new Set([
  ...Object.keys(COVERAGE), "US", "CRYPTO", "FX",
]);

// The closed asset-class vocabulary: the `AssetClass` type plus the synthetic
// `macro` class the macro-series route records under (kept distinct, never
// folded to the wildcard).
const KNOWN_ASSET_CLASSES: ReadonlySet<string> = new Set<string>([
  "equity", "etf", "fund", "debt", "crypto", "index", "fx", "commodity", "derivative", "other", "macro",
]);

const HEALTH_ASSET_ALIASES: Readonly<Record<string, AssetClass>> = {
  stock: "equity", stocks: "equity", share: "equity", shares: "equity",
  commonstock: "equity", etfs: "etf", mutualfund: "fund", currencies: "fx",
  currency: "fx", cryptoasset: "crypto", cryptos: "crypto", bond: "debt",
  bonds: "debt", fixedincome: "debt", indices: "index",
};

/** Normalise a market to upper-case when it is in the closed market vocabulary,
 * else the wildcard `*`. */
export function canonicalMarket(raw: string | null | undefined): string {
  const v = String(raw ?? "").trim().toUpperCase();
  return KNOWN_MARKETS.has(v) ? v : "*";
}

/**
 * Whether a raw source/market value is a literal unresolved `unknown` that the
 * canonical vocabulary would fold to `*`. Used by the one-time ledger migration
 * (Phase 2.3) to detect rows that still carry the legacy literal.
 */
export function isLiteralUnknown(raw: string | null | undefined): boolean {
  return String(raw ?? "").trim().toLowerCase() === "unknown";
}

/** Normalise an asset class to the closed enum (case-insensitive, alias-aware),
 * else the wildcard `*` — never a fabricated `unknown`. */
export function canonicalAssetClass(raw: string | null | undefined): string {
  const v = String(raw ?? "").trim().toLowerCase();
  if (!v || v === "unknown" || v === "*") return "*";
  if (KNOWN_ASSET_CLASSES.has(v)) return v;
  return HEALTH_ASSET_ALIASES[v] ?? "*";
}

// Provider/transport id variants → one canonical source id per provider.
const HEALTH_SOURCE_ALIASES: Readonly<Record<string, string>> = {
  "safe-get": "WEB",
  "custom-search": "WEB",
  "sec-xbrl": "SEC",
};

/** Collapse provider/transport id variants onto one canonical source id per
 * provider, so production traffic, the health probe and declared targets all
 * land on the SAME row. */
export function canonicalSource(raw: string | null | undefined): string {
  const v = String(raw ?? "").trim();
  if (!v) return "unknown";
  const lower = v.toLowerCase();
  if (lower.startsWith("duckduckgo")) return "WEB";
  return HEALTH_SOURCE_ALIASES[lower] ?? v;
}

// ── Capability classification ────────────────────────────────────────────────

// Capabilities that fetch no market data of their own, so they must NOT be
// health-recorded: the introspection/reporting routes would otherwise record
// themselves (recursion/self-noise) and the identity/secret resolvers are not
// data routes. Everything else is instrumented at the bridge boundary.
export const NON_DATA_CAPABILITIES: ReadonlySet<string> = new Set([
  "source_health",
  "research_health",
  "route_probe",
  "coverage",
  "capability_matrix",
  "provider_key_status",
  "macro_resolve",
  "mcp_secret_resolve",
  "mcp_oauth_token_set",
  "mcp_oauth_token_get",
  "mcp_oauth_token_clear",
  // The Market Data Layer records its own provider health in the Python
  // MarketStore (the ProviderRouter + circuit breaker own it), so it must not
  // also write the TS SourceHealth ledger with a different route vocabulary.
  "market_data",
]);

// Bridge capability → the health capability name the registry declares. Mostly
// identity, but `market_snapshot` serves a quote, so it reports as `live_quote`.
export const HEALTH_CAPABILITY: Readonly<Record<string, string>> = {
  market_snapshot: "live_quote",
  live_quote: "live_quote",
  price_history: "price_history",
  crypto_market_data: "crypto_market_data",
  fundamentals: "fundamentals",
  financial_statements: "financial_statements",
  sec_filings: "sec_filings",
  news: "news",
  web_search: "web_search",
  web_fetch: "web_fetch",
  macro_series: "macro_series",
};

// The source id to attribute a route to when the result does not name one.
export const DEFAULT_HEALTH_SOURCE: Readonly<Record<string, string>> = {
  market_snapshot: "JDDS",
  live_quote: "LIVE_STRUCTURED",
  price_history: "LIVE_STRUCTURED",
  crypto_market_data: "CRYPTO",
  fundamentals: "JDDS",
  financial_statements: "JDDS",
  sec_filings: "SEC",
  news: "WEB",
  web_search: "WEB",
  web_fetch: "WEB",
  macro_series: "JDDS",
};

