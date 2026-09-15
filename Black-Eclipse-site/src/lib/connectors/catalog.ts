// ── Provider catalog ────────────────────────────────────────────────────────
// A browsable catalog of every data/intelligence provider BlackEclipse can
// talk to, grouped by what it is FOR (AI, economics, market data, crypto,
// custom). This is a *map of what exists and how it is configured* — it is not
// a second configuration system.
//
// Honesty rules:
//   - `status` reflects reality. A provider gated on an env var is only
//     "connected" when that var is actually set at boot.
//   - `configure` says where the operator must go. Env-gated providers cannot
//     be saved from the browser, so the UI links to the right screen instead of
//     pretending a button wrote a key.
//   - Economics entries are DERIVED from `ECON_SOURCES`, so the catalog cannot
//     drift from the fetch layer.

import { ECON_SOURCES } from "@/lib/economics/sources";
import { LLM_PRESETS, CATALOG_ENV_VARS } from "@/lib/agent/presets";
import { CRYPTO_CONNECTOR_ID } from "./providers/crypto";

export type ProviderCategory = "ai" | "economics" | "market" | "crypto" | "custom";

export const CATEGORY_META: Record<ProviderCategory, { label: string; description: string }> = {
  ai: { label: "AI & LLM", description: "Models that power chat and the research agents." },
  economics: { label: "Economics & Macro", description: "Central banks, statistical agencies and multilateral data." },
  market: { label: "Market Data", description: "Equities, indices and price sources." },
  crypto: { label: "Crypto", description: "Digital-asset prices and tickers." },
  custom: { label: "Your own data", description: "Bring an arbitrary REST API or a hand-defined dataset." },
};

export type ProviderStatus = "connected" | "not_configured" | "builtin" | "available";

/** Minimal read-only view of the environment (avoids requiring NODE_ENV). */
export type EnvLike = Record<string, string | undefined>;

export type ConfigureTarget =
  | { target: "agent" }
  | { target: "integrations" }
  | { target: "wizard" }
  /** Built in and working — nothing to configure. */
  | { target: "none" };

export interface CatalogProvider {
  id: string;
  name: string;
  description: string;
  category: ProviderCategory;
  /** How the provider gets its credentials. */
  auth: "env" | "settings" | "builtin" | "vault";
  /** Env var that gates it, when `auth === "env"`. */
  envVar?: string;
  status: ProviderStatus;
  configure: ConfigureTarget;
  recommended?: boolean;
  docsUrl?: string;
  /** Present for economics entries — the id in `ECON_SOURCES`. */
  sourceId?: string;
}

export interface ProviderCatalog {
  categories: Array<{
    id: ProviderCategory;
    label: string;
    description: string;
    providers: CatalogProvider[];
    connectedCount: number;
  }>;
  /** Env vars that are actually set, so the UI can show per-preset key status. */
  envFlags: Record<string, boolean>;
  totals: { providers: number; connected: number; custom: number };
}

// ── Static, hand-declared providers ────────────────────────────────────────
// Only providers the code actually consumes belong here. Adding an entry that
// nothing calls would be a lie.

interface StaticProvider {
  id: string;
  name: string;
  description: string;
  category: ProviderCategory;
  auth: CatalogProvider["auth"];
  envVar?: string;
  configure: ConfigureTarget;
  recommended?: boolean;
  docsUrl?: string;
}

const STATIC_PROVIDERS: StaticProvider[] = [
  // Market data — built-in scraper chain (see scraper/fetchers/index.ts).
  {
    id: "tradingview",
    name: "TradingView scanner",
    description: "Whole-market scans. Primary source for covered markets.",
    category: "market",
    auth: "builtin",
    configure: { target: "none" },
    recommended: true,
  },
  {
    id: "yfinance",
    name: "yfinance bridge",
    description: "Batched Yahoo quotes via an optional local Python session.",
    category: "market",
    auth: "env",
    envVar: "YAHOO_FINANCE_ENABLED",
    configure: { target: "integrations" },
  },
  {
    id: "scraper",
    name: "HTTP / browser scraper",
    description: "Cheap HTTP + cheerio, with a Playwright escalation for blocked pages.",
    category: "market",
    auth: "builtin",
    configure: { target: "none" },
  },
  {
    id: "finnhub",
    name: "Finnhub",
    description: "Market news, earnings and fundamentals via a free-tier key.",
    category: "market",
    auth: "env",
    envVar: "FINNHUB_API_KEY",
    configure: { target: "integrations" },
    docsUrl: "https://finnhub.io/register",
  },
  {
    id: "polygon",
    name: "Polygon.io",
    description: "US equities/options aggregates, trades and reference data.",
    category: "market",
    auth: "env",
    envVar: "POLYGON_API_KEY",
    configure: { target: "integrations" },
    docsUrl: "https://polygon.io/dashboard/api-keys",
  },
  {
    id: "alphavantage",
    name: "Alpha Vantage",
    description: "Quotes, FX and technical indicators on a free tier.",
    category: "market",
    auth: "env",
    envVar: "ALPHAVANTAGE_API_KEY",
    configure: { target: "integrations" },
    docsUrl: "https://www.alphavantage.co/support/#api-key",
  },
  {
    id: "twelvedata",
    name: "Twelve Data",
    description: "Global equities, FX and crypto with a generous free tier.",
    category: "market",
    auth: "env",
    envVar: "TWELVE_DATA_API_KEY",
    configure: { target: "integrations" },
    docsUrl: "https://twelvedata.com/account/api-keys",
  },
  {
    id: "marketstack",
    name: "Marketstack",
    description: "End-of-day and intraday global equity prices.",
    category: "market",
    auth: "env",
    envVar: "MARKETSTACK_API_KEY",
    configure: { target: "integrations" },
    docsUrl: "https://marketstack.com/product",
  },

  // Crypto — the built-in connector registered by the connector layer.
  {
    id: CRYPTO_CONNECTOR_ID,
    name: "Binance (crypto)",
    description: "Free public 24h ticker. No API key required.",
    category: "crypto",
    auth: "builtin",
    configure: { target: "none" },
    recommended: true,
  },
  {
    id: "coingecko",
    name: "CoinGecko",
    description: "Broad crypto market data: prices, market cap, categories.",
    category: "crypto",
    auth: "env",
    envVar: "COINGECKO_API_KEY",
    configure: { target: "integrations" },
    docsUrl: "https://www.coingecko.com/en/developers/dashboard",
  },
  {
    id: "coinmarketcap",
    name: "CoinMarketCap",
    description: "Rankings, quotes and supply data for thousands of assets.",
    category: "crypto",
    auth: "env",
    envVar: "COINMARKETCAP_API_KEY",
    configure: { target: "integrations" },
    docsUrl: "https://pro.coinmarketcap.com/account",
  },
  {
    id: "kraken",
    name: "Kraken",
    description: "Exchange tickers and OHLC for major pairs. Public endpoints need no key.",
    category: "crypto",
    auth: "builtin",
    configure: { target: "none" },
    docsUrl: "https://docs.kraken.com/api/",
  },

  // Custom — the operator-facing path.
  {
    id: "custom-rest",
    name: "Custom REST API",
    description: "Connect any REST endpoint, test it, map its response into a dataset.",
    category: "custom",
    auth: "vault",
    configure: { target: "wizard" },
    recommended: true,
  },
  {
    id: "custom-dataset",
    name: "Hand-defined dataset",
    description: "Declare fields and record identity yourself, without a live API.",
    category: "custom",
    auth: "vault",
    configure: { target: "wizard" },
  },
];

/**
 * AI providers are DERIVED from `LLM_PRESETS`, so adding a preset there makes it
 * appear in the catalog (and the AI Agent picker) with no second edit.
 */
function aiProviders(env: EnvLike): CatalogProvider[] {
  const entries: CatalogProvider[] = LLM_PRESETS.filter((p) => p.id !== "custom").map((preset) => {
    const connected = preset.keyless ? true : Boolean(preset.envVar && env[preset.envVar]);
    return {
      id: `llm:${preset.id}`,
      name: preset.name,
      description: preset.description,
      category: "ai" as const,
      auth: preset.keyless ? ("builtin" as const) : ("env" as const),
      envVar: preset.keyless ? undefined : preset.envVar,
      status: connected ? ("connected" as const) : ("not_configured" as const),
      configure: { target: "agent" as const },
      recommended: preset.recommended,
      docsUrl: preset.docsUrl,
    };
  });

  // The offline fallback always works, so it is listed explicitly.
  entries.push({
    id: "llm:mock",
    name: "Built-in mock",
    description: "Deterministic offline provider. Always available as the last resort.",
    category: "ai",
    auth: "builtin",
    status: "builtin",
    configure: { target: "none" },
  });
  return entries;
}

// Economics providers that need a key are shown as not_configured until the env
// var is set — the fetch layer refuses to call them otherwise.
function economicsProviders(env: EnvLike): CatalogProvider[] {
  return ECON_SOURCES.map((source) => {
    const gated = Boolean(source.keyRequired && source.keyEnv);
    const connected = gated ? Boolean(env[source.keyEnv as string]) : true;
    return {
      id: `econ:${source.id}`,
      sourceId: source.id,
      name: source.label,
      description: source.description ?? "Macro-economic time series.",
      category: "economics" as const,
      auth: gated ? ("env" as const) : ("builtin" as const),
      envVar: gated ? source.keyEnv : undefined,
      status: gated ? (connected ? "connected" : "not_configured") : "builtin",
      configure: gated ? { target: "integrations" as const } : { target: "none" as const },
    };
  });
}

function statusOf(provider: StaticProvider, env: EnvLike): ProviderStatus {
  if (provider.auth === "builtin") return "builtin";
  if (provider.envVar) return env[provider.envVar] ? "connected" : "not_configured";
  return "available";
}

/**
 * Build the catalog. Pure: all environment access is passed in, so this is
 * testable without touching `process.env`.
 */
export function buildCatalog(env: EnvLike = process.env): ProviderCatalog {
  const staticEntries: CatalogProvider[] = STATIC_PROVIDERS.map((p) => ({
    id: p.id,
    name: p.name,
    description: p.description,
    category: p.category,
    auth: p.auth,
    envVar: p.envVar,
    status: statusOf(p, env),
    configure: p.configure,
    recommended: p.recommended,
    docsUrl: p.docsUrl,
  }));

  const all = [...staticEntries, ...aiProviders(env), ...economicsProviders(env)];

  const order: ProviderCategory[] = ["ai", "economics", "market", "crypto", "custom"];
  const categories = order
    .map((id) => {
      const providers = all.filter((p) => p.category === id);
      return {
        id,
        label: CATEGORY_META[id].label,
        description: CATEGORY_META[id].description,
        providers,
        connectedCount: providers.filter((p) => p.status === "connected" || p.status === "builtin").length,
      };
    })
    .filter((c) => c.providers.length > 0);

  return {
    categories,
    envFlags: Object.fromEntries(CATALOG_ENV_VARS.map((key) => [key, Boolean(env[key])])),
    totals: {
      providers: all.length,
      connected: all.filter((p) => p.status === "connected" || p.status === "builtin").length,
      custom: all.filter((p) => p.category === "custom").length,
    },
  };
}
