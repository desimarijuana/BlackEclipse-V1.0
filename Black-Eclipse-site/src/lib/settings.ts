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
  category?: string;
  region?: string;
  tier?: number;
  enabled: boolean;
}

export const DEFAULT_NEWS_FEEDS: NewsFeed[] = [
  // ─── Tier 1 — Wire & Regulators ───────────────────────────────────────
  { id: "sec-press", url: "https://www.sec.gov/news/pressreleases.rss", source: "SEC", category: "REGULATORY", region: "US", tier: 1, enabled: true },
  { id: "fed-press", url: "https://www.federalreserve.gov/feeds/press_all.xml", source: "Federal Reserve", category: "REGULATORY", region: "US", tier: 1, enabled: true },
  { id: "ecb-press", url: "https://www.ecb.europa.eu/rss/press.html", source: "ECB", category: "REGULATORY", region: "EU", tier: 1, enabled: true },
  { id: "boe-news", url: "https://www.bankofengland.co.uk/rss/news", source: "Bank of England", category: "REGULATORY", region: "UK", tier: 1, enabled: true },
  { id: "ap-top", url: "https://news.google.com/rss/search?q=site:apnews.com+OR+site:apnews.org&hl=en", source: "AP", category: "GEOPOLITICS", region: "GLOBAL", tier: 1, enabled: true },
  { id: "un-news", url: "https://news.un.org/feed/subscribe/en/news/all/rss.xml", source: "UN News", category: "GEOPOLITICS", region: "GLOBAL", tier: 1, enabled: true },
  // ─── Tier 2 — Major Financial Media ──────────────────────────────────
  { id: "bloomberg-mkts", url: "https://feeds.bloomberg.com/markets/news.rss", source: "Bloomberg", category: "MARKETS", region: "GLOBAL", tier: 2, enabled: true },
  { id: "wsj-markets", url: "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", source: "WSJ", category: "MARKETS", region: "US", tier: 2, enabled: true },
  { id: "wsj-world", url: "https://feeds.a.dj.com/rss/RSSWorldNews.xml", source: "WSJ", category: "GEOPOLITICS", region: "GLOBAL", tier: 2, enabled: true },
  { id: "marketwatch", url: "https://feeds.marketwatch.com/marketwatch/topstories/", source: "MarketWatch", category: "MARKETS", region: "US", tier: 2, enabled: true },
  { id: "cnbc-finance", url: "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", source: "CNBC", category: "MARKETS", region: "US", tier: 2, enabled: true },
  { id: "cnbc-world", url: "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362", source: "CNBC", category: "MARKETS", region: "GLOBAL", tier: 2, enabled: true },
  { id: "cnbc-tech", url: "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910", source: "CNBC", category: "TECH", region: "US", tier: 2, enabled: true },
  { id: "seekingalpha", url: "https://seekingalpha.com/market_currents.xml", source: "Seeking Alpha", category: "MARKETS", region: "US", tier: 2, enabled: true },
  { id: "investing-news", url: "https://www.investing.com/rss/news.rss", source: "Investing.com", category: "MARKETS", region: "GLOBAL", tier: 2, enabled: true },
  { id: "economist", url: "https://www.economist.com/finance-and-economics/rss.xml", source: "The Economist", category: "ECONOMIC", region: "GLOBAL", tier: 2, enabled: true },
  { id: "benzinga", url: "https://www.benzinga.com/feed", source: "Benzinga", category: "MARKETS", region: "US", tier: 2, enabled: true },
  { id: "fxstreet", url: "https://www.fxstreet.com/rss/news", source: "FXStreet", category: "MARKETS", region: "GLOBAL", tier: 2, enabled: true },
  // ─── Tier 2 — Global News ────────────────────────────────────────────
  { id: "bbc-world", url: "http://feeds.bbci.co.uk/news/world/rss.xml", source: "BBC", category: "GEOPOLITICS", region: "GLOBAL", tier: 2, enabled: true },
  { id: "bbc-business", url: "http://feeds.bbci.co.uk/news/business/rss.xml", source: "BBC", category: "MARKETS", region: "GLOBAL", tier: 2, enabled: true },
  { id: "aljazeera", url: "https://news.google.com/rss/search?q=site:aljazeera.com&hl=en", source: "Al Jazeera", category: "GEOPOLITICS", region: "GLOBAL", tier: 2, enabled: true },
  { id: "nyt-world", url: "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", source: "NYT", category: "GEOPOLITICS", region: "GLOBAL", tier: 2, enabled: true },
  { id: "guardian-world", url: "https://www.theguardian.com/world/rss", source: "The Guardian", category: "GEOPOLITICS", region: "GLOBAL", tier: 2, enabled: true },
  { id: "france24", url: "https://www.france24.com/en/rss", source: "France 24", category: "GEOPOLITICS", region: "EU", tier: 2, enabled: true },
  { id: "dw-world", url: "https://rss.dw.com/rdf/rss-en-all", source: "Deutsche Welle", category: "GEOPOLITICS", region: "EU", tier: 2, enabled: true },
  { id: "foreignpolicy", url: "https://news.google.com/rss/search?q=site:foreignpolicy.com&hl=en", source: "Foreign Policy", category: "GEOPOLITICS", region: "GLOBAL", tier: 2, enabled: true },
  // ─── Tier 2 — Energy, Commodities, Tech ──────────────────────────────
  { id: "oilprice", url: "https://news.google.com/rss/search?q=oil+prices+OR+crude+oil+markets&hl=en", source: "OilPrice.com", category: "ENERGY", region: "GLOBAL", tier: 2, enabled: true },
  { id: "mining-com", url: "https://news.google.com/rss/search?q=mining+OR+commodities+metals&hl=en", source: "Mining.com", category: "MARKETS", region: "GLOBAL", tier: 2, enabled: true },
  { id: "techcrunch", url: "https://techcrunch.com/feed/", source: "TechCrunch", category: "TECH", region: "GLOBAL", tier: 2, enabled: true },
  { id: "wired", url: "https://www.wired.com/feed/rss", source: "Wired", category: "TECH", region: "US", tier: 2, enabled: true },
  { id: "finextra", url: "https://www.finextra.com/rss/headlines.aspx", source: "Finextra", category: "TECH", region: "GLOBAL", tier: 2, enabled: true },
  // ─── Tier 2 — Asia, India, MENA ──────────────────────────────────────
  { id: "scmp", url: "https://www.scmp.com/rss/91/feed", source: "SCMP", category: "GEOPOLITICS", region: "ASIA", tier: 2, enabled: true },
  { id: "nikkei-asia", url: "https://news.google.com/rss/search?q=site:asia.nikkei.com&hl=en", source: "Nikkei Asia", category: "MARKETS", region: "ASIA", tier: 2, enabled: true },
  { id: "hindu-biz", url: "https://news.google.com/rss/search?q=site:thehindu.com+business&hl=en", source: "The Hindu", category: "MARKETS", region: "INDIA", tier: 2, enabled: true },
  { id: "livemint", url: "https://news.google.com/rss/search?q=site:livemint.com+markets&hl=en", source: "LiveMint", category: "MARKETS", region: "INDIA", tier: 2, enabled: true },
  { id: "et-markets", url: "https://news.google.com/rss/search?q=site:economictimes.indiatimes.com+markets&hl=en", source: "Economic Times", category: "MARKETS", region: "INDIA", tier: 2, enabled: true },
  { id: "moneycontrol", url: "https://news.google.com/rss/search?q=site:moneycontrol.com&hl=en", source: "MoneyControl", category: "MARKETS", region: "INDIA", tier: 2, enabled: true },
  { id: "channel-news-asia", url: "https://www.channelnewsasia.com/rssfeeds/8395986", source: "CNA", category: "MARKETS", region: "ASIA", tier: 2, enabled: true },
  { id: "middle-east-eye", url: "https://news.google.com/rss/search?q=site:middleeasteye.net&hl=en", source: "Middle East Eye", category: "GEOPOLITICS", region: "MENA", tier: 2, enabled: true },
  // ─── Tier 2 — Crypto ─────────────────────────────────────────────────
  { id: "coindesk", url: "https://www.coindesk.com/arc/outboundfeeds/rss/", source: "CoinDesk", category: "CRYPTO", region: "GLOBAL", tier: 2, enabled: true },
  { id: "cointelegraph", url: "https://cointelegraph.com/rss", source: "CoinTelegraph", category: "CRYPTO", region: "GLOBAL", tier: 2, enabled: true },
  { id: "theblock", url: "https://www.theblock.co/rss.xml", source: "The Block", category: "CRYPTO", region: "GLOBAL", tier: 2, enabled: true },
  { id: "decrypt", url: "https://decrypt.co/feed", source: "Decrypt", category: "CRYPTO", region: "GLOBAL", tier: 2, enabled: true },
  // ─── Tier 3 — Economic / Macro / Defense / Tech / ESG ────────────────
  { id: "zero-hedge", url: "https://feeds.feedburner.com/zerohedge/feed", source: "ZeroHedge", category: "ECONOMIC", region: "GLOBAL", tier: 3, enabled: true },
  { id: "calculated-risk", url: "https://feeds.feedburner.com/CalculatedRisk", source: "Calculated Risk", category: "ECONOMIC", region: "US", tier: 3, enabled: true },
  { id: "wolfstreet", url: "https://wolfstreet.com/feed/", source: "Wolf Street", category: "ECONOMIC", region: "US", tier: 3, enabled: true },
  { id: "bellingcat", url: "https://www.bellingcat.com/feed/", source: "Bellingcat", category: "GEOPOLITICS", region: "GLOBAL", tier: 3, enabled: true },
  { id: "arstechnica", url: "https://feeds.arstechnica.com/arstechnica/index", source: "Ars Technica", category: "TECH", region: "GLOBAL", tier: 3, enabled: true },
  { id: "theverge", url: "https://news.google.com/rss/search?q=site:theverge.com&hl=en", source: "The Verge", category: "TECH", region: "GLOBAL", tier: 3, enabled: true },
  { id: "mit-tech", url: "https://www.technologyreview.com/feed/", source: "MIT Tech Review", category: "TECH", region: "GLOBAL", tier: 3, enabled: true },
  { id: "carbon-brief", url: "https://www.carbonbrief.org/feed/", source: "Carbon Brief", category: "ENERGY", region: "GLOBAL", tier: 3, enabled: true },
  // ─── Tier 2 — New topic categories (Google News search feeds) ─────────
  { id: "gn-inflation", url: "https://news.google.com/rss/search?q=inflation+CPI+OR+inflation+rate&hl=en", source: "Google News", category: "INFLATION", region: "GLOBAL", tier: 2, enabled: true },
  { id: "gn-jobs", url: "https://news.google.com/rss/search?q=jobs+report+OR+unemployment+OR+payrolls&hl=en", source: "Google News", category: "JOBS", region: "GLOBAL", tier: 2, enabled: true },
  { id: "gn-central-banks", url: "https://news.google.com/rss/search?q=federal+reserve+OR+interest+rate+decision+OR+central+bank&hl=en", source: "Google News", category: "CENTRAL BANKS", region: "GLOBAL", tier: 2, enabled: true },
  { id: "gn-trade", url: "https://news.google.com/rss/search?q=tariffs+OR+trade+war+OR+trade+deal&hl=en", source: "Google News", category: "TRADE", region: "GLOBAL", tier: 2, enabled: true },
  { id: "gn-war", url: "https://news.google.com/rss/search?q=war+OR+conflict+OR+military+operation&hl=en", source: "Google News", category: "WAR", region: "GLOBAL", tier: 2, enabled: true },
  { id: "gn-politics", url: "https://news.google.com/rss/search?q=politics+OR+election+OR+government&hl=en", source: "Google News", category: "POLITICS", region: "GLOBAL", tier: 2, enabled: true },
  { id: "gn-defense", url: "https://news.google.com/rss/search?q=defense+OR+defence+spending+OR+military+contracts&hl=en", source: "Google News", category: "DEFENSE", region: "GLOBAL", tier: 2, enabled: true },
  { id: "gn-ai", url: "https://news.google.com/rss/search?q=artificial+intelligence+OR+AI+OR+machine+learning&hl=en", source: "Google News", category: "AI", region: "GLOBAL", tier: 2, enabled: true },
  { id: "gn-healthcare", url: "https://news.google.com/rss/search?q=healthcare+OR+pharma+OR+biotech&hl=en", source: "Google News", category: "HEALTHCARE", region: "GLOBAL", tier: 2, enabled: true },
  { id: "gn-auto", url: "https://news.google.com/rss/search?q=electric+vehicles+OR+automakers+OR+EV+sales&hl=en", source: "Google News", category: "AUTO", region: "GLOBAL", tier: 2, enabled: true },
  { id: "gn-climate", url: "https://news.google.com/rss/search?q=climate+change+OR+renewable+energy+OR+emissions&hl=en", source: "Google News", category: "CLIMATE", region: "GLOBAL", tier: 2, enabled: true },
  { id: "gn-commodities", url: "https://news.google.com/rss/search?q=commodities+OR+gold+prices+OR+oil+prices&hl=en", source: "Google News", category: "COMMODITIES", region: "GLOBAL", tier: 2, enabled: true },
  { id: "gn-bonds", url: "https://news.google.com/rss/search?q=bond+market+OR+treasury+yields+OR+bonds&hl=en", source: "Google News", category: "BONDS", region: "GLOBAL", tier: 2, enabled: true },
  { id: "gn-forex", url: "https://news.google.com/rss/search?q=forex+OR+currency+OR+exchange+rate&hl=en", source: "Google News", category: "FOREX", region: "GLOBAL", tier: 2, enabled: true },
  { id: "gn-stocks", url: "https://news.google.com/rss/search?q=stock+market+OR+shares+OR+equities&hl=en", source: "Google News", category: "STOCKS", region: "GLOBAL", tier: 2, enabled: true },
  // ─── Tier 4 — Blogs & Aggregators ────────────────────────────────────
  { id: "hackernews", url: "https://hnrss.org/frontpage", source: "Hacker News", category: "TECH", region: "GLOBAL", tier: 4, enabled: true },
  { id: "abnormal-returns", url: "https://news.google.com/rss/search?q=site:abnormalreturns.com&hl=en", source: "Abnormal Returns", category: "MARKETS", region: "US", tier: 4, enabled: true },
  { id: "marginal-rev", url: "https://marginalrevolution.com/feed", source: "Marginal Revolution", category: "ECONOMIC", region: "GLOBAL", tier: 4, enabled: true },
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
  // Only integrations that are actually WIRED at runtime are reported here.
  // Keys that exist in .env but have zero runtime usage (FINNHUB, SUPABASE,
  // BINANCE_API_KEY, COINGECKO, BETTER_AUTH) are deliberately omitted —
  // reporting them "connected" was a lie.
  yahoo: boolean;
  // Economics sources — truthful key status (never report connected without a key).
  fred: boolean;
  bea: boolean;
  bls: boolean;
  tradingEconomics: boolean;
  akshare: boolean;
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
    yahoo: process.env.YAHOO_FINANCE_ENABLED === "true",
    fred: Boolean(process.env.FRED_API_KEY),
    bea: Boolean(process.env.BEA_API_KEY),
    bls: Boolean(process.env.BLS_API_KEY),
    tradingEconomics: Boolean(process.env.TRADING_ECONOMICS_API_KEY),
    akshare: Boolean(process.env.AKSHARE_API_KEY),
    database: true,
  };
}
