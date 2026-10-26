// ── Provider API-key vault ───────────────────────────────────────────────────
// A single, honest registry of every credential BlackEclipse can accept, plus
// encrypted at-rest storage for the ones an operator pastes in the UI.
//
// WHY A VAULT AND NOT JUST `process.env`:
// Environment variables are the right mechanism for a deployment, but they are
// useless to someone running a zero-config local install — they would have to
// edit a file and restart. This lets the same key be entered in Settings,
// stored encrypted in JDDS, and used immediately, while keeping the env var as
// the authoritative override (a real deployment's env always wins).
//
// HONESTY RULES (these are the whole point of the module):
//   1. A stored key is never returned to the browser — only `hasKey: boolean`.
//   2. "Configured" is derived from the real resolution order, never guessed.
//   3. A key that is stored but not yet applied on this process is reported as
//      stored-but-inactive, not as working.
//   4. Encryption is the existing AES-256-GCM path (`connectors/secrets`); keys
//      are never written to `SystemConfig` in plaintext.
//
// `applyStoredKeysToEnv()` copies stored keys into `process.env` (without
// clobbering real env vars) so every existing consumer — which reads
// `process.env` directly — keeps working with no per-provider change.

import { prisma } from '@/lib/db';
import { encryptSecret, decryptSecret, isEncryptedPayload } from '@/lib/connectors/secrets';

/** Where the encrypted key values live in `SystemConfig`. */
export const PROVIDER_KEYS_CONFIG_KEY = 'provider_keys_v1';

export type KeyCategory = 'ai' | 'market' | 'crypto' | 'economics';

export interface ProviderKeyDef {
  /** The env var this key maps to. This is the identity. */
  envVar: string;
  label: string;
  provider: string;
  category: KeyCategory;
  /** What the key unlocks, shown under the field. */
  description: string;
  /** Where to obtain it. */
  docsUrl?: string;
  /** True when the value is not secret (e.g. a base URL). */
  publicValue?: boolean;
  /**
   * A real endpoint used by "Test". Only declared where a cheap, safe request
   * exists; a provider without one shows no test button rather than a fake
   * success.
   */
  test?: {
    url: string;
    /** How the key is presented to that endpoint. */
    auth: { kind: 'header'; name: string; prefix?: string } | { kind: 'query'; name: string };
  };
}

export const CATEGORY_LABELS: Record<KeyCategory, string> = {
  ai: 'AI & LLM',
  market: 'Market Data',
  crypto: 'Crypto',
  economics: 'Economics & Macro',
};

/**
 * Every credential the app can consume. Kept in one list so the vault, the
 * catalog and `/api/settings` cannot disagree about what a key means.
 */
export const PROVIDER_KEYS: ProviderKeyDef[] = [
  // ── AI & LLM ──────────────────────────────────────────────────────────────
  { envVar: 'OPENAI_API_KEY', label: 'OpenAI', provider: 'OpenAI', category: 'ai', description: 'Powers chat, research and the Investor Eye analyst.', docsUrl: 'https://platform.openai.com/api-keys',
    test: { url: 'https://api.openai.com/v1/models', auth: { kind: 'header', name: 'authorization', prefix: 'Bearer ' } } },
  { envVar: 'ANTHROPIC_API_KEY', label: 'Anthropic', provider: 'Anthropic', category: 'ai', description: 'Claude models for the AI agent.', docsUrl: 'https://console.anthropic.com/settings/keys',
    test: { url: 'https://api.anthropic.com/v1/models', auth: { kind: 'header', name: 'x-api-key' } } },
  { envVar: 'OLLAMA_BASE_URL', label: 'Ollama base URL', provider: 'Ollama', category: 'ai', description: 'Local models. No key — the base URL, e.g. http://localhost:11434/v1.', docsUrl: 'https://ollama.com/download', publicValue: true },
  { envVar: 'GROQ_API_KEY', label: 'Groq', provider: 'Groq', category: 'ai', description: 'Fast OpenAI-compatible inference.', docsUrl: 'https://console.groq.com/keys',
    test: { url: 'https://api.groq.com/openai/v1/models', auth: { kind: 'header', name: 'authorization', prefix: 'Bearer ' } } },
  { envVar: 'DEEPSEEK_API_KEY', label: 'DeepSeek', provider: 'DeepSeek', category: 'ai', description: 'OpenAI-compatible endpoint.', docsUrl: 'https://platform.deepseek.com/api_keys',
    test: { url: 'https://api.deepseek.com/models', auth: { kind: 'header', name: 'authorization', prefix: 'Bearer ' } } },
  { envVar: 'MISTRAL_API_KEY', label: 'Mistral', provider: 'Mistral AI', category: 'ai', description: 'OpenAI-compatible endpoint.', docsUrl: 'https://console.mistral.ai/api-keys/',
    test: { url: 'https://api.mistral.ai/v1/models', auth: { kind: 'header', name: 'authorization', prefix: 'Bearer ' } } },
  { envVar: 'GEMINI_API_KEY', label: 'Google Gemini', provider: 'Google', category: 'ai', description: 'Gemini models.', docsUrl: 'https://aistudio.google.com/app/apikey' },
  { envVar: 'XAI_API_KEY', label: 'xAI Grok', provider: 'xAI', category: 'ai', description: 'Grok models.', docsUrl: 'https://console.x.ai/',
    test: { url: 'https://api.x.ai/v1/models', auth: { kind: 'header', name: 'authorization', prefix: 'Bearer ' } } },
  { envVar: 'OPENROUTER_API_KEY', label: 'OpenRouter', provider: 'OpenRouter', category: 'ai', description: 'Router across many models.', docsUrl: 'https://openrouter.ai/keys',
    test: { url: 'https://openrouter.ai/api/v1/models', auth: { kind: 'header', name: 'authorization', prefix: 'Bearer ' } } },
  { envVar: 'OPENCODE_API_KEY', label: 'OpenCode Zen', provider: 'OpenCode', category: 'ai', description: 'OpenCode Console gateway: curated coding models on one key.', docsUrl: 'https://opencode.ai/console',
    test: { url: 'https://opencode.ai/inference/v1/models', auth: { kind: 'header', name: 'authorization', prefix: 'Bearer ' } } },
  { envVar: 'TOGETHER_API_KEY', label: 'Together AI', provider: 'Together', category: 'ai', description: 'Open-model inference.', docsUrl: 'https://api.together.xyz/settings/api-keys',
    test: { url: 'https://api.together.xyz/v1/models', auth: { kind: 'header', name: 'authorization', prefix: 'Bearer ' } } },
  { envVar: 'PERPLEXITY_API_KEY', label: 'Perplexity', provider: 'Perplexity', category: 'ai', description: 'Search-augmented models.', docsUrl: 'https://www.perplexity.ai/settings/api',
    test: { url: 'https://api.perplexity.ai/models', auth: { kind: 'header', name: 'authorization', prefix: 'Bearer ' } } },
  { envVar: 'FIREWORKS_API_KEY', label: 'Fireworks AI', provider: 'Fireworks', category: 'ai', description: 'Open-model inference.', docsUrl: 'https://fireworks.ai/account/api-keys',
    test: { url: 'https://api.fireworks.ai/inference/v1/models', auth: { kind: 'header', name: 'authorization', prefix: 'Bearer ' } } },

  // ── Market Data ───────────────────────────────────────────────────────────
  { envVar: 'FINNHUB_API_KEY', label: 'Finnhub', provider: 'Finnhub', category: 'market', description: 'Real-time quotes, fundamentals and news.', docsUrl: 'https://finnhub.io/dashboard',
    test: { url: 'https://finnhub.io/api/v1/quote?symbol=AAPL', auth: { kind: 'query', name: 'token' } } },
  { envVar: 'POLYGON_API_KEY', label: 'Polygon.io', provider: 'Polygon', category: 'market', description: 'US equities, FX and aggregates.', docsUrl: 'https://polygon.io/dashboard/api-keys',
    test: { url: 'https://api.polygon.io/v2/aggs/ticker/AAPL/prev', auth: { kind: 'query', name: 'apiKey' } } },
  { envVar: 'ALPHAVANTAGE_API_KEY', label: 'Alpha Vantage', provider: 'Alpha Vantage', category: 'market', description: 'Equities, FX and technical series.', docsUrl: 'https://www.alphavantage.co/support/#api-key',
    test: { url: 'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=AAPL', auth: { kind: 'query', name: 'apikey' } } },
  { envVar: 'TWELVE_DATA_API_KEY', label: 'Twelve Data', provider: 'Twelve Data', category: 'market', description: 'Equities, FX, crypto and indices.', docsUrl: 'https://twelvedata.com/account/api-keys',
    test: { url: 'https://api.twelvedata.com/price?symbol=AAPL', auth: { kind: 'query', name: 'apikey' } } },
  { envVar: 'MARKETSTACK_API_KEY', label: 'Marketstack', provider: 'Marketstack', category: 'market', description: 'End-of-day and intraday prices.', docsUrl: 'https://marketstack.com/dashboard',
    test: { url: 'https://api.marketstack.com/v1/tickers', auth: { kind: 'query', name: 'access_key' } } },
  { envVar: 'FINANCIALMODELINGPREP_API_KEY', label: 'Financial Modeling Prep', provider: 'Financial Modeling Prep', category: 'market', description: 'Normalized fundamentals, ratios and analyst estimates for the Fundamentals page.', docsUrl: 'https://site.financialmodelingprep.com/developer/docs',
    test: { url: 'https://financialmodelingprep.com/api/v3/quote/AAPL', auth: { kind: 'query', name: 'apikey' } } },
  // ── Research web search (operator-configurable second provider) ────────────
  // The keyless DuckDuckGo HTML provider is always present; these two entries let
  // an operator add ANY JSON search API as an independent second route without a
  // code change. The config is public (a URL + field mapping); the key is secret.
  { envVar: 'SEARCH_API_CONFIG', label: 'Custom search API config', provider: 'Web Search', category: 'market', publicValue: true,
    description:
      'JSON config for an additional web-search provider used by research. Shape: {"url":"https://api.example.com/search?q={query}&count={limit}","authKind":"query|bearer|header","authParam":"key","resultsPath":"results","titlePath":"title","urlPath":"link","snippetPath":"snippet"}. Absent → only the keyless default search is used.' },
  { envVar: 'SEARCH_API_KEY', label: 'Custom search API key', provider: 'Web Search', category: 'market', docsUrl: 'https://duckduckgo.com/',
    description: 'Secret for the advanced search-API config above. Sent per its authKind (query/bearer/header). Not needed for keyless endpoints.' },

  // ── Research search providers (add ONE key to enable a dependable engine) ──
  // Each named provider has its own vault key, so a user can add/remove it in
  // Settings with no JSON. The first configured one is preferred over the keyless
  // HTML chain; `SEARCH_API_CONFIG` (advanced) still overrides when set.
  { envVar: 'TAVILY_API_KEY', label: 'Tavily', provider: 'Web Search', category: 'market', docsUrl: 'https://tavily.com',
    description: 'Dependable search API for research. Add this key to prefer Tavily over the keyless chain.' },
  { envVar: 'BRAVE_API_KEY', label: 'Brave Search', provider: 'Web Search', category: 'market', docsUrl: 'https://brave.com/search/api/',
    description: 'Independent web index. Add this key to prefer Brave over the keyless chain.' },
  { envVar: 'EXA_API_KEY', label: 'Exa', provider: 'Web Search', category: 'market', docsUrl: 'https://exa.ai',
    description: 'Semantic/embeddings web search. Add this key to prefer Exa over the keyless chain.' },
  { envVar: 'SERPER_API_KEY', label: 'Serper (Google)', provider: 'Web Search', category: 'market', docsUrl: 'https://serper.dev',
    description: 'Google-shaped results via serper.dev. Add this key to prefer Serper over the keyless chain.' },
  { envVar: 'SERPAPI_API_KEY', label: 'SerpApi', provider: 'Web Search', category: 'market', docsUrl: 'https://serpapi.com',
    description: 'Multi-engine search API. Add this key to prefer SerpApi over the keyless chain.' },
  { envVar: 'BING_SEARCH_API_KEY', label: 'Bing Web Search (Azure)', provider: 'Web Search', category: 'market', docsUrl: 'https://www.microsoft.com/en-us/bing/apis/bing-web-search-api',
    description: 'Azure Bing Web Search. Add this key to prefer Bing over the keyless chain.' },
  { envVar: 'GOOGLE_CSE_API_KEY', label: 'Google Custom Search', provider: 'Web Search', category: 'market', docsUrl: 'https://developers.google.com/custom-search/v1/overview',
    description: 'Google Custom Search JSON API key (pair with a `cx` via the advanced config).' },
  { envVar: 'SEARXNG_URL', label: 'SearXNG base URL', provider: 'Web Search', category: 'market', publicValue: true, docsUrl: 'https://docs.searxng.org',
    description: 'Base URL of a self-hosted SearXNG instance, e.g. https://searx.example. Keyless.' },

  // ── Crypto ────────────────────────────────────────────────────────────────
  { envVar: 'COINGECKO_API_KEY', label: 'CoinGecko', provider: 'CoinGecko', category: 'crypto', description: 'Higher rate limits for crypto market data.', docsUrl: 'https://www.coingecko.com/en/developers/dashboard',
    test: { url: 'https://api.coingecko.com/api/v3/ping', auth: { kind: 'header', name: 'x-cg-demo-api-key' } } },
  { envVar: 'COINMARKETCAP_API_KEY', label: 'CoinMarketCap', provider: 'CoinMarketCap', category: 'crypto', description: 'Crypto listings and quotes.', docsUrl: 'https://pro.coinmarketcap.com/account',
    test: { url: 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest?limit=1', auth: { kind: 'header', name: 'X-CMC_PRO_API_KEY' } } },

  // ── Economics & Macro ─────────────────────────────────────────────────────
  { envVar: 'FRED_API_KEY', label: 'FRED', provider: 'St. Louis Fed', category: 'economics', description: 'Full macro series access (public CSV works without a key).', docsUrl: 'https://fredaccount.stlouisfed.org/apikeys',
    test: { url: 'https://api.stlouisfed.org/fred/series?series_id=GDP&file_type=json', auth: { kind: 'query', name: 'api_key' } } },
  { envVar: 'BEA_API_KEY', label: 'BEA', provider: 'U.S. Bureau of Economic Analysis', category: 'economics', description: 'GDP and national accounts.', docsUrl: 'https://apps.bea.gov/api/signup/' },
  { envVar: 'BLS_API_KEY', label: 'BLS', provider: 'U.S. Bureau of Labor Statistics', category: 'economics', description: 'Employment and inflation releases.', docsUrl: 'https://data.bls.gov/registrationEngine/' },
  { envVar: 'TRADING_ECONOMICS_API_KEY', label: 'Trading Economics', provider: 'Trading Economics', category: 'economics', description: 'Global macro indicators and calendars.', docsUrl: 'https://tradingeconomics.com/api/' },
  { envVar: 'AKSHARE_API_KEY', label: 'AKShare', provider: 'AKShare', category: 'economics', description: 'China market and macro data.', docsUrl: 'https://akshare.akfamily.xyz/' },
];

const BY_ENV = new Map(PROVIDER_KEYS.map((d) => [d.envVar, d]));

export function providerKeyDef(envVar: string): ProviderKeyDef | undefined {
  return BY_ENV.get(envVar);
}

/**
 * Which env vars THIS process populated from the vault.
 *
 * This is the memory that makes "remove" safe: only variables we ourselves set
 * may be cleared. A real deployment env var is never in this set, so removing a
 * stored key can never destroy it.
 */
const vaultApplied = new Set<string>();

/** Test seam. */
export function resetVaultApplied(): void {
  vaultApplied.clear();
}

// ── Encrypted storage ────────────────────────────────────────────────────────

interface VaultRecord {
  /** envVar → encrypted payload. */
  keys: Record<string, string>;
  updatedAt: string;
}

async function readVault(): Promise<VaultRecord> {
  try {
    const row = await prisma.systemConfig.findUnique({ where: { key: PROVIDER_KEYS_CONFIG_KEY } });
    if (!row?.value) return { keys: {}, updatedAt: new Date(0).toISOString() };
    const parsed = JSON.parse(row.value) as Partial<VaultRecord>;
    return { keys: parsed.keys ?? {}, updatedAt: parsed.updatedAt ?? new Date(0).toISOString() };
  } catch {
    return { keys: {}, updatedAt: new Date(0).toISOString() };
  }
}

async function writeVault(record: VaultRecord): Promise<void> {
  const value = JSON.stringify(record);
  await prisma.systemConfig.upsert({
    where: { key: PROVIDER_KEYS_CONFIG_KEY },
    update: { value },
    create: { key: PROVIDER_KEYS_CONFIG_KEY, value },
  });
}

/** Persist a key (encrypted). An empty value removes it. */
export async function saveProviderKey(envVar: string, plaintext: string): Promise<void> {
  if (!BY_ENV.has(envVar)) throw new Error(`Unknown provider key: ${envVar}`);
  const vault = await readVault();
  const trimmed = plaintext.trim();
  if (!trimmed) delete vault.keys[envVar];
  else vault.keys[envVar] = encryptSecret(trimmed);
  vault.updatedAt = new Date().toISOString();
  await writeVault(vault);
  applyStoredKeysToEnv();
}

export async function deleteProviderKey(envVar: string): Promise<void> {
  const vault = await readVault();
  if (!(envVar in vault.keys)) return;
  delete vault.keys[envVar];
  vault.updatedAt = new Date().toISOString();
  await writeVault(vault);
  // Only clear the process variable if THIS process put it there from the vault.
  // A real deployment env var must never be destroyed by removing a stored key.
  if (vaultApplied.has(envVar)) {
    delete process.env[envVar];
    vaultApplied.delete(envVar);
  }
  applyStoredKeysToEnv();
}

/** Decrypt one stored key, or null when none is stored / it fails to decrypt. */
export async function storedProviderKey(envVar: string): Promise<string | null> {
  const vault = await readVault();
  const payload = vault.keys[envVar];
  if (!payload) return null;
  if (!isEncryptedPayload(payload)) return null;
  try {
    return decryptSecret(payload);
  } catch {
    // A key encrypted under a different machine key cannot be recovered — report
    // it as absent rather than crashing the resolution path.
    return null;
  }
}

/**
 * The effective value of a key, in precedence order:
 *   1. a real environment variable (deployment wins),
 *   2. the encrypted vault.
 * Returns null when neither is present.
 */
export async function resolveProviderKey(envVar: string): Promise<string | null> {
  const fromEnv = process.env[envVar];
  if (fromEnv && fromEnv.trim() !== '') return fromEnv;
  return storedProviderKey(envVar);
}

/**
 * Copy stored keys into `process.env` so existing consumers (which read env
 * vars directly) use them without a per-provider refactor.
 *
 * - A REAL env var is never overwritten — a deployment's configuration is
 *   authoritative, and the vault is a convenience for local installs.
 * - Values are never logged.
 * - Idempotent; safe to call at boot and after each save.
 */
export async function applyStoredKeysToEnv(): Promise<number> {
  const vault = await readVault();
  let applied = 0;
  for (const envVar of Object.keys(vault.keys)) {
    // Track which vars this process itself populated, so a later save/delete can
    // update them without ever touching a real deployment variable.
    if (vaultApplied.has(envVar)) {
      const stored = await storedProviderKey(envVar);
      if (stored) {
        process.env[envVar] = stored;
        applied++;
      } else {
        delete process.env[envVar];
        vaultApplied.delete(envVar);
      }
      continue;
    }
    if (process.env[envVar] && process.env[envVar]!.trim() !== '') continue; // real env wins
    const stored = await storedProviderKey(envVar);
    if (!stored) continue;
    process.env[envVar] = stored;
    vaultApplied.add(envVar);
    applied++;
  }
  return applied;
}

/**
 * Non-secret status for every provider key. This is what the UI renders — the
 * key itself never crosses this boundary.
 */
export interface ProviderKeyStatus {
  envVar: string;
  label: string;
  provider: string;
  category: KeyCategory;
  description: string;
  docsUrl?: string;
  publicValue: boolean;
  testable: boolean;
  /** A real environment variable is set — authoritative, not editable here. */
  fromEnv: boolean;
  /** An encrypted value is stored in the vault. */
  stored: boolean;
  /** Effective resolution: env or vault. */
  configured: boolean;
  /** Masked hint, e.g. "sk-…AB12". Never the full key. */
  hint?: string;
}

/** A masked hint that reveals at most the last 4 characters. */
function maskHint(value: string): string {
  const v = value.trim();
  if (v.length <= 4) return '••••';
  return `••••${v.slice(-4)}`;
}

export async function listProviderKeyStatus(): Promise<ProviderKeyStatus[]> {
  const vault = await readVault();
  const out: ProviderKeyStatus[] = [];
  for (const def of PROVIDER_KEYS) {
    const fromEnv = Boolean(process.env[def.envVar] && process.env[def.envVar]!.trim() !== '');
    const stored = Boolean(vault.keys[def.envVar]);
    let hint: string | undefined;
    if (fromEnv && !def.publicValue) hint = maskHint(process.env[def.envVar]!);
    else if (stored && !def.publicValue) {
      const decrypted = await storedProviderKey(def.envVar);
      if (decrypted) hint = maskHint(decrypted);
    }
    out.push({
      envVar: def.envVar,
      label: def.label,
      provider: def.provider,
      category: def.category,
      description: def.description,
      docsUrl: def.docsUrl,
      publicValue: Boolean(def.publicValue),
      testable: Boolean(def.test),
      fromEnv,
      stored,
      configured: fromEnv || stored,
      hint,
    });
  }
  return out;
}
