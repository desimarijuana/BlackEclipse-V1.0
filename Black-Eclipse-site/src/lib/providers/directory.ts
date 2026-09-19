// ── Provider directory (why a provider exists, who uses it, where it lives) ──
// A single, client-safe source of human context for every provider the settings
// UI renders. It answers the questions a user actually has:
//
//   What is this API?       → purpose
//   Which feature uses it?  → usedBy
//   Is it free?             → tier
//   Where do I configure it? → home
//
// `home` is the key to the Settings information architecture: **every provider
// has exactly one home**, so a given API is listed in one section and never
// repeated across several. The Settings rail is organised by home:
//
//   ai            → AI / LLM
//   investor-eye  → Investor Eye (world-state event sources)
//   economics     → Economics (macro series & calendars)
//   news          → News (headlines & feeds)
//   market         → Market Screener (prices, fundamentals, crypto)
//
// It is deliberately NOT a second configuration system: status, keys and
// testing still come from `/api/providers` and `/api/provider-keys`. This module
// only supplies the "why / where" metadata, keyed by env var (vault keys) or by
// catalog provider id (built-in providers).

import type { AppTab } from "@/lib/search/types";

export type ProviderTier = "builtin" | "free" | "free-tier" | "paid";

/** The one Settings section a provider belongs to. */
export type SettingsHome = "ai" | "investor-eye" | "economics" | "news" | "market";

export interface ProviderDirectoryEntry {
  /** What data or service the provider supplies. */
  purpose: string;
  /** BlackEclipse features that consume it. */
  usedBy: string[];
  /** Cost expectation, only where we actually know it. */
  tier: ProviderTier;
  /** The single Settings section that configures it. */
  home: SettingsHome;
}

const LLM_FEATURES = ["Chat", "Research", "Investor Eye analyst"];

/**
 * Keyed by env var for vault keys, and by catalog id for built-in providers.
 * Both lookup paths go through `providerMeta`.
 */
const ENTRIES: Record<string, ProviderDirectoryEntry> = {
  // ── AI / LLM ──────────────────────────────────────────────────────────────
  OPENAI_API_KEY: { purpose: "Large language models", usedBy: LLM_FEATURES, tier: "paid", home: "ai" },
  ANTHROPIC_API_KEY: { purpose: "Large language models", usedBy: LLM_FEATURES, tier: "paid", home: "ai" },
  OLLAMA_BASE_URL: { purpose: "Local large language models", usedBy: LLM_FEATURES, tier: "free", home: "ai" },
  GROQ_API_KEY: { purpose: "Fast open-model inference", usedBy: LLM_FEATURES, tier: "free-tier", home: "ai" },
  DEEPSEEK_API_KEY: { purpose: "Reasoning / coding models", usedBy: LLM_FEATURES, tier: "paid", home: "ai" },
  MISTRAL_API_KEY: { purpose: "Open-weight & commercial models", usedBy: LLM_FEATURES, tier: "paid", home: "ai" },
  GEMINI_API_KEY: { purpose: "Multimodal models", usedBy: LLM_FEATURES, tier: "free-tier", home: "ai" },
  XAI_API_KEY: { purpose: "Grok models", usedBy: LLM_FEATURES, tier: "paid", home: "ai" },
  OPENROUTER_API_KEY: { purpose: "Model routing & fallback", usedBy: LLM_FEATURES, tier: "paid", home: "ai" },
  TOGETHER_API_KEY: { purpose: "Hosted open-model inference", usedBy: LLM_FEATURES, tier: "paid", home: "ai" },
  PERPLEXITY_API_KEY: { purpose: "Search-grounded models", usedBy: ["Research", "News analysis"], tier: "paid", home: "ai" },
  FIREWORKS_API_KEY: { purpose: "Hosted open-model inference", usedBy: LLM_FEATURES, tier: "paid", home: "ai" },

  // ── Economics & macro (its own section) ───────────────────────────────────
  FRED_API_KEY: { purpose: "Economics & macro series", usedBy: ["Economics", "Investor Eye macro"], tier: "free-tier", home: "economics" },
  BEA_API_KEY: { purpose: "Economics & macro series", usedBy: ["Economics"], tier: "free-tier", home: "economics" },
  BLS_API_KEY: { purpose: "Economics & macro series", usedBy: ["Economics"], tier: "free-tier", home: "economics" },
  TRADING_ECONOMICS_API_KEY: { purpose: "Global macro & calendars", usedBy: ["Economics"], tier: "paid", home: "economics" },
  AKSHARE_API_KEY: { purpose: "China market & macro data", usedBy: ["Economics"], tier: "free", home: "economics" },

  // ── News (its own section) ────────────────────────────────────────────────
  FINNHUB_API_KEY: { purpose: "Market news & headlines", usedBy: ["News", "Investor Eye sentiment"], tier: "free-tier", home: "news" },

  // ── Market Screener (prices, fundamentals, crypto) ────────────────────────
  tradingview: { purpose: "Market + price data", usedBy: ["Market Screener", "Investor Eye", "Charts"], tier: "builtin", home: "market" },
  yfinance: { purpose: "Market + price data", usedBy: ["Market Screener", "Charts"], tier: "free", home: "market" },
  scraper: { purpose: "Market + price data", usedBy: ["Market Screener", "Investor Eye"], tier: "builtin", home: "market" },
  sec_edgar: { purpose: "SEC filings & company data", usedBy: ["Market Screener", "Fundamentals"], tier: "builtin", home: "market" },
  "sec-edgar": { purpose: "SEC filings & company data", usedBy: ["Market Screener", "Fundamentals"], tier: "builtin", home: "market" },
  POLYGON_API_KEY: { purpose: "US equities, FX & aggregates", usedBy: ["Market Screener", "Charts"], tier: "free-tier", home: "market" },
  ALPHAVANTAGE_API_KEY: { purpose: "Quotes, FX & earnings", usedBy: ["Market Screener", "Earnings"], tier: "free-tier", home: "market" },
  TWELVE_DATA_API_KEY: { purpose: "Global equities, FX & crypto", usedBy: ["Market Screener", "Charts"], tier: "free-tier", home: "market" },
  MARKETSTACK_API_KEY: { purpose: "End-of-day & intraday prices", usedBy: ["Market Screener", "Charts"], tier: "free-tier", home: "market" },
  FINANCIALMODELINGPREP_API_KEY: { purpose: "Fundamentals, ratios & estimates", usedBy: ["Market Screener", "Fundamentals"], tier: "free-tier", home: "market" },
  COINGECKO_API_KEY: { purpose: "Crypto market data", usedBy: ["Market Screener", "Investor Eye"], tier: "free-tier", home: "market" },
  COINMARKETCAP_API_KEY: { purpose: "Crypto rankings & quotes", usedBy: ["Market Screener"], tier: "free-tier", home: "market" },
  "builtin:crypto": { purpose: "Crypto prices & tickers", usedBy: ["Market Screener", "Investor Eye"], tier: "builtin", home: "market" },
  kraken: { purpose: "Crypto prices & tickers", usedBy: ["Market Screener", "Charts"], tier: "builtin", home: "market" },

  // ── Custom (Market Screener wizard) ───────────────────────────────────────
  "custom-rest": { purpose: "Bring your own REST data", usedBy: ["Custom widgets"], tier: "free", home: "market" },
  "custom-dataset": { purpose: "Hand-defined dataset", usedBy: ["Custom widgets"], tier: "free", home: "market" },
};

/** Fallback context by catalog category, so nothing renders blank. */
const CATEGORY_FALLBACK: Record<string, ProviderDirectoryEntry> = {
  ai: { purpose: "Large language models", usedBy: LLM_FEATURES, tier: "free-tier", home: "ai" },
  market: { purpose: "Market data", usedBy: ["Market Screener", "Charts"], tier: "free-tier", home: "market" },
  crypto: { purpose: "Crypto market data", usedBy: ["Market Screener"], tier: "free-tier", home: "market" },
  economics: { purpose: "Economics & macro data", usedBy: ["Economics"], tier: "free-tier", home: "economics" },
  custom: { purpose: "Your own data", usedBy: ["Custom widgets"], tier: "free", home: "market" },
};

/**
 * Look up the purpose/used-by/tier/home for a provider.
 *
 * @param id       env var (vault key) or catalog provider id (built-in).
 * @param category optional catalog category, used as a fallback.
 */
export function providerMeta(
  id: string,
  category?: keyof typeof CATEGORY_FALLBACK,
): ProviderDirectoryEntry {
  const direct = ENTRIES[id];
  if (direct) return direct;
  // Economics catalog ids look like `econ:fred`; they all live in Economics.
  if (id.startsWith("econ:")) return CATEGORY_FALLBACK.economics;
  if (id.startsWith("llm:")) return CATEGORY_FALLBACK.ai;
  return (category && CATEGORY_FALLBACK[category]) || {
    purpose: "Data provider",
    usedBy: ["Investor Eye"],
    tier: "free-tier",
    home: "market",
  };
}

/**
 * The single Settings section a provider belongs to. Prefer the env var (for
 * key-gated providers) then the catalog id, then the category fallback.
 */
export function providerHome(
  id: string,
  envVar?: string,
  category?: keyof typeof CATEGORY_FALLBACK,
): SettingsHome {
  if (envVar && ENTRIES[envVar]) return ENTRIES[envVar].home;
  return providerMeta(id, category).home;
}

export const TIER_LABEL: Record<ProviderTier, string> = {
  builtin: "Built-in",
  free: "Free",
  "free-tier": "Free tier",
  paid: "Paid",
};

// ── "Used by" → consuming page ───────────────────────────────────────────────
// Lets the registry turn a "Used by: X" label into a link to the actual page
// that consumes the provider, closing the why → where loop.

export interface ConsumingPage {
  /** AppTab value to navigate to. */
  tab: AppTab;
  /** Optional deep-link params for the destination. */
  params?: Record<string, string>;
}

const CONSUMING_PAGES: Record<string, ConsumingPage> = {
  chat: { tab: "chat" },
  research: { tab: "chat" },
  "investor eye analyst": { tab: "investor-eye" },
  "investor eye": { tab: "investor-eye" },
  "investor eye macro": { tab: "investor-eye" },
  "investor eye sentiment": { tab: "investor-eye" },
  "market screener": { tab: "discovery" },
  screener: { tab: "discovery" },
  charts: { tab: "chart" },
  chart: { tab: "chart" },
  economics: { tab: "economics" },
  news: { tab: "news" },
  "news analysis": { tab: "news" },
  fundamentals: { tab: "discovery" },
  earnings: { tab: "discovery" },
  "custom widgets": { tab: "dashboard" },
};

/** The page that consumes a "Used by" label, or null when it is a concept only. */
export function consumingPage(label: string): ConsumingPage | null {
  return CONSUMING_PAGES[label.trim().toLowerCase()] ?? null;
}

// ── Investor Eye feature map ────────────────────────────────────────────────
// Which provider powers each Investor Eye capability. This is the "show which
// provider powers each feature" requirement, in one place. It is informational:
// the chips reference providers whose configuration lives in their own section.

export interface InvestorEyeFeature {
  id: string;
  label: string;
  description: string;
  /** Provider ids (env vars or catalog ids) that power this feature. */
  providers: string[];
}

export const INVESTOR_EYE_FEATURES: InvestorEyeFeature[] = [
  {
    id: "events",
    label: "Global event map",
    description: "Geopolitical and market events plotted by region.",
    providers: ["gdelt", "news-feeds"],
  },
  {
    id: "conflict",
    label: "Conflict lens",
    description: "Active-conflict wires beyond GDELT coding.",
    providers: ["news-feeds"],
  },
  {
    id: "macro",
    label: "Macro / economics",
    description: "Inflation, rates, GDP and labor series.",
    providers: ["FRED_API_KEY", "BEA_API_KEY", "BLS_API_KEY", "TRADING_ECONOMICS_API_KEY"],
  },
  {
    id: "markets",
    label: "Markets & prices",
    description: "Quotes, scans and index levels.",
    providers: ["tradingview", "yfinance", "FINNHUB_API_KEY", "POLYGON_API_KEY"],
  },
  {
    id: "fundamentals",
    label: "Fundamentals",
    description: "Company financials, ratios and filings.",
    providers: ["sec-edgar", "FINANCIALMODELINGPREP_API_KEY"],
  },
  {
    id: "earnings",
    label: "Earnings & calendar",
    description: "Earnings dates and economic releases.",
    providers: ["FINNHUB_API_KEY", "ALPHAVANTAGE_API_KEY", "econ:economic-calendar"],
  },
  {
    id: "news",
    label: "News & sentiment",
    description: "Headlines feeding the sentiment glow.",
    providers: ["news-feeds", "FINNHUB_API_KEY"],
  },
  {
    id: "crypto",
    label: "Crypto",
    description: "Digital-asset prices and tickers.",
    providers: ["builtin:crypto", "COINGECKO_API_KEY", "COINMARKETCAP_API_KEY"],
  },
];

/** Human label for a provider id, for the feature map. */
export function providerLabel(id: string): string {
  const labels: Record<string, string> = {
    gdelt: "GDELT",
    "news-feeds": "RSS news feeds",
    "econ:economic-calendar": "Economic Calendar",
    "sec-edgar": "SEC EDGAR",
    tradingview: "TradingView scanner",
    yfinance: "yfinance bridge",
    "builtin:crypto": "Binance",
    FRED_API_KEY: "FRED",
    BEA_API_KEY: "BEA",
    BLS_API_KEY: "BLS",
    TRADING_ECONOMICS_API_KEY: "Trading Economics",
    FINNHUB_API_KEY: "Finnhub",
    POLYGON_API_KEY: "Polygon.io",
    ALPHAVANTAGE_API_KEY: "Alpha Vantage",
    FINANCIALMODELINGPREP_API_KEY: "Financial Modeling Prep",
    COINGECKO_API_KEY: "CoinGecko",
    COINMARKETCAP_API_KEY: "CoinMarketCap",
  };
  return labels[id] ?? providerMeta(id).purpose;
}

/** The Settings section a feature-map chip's provider is configured in. */
export function providerHomeForLabel(id: string): SettingsHome {
  return providerMeta(id).home;
}
