// ── LLM provider presets (derived from the canonical provider registry) ─────
// This file used to be a second provider table. It is now a thin view over
// `lib/providers/registry`, so the onboarding wizard, Settings › AI, the vault
// and the Python runtime cannot disagree about a provider id, base URL or auth
// style again.
//
// Each preset still fills in `baseUrl` + a default `model`; the operator supplies
// the key (or the vault/environment does), which is why the catalog reports key
// status honestly instead of pretending to connect.

import {
  PROVIDERS,
  getProvider,
  providerForBaseUrl,
  isLocalUrl,
  type ProviderDescriptor,
} from "@/lib/providers/registry";

export interface LLMPreset {
  id: string;
  name: string;
  description: string;
  /** OpenAI-compatible base URL (or the native API root), no trailing slash. */
  baseUrl: string;
  /** Sensible default model for this provider. */
  model: string;
  /** Env var that supplies the key, when the provider is env-configurable. */
  envVar?: string;
  /** True when no key is needed (local servers). */
  keyless?: boolean;
  docsUrl?: string;
  recommended?: boolean;
  // Additive fields used by the connect flow. They are optional so every
  // existing consumer that only reads id/name/baseUrl/model keeps working.
  protocol?: ProviderDescriptor["protocol"];
  authStyle?: ProviderDescriptor["authStyle"];
  local?: boolean;
  tier?: ProviderDescriptor["tier"];
  supportsModelList?: boolean;
  keyPrefixes?: string[];
}

function toPreset(provider: ProviderDescriptor): LLMPreset {
  return {
    id: provider.id,
    name: provider.name,
    description: provider.description,
    baseUrl: provider.baseUrl,
    model: provider.model,
    envVar: provider.envVar,
    keyless: provider.keyless,
    docsUrl: provider.docsUrl,
    recommended: provider.recommended,
    protocol: provider.protocol,
    authStyle: provider.authStyle,
    local: provider.local,
    tier: provider.tier,
    supportsModelList: provider.supportsModelList,
    keyPrefixes: provider.keyPrefixes,
  };
}

export const LLM_PRESETS: LLMPreset[] = PROVIDERS.map(toPreset);

export function getLLMPreset(id: string): LLMPreset | undefined {
  const provider = getProvider(id);
  return provider ? toPreset(provider) : undefined;
}

/**
 * True when a base URL points at the local machine. Local inference servers
 * (Ollama, LM Studio) legitimately need no API key, so the key requirement in
 * `setLLMConfig` must not block them.
 *
 * Lives here (a pure, client-safe module) rather than in `lib/settings.ts`,
 * which imports Prisma — that import must never reach the browser bundle.
 */
export function isLocalBaseUrl(baseUrl: string): boolean {
  return isLocalUrl(baseUrl);
}

/**
 * Match a saved base URL back to a preset, so the UI can show "current".
 *
 * Local servers are routinely pasted without the OpenAI `/v1` suffix
 * (`http://localhost:11434`, Ollama's documented root, instead of `…/v1`).
 * Both name the same server, so a keyless preset also matches its root form.
 */
export function presetForBaseUrl(baseUrl: string): LLMPreset | undefined {
  const provider = providerForBaseUrl(baseUrl);
  return provider ? toPreset(provider) : undefined;
}

/**
 * The provider id the runtime should use for a saved LLM config.
 *
 * `auto` and `mock` are CONFIGURATION sentinels, not provider catalog ids — the
 * Python runtime cannot build a model from them. Resolve the sentinel from the
 * endpoint the operator actually saved: the preset that owns this base URL, else
 * the generic keyless local kind for a loopback URL, else `openai` for a hosted
 * OpenAI-compatible URL.
 */
export function resolveLLMProviderId(config: {
  provider: string;
  baseUrl: string;
}): string {
  if (config.provider && config.provider !== "auto" && config.provider !== "mock") {
    return config.provider;
  }
  const preset = presetForBaseUrl(config.baseUrl);
  if (preset) return preset.id;
  return isLocalBaseUrl(config.baseUrl) ? "ollama" : "openai";
}

/**
 * Every env var the UI reports key status for. Kept as one list so the catalog
 * and `/api/settings` cannot disagree about what "configured" means.
 *
 * These are all *optional* additions to the scraper chain — none are required
 * for the app to run (zero-config policy, ADR-001).
 */
export const CATALOG_ENV_VARS: string[] = [
  // AI
  "OPENAI_API_KEY",
  "ANTHROPIC_API_KEY",
  "OLLAMA_BASE_URL",
  "OLLAMA_API_KEY",
  "GROQ_API_KEY",
  "DEEPSEEK_API_KEY",
  "MISTRAL_API_KEY",
  "GEMINI_API_KEY",
  "XAI_API_KEY",
  "OPENROUTER_API_KEY",
  "OPENCODE_API_KEY",
  "TOGETHER_API_KEY",
  "PERPLEXITY_API_KEY",
  "FIREWORKS_API_KEY",
  "CUSTOM_LLM_API_KEY",
  // Market data
  "YAHOO_FINANCE_ENABLED",
  "FINNHUB_API_KEY",
  "POLYGON_API_KEY",
  "ALPHAVANTAGE_API_KEY",
  "TWELVE_DATA_API_KEY",
  "MARKETSTACK_API_KEY",
  // Crypto
  "COINGECKO_API_KEY",
  "COINMARKETCAP_API_KEY",
  // Economics
  "FRED_API_KEY",
  "BEA_API_KEY",
  "BLS_API_KEY",
  "TRADING_ECONOMICS_API_KEY",
  "AKSHARE_API_KEY",
];
