// ── LLM provider presets ────────────────────────────────────────────────────
// Concrete, working configurations for OpenAI-compatible chat-completions
// endpoints. Every entry here speaks the same protocol the existing
// `OpenAICompatibleProvider` already sends, so "Use this" is a real, functional
// choice — not a label.
//
// Each preset only fills in `baseUrl` + a default `model`. The operator still
// supplies the key (or sets it in the environment), which is why the catalog
// reports key status honestly rather than pretending to connect.

export interface LLMPreset {
  id: string;
  name: string;
  description: string;
  /** OpenAI-compatible base URL, no trailing slash. */
  baseUrl: string;
  /** Sensible default model for this provider. */
  model: string;
  /** Env var that supplies the key, when the provider is env-configurable. */
  envVar?: string;
  /** True when no key is needed (local servers). */
  keyless?: boolean;
  docsUrl?: string;
  recommended?: boolean;
}

export const LLM_PRESETS: LLMPreset[] = [
  {
    id: "openai",
    name: "OpenAI",
    description: "GPT models. The reference OpenAI-compatible endpoint.",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
    envVar: "OPENAI_API_KEY",
    docsUrl: "https://platform.openai.com/api-keys",
  },
  {
    id: "anthropic",
    name: "Anthropic",
    description: "Claude models via the OpenAI-compatible gateway.",
    baseUrl: "https://api.anthropic.com/v1",
    model: "claude-3-5-sonnet-latest",
    envVar: "ANTHROPIC_API_KEY",
    docsUrl: "https://console.anthropic.com/settings/keys",
  },
  {
    id: "ollama",
    name: "Ollama (local)",
    description: "Run models on your own machine. No key, no data leaves the box.",
    baseUrl: "http://localhost:11434/v1",
    model: "llama3.1",
    envVar: "OLLAMA_BASE_URL",
    keyless: true,
    recommended: true,
    docsUrl: "https://ollama.com/download",
  },
  {
    id: "ollama-cloud",
    name: "Ollama Cloud",
    description: "Ollama's hosted models — no local GPU. Needs an ollama.com API key.",
    baseUrl: "https://ollama.com/v1",
    model: "gemma4:31b",
    envVar: "OLLAMA_API_KEY",
    docsUrl: "https://ollama.com/settings/keys",
  },
  {
    id: "lmstudio",
    name: "LM Studio (local)",
    description: "Local GUI for GGUF models, exposes an OpenAI-compatible server.",
    baseUrl: "http://localhost:1234/v1",
    model: "local-model",
    keyless: true,
    docsUrl: "https://lmstudio.ai/",
  },
  {
    id: "groq",
    name: "Groq",
    description: "Very fast inference for open models (Llama, Mixtral, Gemma).",
    baseUrl: "https://api.groq.com/openai/v1",
    model: "llama-3.3-70b-versatile",
    envVar: "GROQ_API_KEY",
    docsUrl: "https://console.groq.com/keys",
  },
  {
    id: "deepseek",
    name: "DeepSeek",
    description: "Strong reasoning and coding models at low cost.",
    baseUrl: "https://api.deepseek.com/v1",
    model: "deepseek-chat",
    envVar: "DEEPSEEK_API_KEY",
    docsUrl: "https://platform.deepseek.com/api_keys",
  },
  {
    id: "mistral",
    name: "Mistral",
    description: "European open-weight and commercial models.",
    baseUrl: "https://api.mistral.ai/v1",
    model: "mistral-large-latest",
    envVar: "MISTRAL_API_KEY",
    docsUrl: "https://console.mistral.ai/api-keys/",
  },
  {
    id: "google",
    name: "Google Gemini",
    description: "Gemini models via their OpenAI-compatible endpoint.",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    model: "gemini-2.0-flash",
    envVar: "GEMINI_API_KEY",
    docsUrl: "https://aistudio.google.com/app/apikey",
  },
  {
    id: "xai",
    name: "xAI (Grok)",
    description: "Grok models with real-time search capability.",
    baseUrl: "https://api.x.ai/v1",
    model: "grok-2-latest",
    envVar: "XAI_API_KEY",
    docsUrl: "https://console.x.ai/",
  },
  {
    id: "openrouter",
    name: "OpenRouter",
    description: "One key for hundreds of models across providers, with fallback routing.",
    baseUrl: "https://openrouter.ai/api/v1",
    model: "openai/gpt-4o-mini",
    envVar: "OPENROUTER_API_KEY",
    docsUrl: "https://openrouter.ai/keys",
  },
  {
    id: "opencode",
    name: "OpenCode Zen",
    description: "OpenCode's gateway of curated coding models on one key.",
    baseUrl: "https://opencode.ai/inference/openai/v1",
    model: "glm-5.3",
    envVar: "OPENCODE_API_KEY",
    docsUrl: "https://opencode.ai/console",
  },
  {
    id: "opencode-go",
    name: "OpenCode Go",
    description: "OpenCode's Go subscription gateway — a different base URL from Zen; same Console key.",
    baseUrl: "https://opencode.ai/inference/go/openai/v1",
    model: "kimi-k3",
    envVar: "OPENCODE_API_KEY",
    docsUrl: "https://opencode.ai/docs/console/go/",
  },
  {
    id: "together",
    name: "Together AI",
    description: "Hosted open models with an OpenAI-compatible API.",
    baseUrl: "https://api.together.xyz/v1",
    model: "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    envVar: "TOGETHER_API_KEY",
    docsUrl: "https://api.together.xyz/settings/api-keys",
  },
  {
    id: "perplexity",
    name: "Perplexity",
    description: "Search-grounded models — useful for news and catalyst research.",
    baseUrl: "https://api.perplexity.ai",
    model: "sonar",
    envVar: "PERPLEXITY_API_KEY",
    docsUrl: "https://www.perplexity.ai/settings/api",
  },
  {
    id: "fireworks",
    name: "Fireworks AI",
    description: "Fast hosted inference for open-weight models.",
    baseUrl: "https://api.fireworks.ai/inference/v1",
    model: "accounts/fireworks/models/llama-v3p3-70b-instruct",
    envVar: "FIREWORKS_API_KEY",
    docsUrl: "https://fireworks.ai/account/api-keys",
  },
  {
    id: "custom",
    name: "Custom provider",
    description: "Any OpenAI-compatible endpoint by base URL.",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
    keyless: true,
  },
];

export function getLLMPreset(id: string): LLMPreset | undefined {
  return LLM_PRESETS.find((p) => p.id === id);
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
  try {
    const host = new URL(baseUrl).hostname.toLowerCase();
    return (
      host === "localhost" ||
      host === "127.0.0.1" ||
      host === "[::1]" ||
      host === "::1" ||
      host === "0.0.0.0"
    );
  } catch {
    return false;
  }
}

/** Match a saved base URL back to a preset, so the UI can show "current". */
export function presetForBaseUrl(baseUrl: string): LLMPreset | undefined {
  const normalized = baseUrl.replace(/\/+$/, "");
  return LLM_PRESETS.find((p) => p.baseUrl.replace(/\/+$/, "") === normalized);
}

/**
 * The provider id the runtime should use for a saved LLM config.
 *
 * `auto` and `mock` are CONFIGURATION sentinels, not provider catalog ids — the
 * Python runtime cannot build a model from them. Previously callers forwarded
 * both as `openai`, so a valid local endpoint (Ollama/LM Studio) was treated as
 * a keyed OpenAI account and every run failed with "Provider 'openai' is not
 * configured (missing API key)" even though the local server was running.
 *
 * Resolve the sentinel from the endpoint the operator actually saved: the
 * preset that owns this base URL, else the generic keyless local kind for a
 * loopback URL, else the generic OpenAI-compatible kind for a hosted URL.
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
