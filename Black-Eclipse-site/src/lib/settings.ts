// ─── Settings / Configuration vault ────────────────────────────────────
// Central place for user-configurable settings, persisted in JDDS
// (SystemConfig key/value table) with sensible env-var fallbacks.
//
// Every setting here is surfaced on the Settings screen so the user can
// control the entire site from one place — LLM provider, market data,
// news feeds, app preferences, and data hygiene.

import { prisma } from "@/lib/db";

// ─── Low-level key/value helpers ───────────────────────────────────────

export async function getConfig(key: string): Promise<string | null> {
  try {
    const row = await prisma.systemConfig.findUnique({ where: { key } });
    return row?.value ?? null;
  } catch {
    return null;
  }
}

export async function setConfig(key: string, value: string): Promise<void> {
  await prisma.systemConfig.upsert({
    where: { key },
    update: { value },
    create: { key, value },
  });
}

export async function getConfigJSON<T>(key: string, fallback: T): Promise<T> {
  const raw = await getConfig(key);
  if (!raw) return fallback;
  try {
    return { ...fallback, ...JSON.parse(raw) } as T;
  } catch {
    return fallback;
  }
}

export async function setConfigJSON(key: string, value: unknown): Promise<void> {
  await setConfig(key, JSON.stringify(value));
}

// ─── LLM / Agent provider configuration ────────────────────────────────

export type LLMProviderName = "auto" | "openai" | "ollama" | "anthropic" | "mock";

export interface LLMConfig {
  provider: LLMProviderName;
  baseUrl: string;
  apiKey: string;
  model: string;
}

export const DEFAULT_LLM_CONFIG: LLMConfig = {
  provider: "auto",
  baseUrl: "https://api.openai.com/v1",
  apiKey: "",
  model: "gpt-4o-mini",
};

const LLM_KEY = "llm_config";

// Effective LLM config = DB overrides on top of env defaults.
export async function getLLMConfig(): Promise<LLMConfig> {
  const dbCfg = await getConfigJSON<LLMConfig>(LLM_KEY, DEFAULT_LLM_CONFIG);
  const envProvider: LLMProviderName =
    process.env.OLLAMA_BASE_URL ? "ollama"
    : process.env.ANTHROPIC_API_KEY ? "anthropic"
    : process.env.OPENAI_API_KEY ? "openai"
    : "mock";

  // Resolve an effective base url / model from env when the DB hasn't set one.
  let baseUrl = dbCfg.baseUrl || DEFAULT_LLM_CONFIG.baseUrl;
  let model = dbCfg.model || DEFAULT_LLM_CONFIG.model;
  let apiKey = dbCfg.apiKey;

  if (dbCfg.provider === "auto") {
    if (process.env.OLLAMA_BASE_URL) {
      baseUrl = (process.env.OLLAMA_BASE_URL.replace(/\/$/, "") + "/v1");
      model = process.env.OLLAMA_MODEL || "llama3.1";
      apiKey = process.env.OLLAMA_API_KEY || "ollama";
    } else if (process.env.ANTHROPIC_API_KEY) {
      baseUrl = process.env.OPENAI_BASE_URL || "https://api.openai.com/v1";
      model = process.env.OPENAI_MODEL || "gpt-4o-mini";
      apiKey = process.env.ANTHROPIC_API_KEY;
    } else if (process.env.OPENAI_API_KEY) {
      baseUrl = process.env.OPENAI_BASE_URL || "https://api.openai.com/v1";
      model = process.env.OPENAI_MODEL || "gpt-4o-mini";
      apiKey = process.env.OPENAI_API_KEY;
    }
    return { provider: envProvider, baseUrl, model, apiKey };
  }

  return { ...dbCfg, baseUrl, model, apiKey };
}

export async function setLLMConfig(config: Partial<LLMConfig>): Promise<LLMConfig> {
  const next = await getLLMConfig();
  const merged: LLMConfig = {
    ...next,
    ...config,
  };
  if (merged.provider !== "mock" && !merged.apiKey) {
    throw new Error("An API key is required for a real LLM provider");
  }
  await setConfigJSON(LLM_KEY, merged);
  return merged;
}

// ─── News feed configuration ───────────────────────────────────────────

export interface NewsFeed {
  id: string;
  url: string;
  source: string;
  enabled: boolean;
}

export const DEFAULT_NEWS_FEEDS: NewsFeed[] = [
  { id: "yahoo", url: "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC,^IXIC,^DJI&region=US&lang=en-US", source: "Yahoo Finance", enabled: true },
  { id: "coindesk", url: "https://www.coindesk.com/arc/outboundfeeds/rss/", source: "CoinDesk", enabled: true },
  { id: "cointelegraph", url: "https://cointelegraph.com/rss", source: "CoinTelegraph", enabled: true },
  { id: "cnbc", url: "https://www.cnbc.com/id/100003114/device/rss/rss.html", source: "CNBC", enabled: true },
];

const NEWS_FEEDS_KEY = "news_feeds";

export async function getNewsFeeds(): Promise<NewsFeed[]> {
  const stored = await getConfigJSON<NewsFeed[]>(NEWS_FEEDS_KEY, DEFAULT_NEWS_FEEDS);
  return stored.length > 0 ? stored : DEFAULT_NEWS_FEEDS;
}

export async function setNewsFeeds(feeds: NewsFeed[]): Promise<NewsFeed[]> {
  const clean = feeds.map((f) => ({ ...DEFAULT_NEWS_FEEDS.find((d) => d.id === f.id) ?? {}, ...f }));
  await setConfigJSON(NEWS_FEEDS_KEY, clean);
  return clean;
}

export async function toggleNewsFeed(id: string, enabled: boolean): Promise<NewsFeed[]> {
  const feeds = await getNewsFeeds();
  const next = feeds.map((f) => (f.id === id ? { ...f, enabled } : f));
  return setNewsFeeds(next);
}

// ─── App preferences (client-side, mirrored for reference) ─────────────

export interface AppPreferences {
  theme: "dark" | "light";
  defaultMarket: string;
  refreshMs: number;
}

export const DEFAULT_PREFERENCES: AppPreferences = {
  theme: "dark",
  defaultMarket: "US",
  refreshMs: 15000,
};

const PREFS_KEY = "app_preferences";

export async function getPreferences(): Promise<AppPreferences> {
  return getConfigJSON<AppPreferences>(PREFS_KEY, DEFAULT_PREFERENCES);
}

export async function setPreferences(prefs: Partial<AppPreferences>): Promise<AppPreferences> {
  const next = await getPreferences();
  const merged = { ...next, ...prefs };
  await setConfigJSON(PREFS_KEY, merged);
  return merged;
}

// ─── Integrations status (read-only, from env) ────────────────────────

export interface IntegrationStatus {
  llm: { provider: string; model: string; configured: boolean };
  finnhub: boolean;
  binance: boolean;
  coingecko: boolean;
  yahoo: boolean;
  auth: boolean;
  database: boolean;
}

export async function getIntegrationsStatus(): Promise<IntegrationStatus> {
  const llm = await getLLMConfig();
  return {
    llm: {
      provider: llm.provider,
      model: llm.model,
      configured: llm.provider !== "mock",
    },
    finnhub: Boolean(process.env.FINNHUB_API_KEY),
    binance: Boolean(process.env.BINANCE_API_KEY),
    coingecko: Boolean(process.env.COINGECKO_API_KEY),
    yahoo: process.env.YAHOO_FINANCE_ENABLED === "true",
    auth: Boolean(process.env.BETTER_AUTH_SECRET),
    database: true,
  };
}
