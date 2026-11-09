// ─── Settings / Configuration vault ────────────────────────────────────
// Central place for user-configurable settings, persisted in JDDS
// (SystemConfig key/value table) with sensible env-var fallbacks.
//
// Every setting here is surfaced on the Settings screen so the user can
// control the entire site from one place — LLM provider, market data,
// news feeds, app preferences, and data hygiene.

import { prisma } from "@/lib/db";
import { isLocalBaseUrl, presetForBaseUrl, CATALOG_ENV_VARS } from "@/lib/agent/presets";
import { assertModelAllowed } from "@/lib/privacy";
import { storedProviderKey } from "@/lib/provider-keys";

/**
 * The env var that holds the key for a given LLM base URL, when it matches a
 * known preset. Used so a key pasted in the provider-key vault is honoured by
 * the LLM runtime without re-entering it in the LLM config.
 */
function llmKeyEnvVar(baseUrl: string): string | undefined {
  return presetForBaseUrl(baseUrl)?.envVar;
}

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

/** Remove a config row entirely (used by the setup reset scopes). */
export async function deleteConfig(key: string): Promise<void> {
  try {
    await prisma.systemConfig.delete({ where: { key } });
  } catch {
    // Absent row = already clean; reset is idempotent.
  }
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

// `openai` is the default OpenAI-compatible family: any preset (Groq, Mistral,
// DeepSeek, OpenRouter, …) is stored as its own preset id plus its baseUrl/model,
// matching the Python runtime's `PROVIDER_CATALOG` ids so provider-specific
// construction (Anthropic, Google, Mistral, Groq) is honoured. `auto` resolves
// from the environment; `mock` is the offline stub.
export type LLMProviderName =
  | "auto" | "mock"
  | "openai" | "anthropic" | "google" | "mistral" | "groq"
  | "ollama" | "lmstudio" | "deepseek" | "xai" | "openrouter" | "opencode"
  | "together" | "perplexity" | "fireworks" | "custom";

export interface LLMConfig {
  provider: LLMProviderName;
  baseUrl: string;
  apiKey: string;
  model: string;
  /**
   * Optional operator-declared context window (tokens) for the selected model.
   * Used ONLY when the runtime catalog cannot resolve one (a local server, a
   * router, a custom endpoint). Empty/undefined leaves the window unknown and
   * the conservative ceiling applies — it is never fabricated.
   */
  contextWindow?: number;
  /**
   * Optional reasoning-effort override ("model variant"). Sent to the runtime as
   * the `reasoning` routing requirement + applied to native reasoning controls.
   * One of `low`/`medium`/`high`/`very_high`; absent means the runtime's task
   * profile decides. Only meaningful for models that declare reasoning support —
   * an OpenAI-compatible endpoint without one is never force-fed the knob.
   */
  reasoningEffort?: "low" | "medium" | "high" | "very_high";
  /**
   * Optional coding model. When set, a build run (a chat code turn or a Code
   * task) uses this model on the SAME provider/key/URL. A profile, not a second
   * provider: it is the "best for building" knob.
   */
  codingModel?: string;
  /**
   * Optional model-routing preference (spec §44). Sent to the runtime as
   * `input.context.modelPolicy`, where it outranks the automatic router. Absent
   * means normal routing. Every field is opt-in and additive.
   */
  routingPolicy?: {
    /** Restrict to local models only ("Use local models only"). */
    localOnly?: boolean;
    /** Prefer models that cost nothing ("Don't use paid models"). */
    preferFree?: boolean;
    /** Restrict to these provider ids. */
    allowedProviders?: string[];
    /** Never use these provider ids. */
    deniedProviders?: string[];
  };
}

export const DEFAULT_LLM_CONFIG: LLMConfig = {
  provider: "auto",
  baseUrl: "https://api.openai.com/v1",
  apiKey: "",
  model: "gpt-4o-mini",
};

/**
 * The placeholder stored for a keyless local endpoint (some OpenAI-compatible
 * clients require a non-empty key string). It is NOT a credential and is never
 * sent to a remote provider — see `getLLMConfig`/`setLLMConfig`.
 */
export const LOCAL_KEY_SENTINEL = "local";

const LLM_KEY = "llm_config";

// Raw LLM config = DB overrides on top of env defaults, WITHOUT the vault
// fallback. Used for persistence so a vault-owned key is never copied into the
// plaintext llm_config row.
async function readLLMConfigRaw(): Promise<LLMConfig> {
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

/**
 * Effective LLM config for RUNTIME use: the raw config, plus a vault fallback
 * for the key. When the LLM config has no key of its own, the provider-key
 * vault entry for the matching preset is used — so a key entered once (in the
 * AI provider list) powers the runtime with no second key field to sync.
 *
 * The `"local"` sentinel is NOT a real credential: it is a placeholder some
 * clients require for keyless local servers. It must never shadow a vault/env
 * key once the endpoint is remote, otherwise switching from Ollama to a hosted
 * provider would send `"local"` and fail with 401 (the "can't add my API key"
 * bug).
 */
export async function getLLMConfig(): Promise<LLMConfig> {
  const cfg = await readLLMConfigRaw();
  const hasRealKey = Boolean(cfg.apiKey) && cfg.apiKey !== LOCAL_KEY_SENTINEL;
  if (hasRealKey) return cfg;
  const envVar = llmKeyEnvVar(cfg.baseUrl);
  if (!envVar) return { ...cfg, apiKey: isLocalBaseUrl(cfg.baseUrl) ? LOCAL_KEY_SENTINEL : cfg.apiKey };
  const apiKey = process.env[envVar] || (await storedProviderKey(envVar)) || "";
  return { ...cfg, apiKey };
}

export async function setLLMConfig(
  config: Omit<Partial<LLMConfig>, "contextWindow" | "reasoningEffort"> & {
    contextWindow?: number | null;
    reasoningEffort?: LLMConfig["reasoningEffort"] | null;
    codingModel?: string | null;
  },
): Promise<LLMConfig> {
  // Merge over the RAW config so persisting never folds a vault key into the
  // plaintext row; only values the caller actually sends change.
  const next = await readLLMConfigRaw();
  const merged: LLMConfig = {
    ...next,
    ...(config as Partial<LLMConfig>),
  };
  // An explicit `null` clears the declared window (a plain `undefined` cannot —
  // JSON.stringify drops it, so the merge would silently keep the old value).
  if (config.contextWindow === null) delete merged.contextWindow;
  // An explicit `null` clears the reasoning-effort override back to Auto.
  if ((config as { reasoningEffort?: unknown }).reasoningEffort === null) {
    delete merged.reasoningEffort;
  }
  // An explicit `null` clears the routing preference similarly.
  if ((config as { routingPolicy?: unknown }).routingPolicy === null) delete merged.routingPolicy;
  // An explicit `null` clears the coding model back to the chat model.
  if (config.codingModel === null) delete merged.codingModel;

  // A `"local"` sentinel is never a real key; drop it here so it cannot survive
  // a switch to a remote endpoint and be sent as the credential.
  if (merged.apiKey === LOCAL_KEY_SENTINEL) merged.apiKey = "";

  // Fail closed before persisting a provider that local-only mode forbids.
  assertModelAllowed(merged.baseUrl, merged.provider);

  if (merged.provider !== "mock" && !merged.apiKey && !isLocalBaseUrl(merged.baseUrl)) {
    // The key may legitimately live in the provider-key vault or the environment
    // (the single key home for a preset). Only refuse when neither holds one.
    const envVar = llmKeyEnvVar(merged.baseUrl);
    const vaultKey = envVar ? process.env[envVar] || (await storedProviderKey(envVar)) : "";
    if (!vaultKey) {
      throw new Error("An API key is required for a remote LLM provider");
    }
  }
  if (merged.provider !== "mock" && !merged.apiKey && isLocalBaseUrl(merged.baseUrl)) {
    // Local servers ignore the key but some clients require a non-empty string.
    merged.apiKey = LOCAL_KEY_SENTINEL;
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
  // ─── Tier 2 — Conflict watch (Investor Eye) ──────────────────────────
  // Dedicated conflict wires. The general GEOPOLITICS feeds carry conflict
  // stories mixed with diplomacy and trade; these are scoped to active conflict
  // so the Investor Eye "Conflict" lens is dense and current rather than relying
  // on GDELT's CAMEO coding alone.
  { id: "gn-conflict-now", url: "https://news.google.com/rss/search?q=(airstrike+OR+shelling+OR+offensive+OR+ceasefire+OR+militants)+when:2d&hl=en", source: "Google News", category: "WAR", region: "GLOBAL", tier: 1, enabled: true },
  { id: "gn-conflict-mideast", url: "https://news.google.com/rss/search?q=(Gaza+OR+Lebanon+OR+Red+Sea+OR+Yemen+OR+Syria+OR+Iran)+conflict+when:3d&hl=en", source: "Google News", category: "WAR", region: "MENA", tier: 1, enabled: true },
  { id: "gn-conflict-ukraine", url: "https://news.google.com/rss/search?q=(Ukraine+OR+Russia)+strike+OR+front+line+OR+drone+when:3d&hl=en", source: "Google News", category: "WAR", region: "EU", tier: 1, enabled: true },
  { id: "gn-conflict-shipping", url: "https://news.google.com/rss/search?q=(shipping+OR+tanker+OR+port+OR+strait)+attack+OR+blockade+OR+disruption+when:3d&hl=en", source: "Google News", category: "WAR", region: "GLOBAL", tier: 1, enabled: true },
  { id: "gn-conflict-coup", url: "https://news.google.com/rss/search?q=(coup+OR+martial+law+OR+unrest+OR+armed+group)+when:3d&hl=en", source: "Google News", category: "WAR", region: "GLOBAL", tier: 1, enabled: true },
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
  /**
   * IANA timezone for displaying timestamps (e.g. 'UTC', 'Europe/London',
   * 'Asia/Karachi'). Empty/absent means "follow the browser". Every formatted
   * time prints its zone, so the value is never ambiguous.
   */
  timeZone?: string;
}

export const DEFAULT_PREFERENCES: AppPreferences = {
  theme: "dark",
  defaultMarket: "US",
  refreshMs: 15000,
  timeZone: "UTC",
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
  /**
   * Raw "is this env var set" map for every provider key the catalog advertises.
   * The UI uses it to show honest per-provider status without hard-coding a
   * second list that would drift.
   */
  envFlags: Record<string, boolean>;
}

export async function getIntegrationsStatus(): Promise<IntegrationStatus> {
  const llm = await getLLMConfig();
  const envFlags: Record<string, boolean> = {};
  for (const key of CATALOG_ENV_VARS) envFlags[key] = Boolean(process.env[key]);
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
    envFlags,
  };
}
