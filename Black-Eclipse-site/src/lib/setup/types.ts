// ── First-run setup types (client-safe) ─────────────────────────────────────
// Shared vocabulary for the onboarding catalog, capability mapping, bundles,
// server state and API payloads. This module must stay free of Prisma/Node
// imports so the browser can use the same definitions the server enforces.

export type SetupMode = "personal" | "commercial";

/**
 * Where a source sits in the product:
 *   included  — open data that ships with Eclipse, no account
 *   connected — the user brings their own key/account
 *   advanced  — community/scraper sources, off unless explicitly accepted
 */
export type SourceTier = "included" | "connected" | "advanced";

/** Whether the source's terms fit a commercial product. */
export type CommercialStatus = "ok" | "attribution" | "personal-only" | "verify";

export type SourceCategory =
  | "filings"
  | "market"
  | "crypto"
  | "news"
  | "macro"
  | "research"
  | "events";

export type SourceId =
  // Included open data
  | "sec"
  | "fred"
  | "bea"
  | "bls"
  | "worldbank"
  | "eurostat"
  | "gdelt"
  | "usgs"
  | "firms"
  | "news-rss"
  // Connected market / fundamentals
  | "polygon"
  | "twelvedata"
  | "finnhub"
  | "alphavantage"
  | "marketstack"
  | "fmp"
  // Connected crypto
  | "coinmarketcap"
  | "coingecko-paid"
  // Connected macro / search
  | "tradingeconomics"
  | "tavily"
  | "brave"
  | "exa"
  | "serper"
  // Advanced / community
  | "tradingview"
  | "yfinance"
  | "http"
  | "browser"
  | "scrapling"
  | "binance"
  | "kraken"
  | "coingecko"
  | "duckduckgo";

export interface SourceDef {
  id: SourceId;
  label: string;
  short: string;
  tier: SourceTier;
  category: SourceCategory;
  /** What the source powers, in user language. */
  powers: string[];
  commercial: CommercialStatus;
  /** Why the badge applies / what to verify. */
  note?: string;
  termsUrl?: string;
  /** Vault env var for a connected source. */
  envVar?: string;
  /** Attribution line the UI must display when this source is used. */
  attribution?: string;
  /** True for sources that are enabled by the safe default. */
  defaultOn: boolean;
}

export type CapabilityId =
  | "chat"
  | "company"
  | "macro"
  | "events"
  | "prices"
  | "news"
  | "search"
  | "crypto";

export type CapabilityStatus = "ready" | "needs-key" | "off" | "unavailable";

export interface CapabilityDef {
  id: CapabilityId;
  label: string;
  description: string;
  included: SourceId[];
  connected: SourceId[];
  advanced: SourceId[];
}

export type BundleId = "research" | "personal-trader" | "commercial" | "crypto" | "custom";

export interface BundlesDef {
  id: BundleId;
  label: string;
  description: string;
}

/** Non-secret key status, matching /api/provider-keys. */
export interface KeyStatusLite {
  envVar: string;
  configured: boolean;
  stored: boolean;
  fromEnv: boolean;
  testable: boolean;
  publicValue?: boolean;
  hint?: string;
}

export interface SourcePrefs {
  version: 1;
  mode: SetupMode;
  sources: Record<string, boolean>;
  acceptedRestrictedSources: string[];
  updatedAt: string;
}

export interface OnboardingState {
  completed: boolean;
  completedAt?: string;
  mode: SetupMode;
  version: 1;
  aiSkipped?: boolean;
  migrated?: boolean;
}

export type AiChoice =
  | { kind: "local"; presetId: "ollama" | "lmstudio"; baseUrl?: string; model?: string }
  | { kind: "key"; presetId: string; apiKey: string; model?: string }
  | { kind: "custom"; baseUrl: string; apiKey?: string; model: string; contextWindow?: number }
  | { kind: "skip" };

export interface SetupCompleteInput {
  mode: SetupMode;
  bundleId?: BundleId;
  sources: Record<string, boolean>;
  acceptedRestrictedSources?: string[];
  ai?: AiChoice;
  /** Required: the risk notice version the user explicitly accepted. */
  riskAckVersion?: string;
}
