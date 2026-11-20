// ── AI provider registry (client-safe, single source of truth) ──────────────
// One descriptor per LLM API the UI can connect. This module replaces the three
// drifting tables that used to exist (presets.ts, provider-keys.ts and the
// Python catalog): the UI presets are DERIVED from here, and a parity test keeps
// it in step with `python/harness/models.py`.
//
// A descriptor answers every question the connect UI asks:
//   - what protocol does it speak?      → protocol
//   - how is the key presented?         → authStyle
//   - where is the API / key page?      → baseUrl / docsUrl
//   - can we list models?               → supportsModelList
//   - how do we recognise a pasted key? → keyPrefixes
//
// It contains no secrets and no server-only imports, so both the browser and
// the Next route handlers can use it.

export type ProviderProtocol = "openai" | "anthropic" | "google";

/**
 * How the credential is presented to the provider. Test/probe code MUST use
 * this — sending every key as `Authorization: Bearer` is why a valid Anthropic
 * or Gemini key used to report "rejected".
 */
export type ProviderAuthStyle =
  | "bearer"
  | "x-api-key"
  | "x-goog-api-key"
  | "none";

export type ProviderTier = "free" | "free-tier" | "paid";

export interface ProviderDescriptor {
  id: string;
  /** Display name, e.g. "OpenAI". */
  name: string;
  /** One plain-language sentence for a non-technical user. */
  description: string;
  protocol: ProviderProtocol;
  authStyle: ProviderAuthStyle;
  /** OpenAI-compatible base URL (or the native API root for Anthropic/Google). */
  baseUrl: string;
  /** A safe default model id for the provider. */
  model: string;
  /** Vault env var that stores the key, when keyed. */
  envVar?: string;
  /** True when no credential is needed (a local model server). */
  keyless?: boolean;
  /** True when the endpoint runs on the operator's machine. */
  local?: boolean;
  /** Where to create/manage the key. */
  docsUrl?: string;
  /** Prefixes that make a pasted key recognisable. Longest match wins. */
  keyPrefixes?: string[];
  tier: ProviderTier;
  /** Show in the onboarding "popular" set. */
  popular?: boolean;
  recommended?: boolean;
  /** Providers that publish a model list at the protocol's standard path.
   * Defaults to true when omitted. */
  supportsModelList?: boolean;
}

/**
 * The canonical AI providers. Order is the order the UI shows popular entries.
 *
 * `baseUrl` values are preserved from the original presets so a saved config
 * still matches its provider after an upgrade.
 */
export const PROVIDERS: ProviderDescriptor[] = [
  {
    id: "openai",
    name: "OpenAI",
    description: "ChatGPT models (GPT-5, GPT-4.1). The reference API most tools copy.",
    protocol: "openai",
    authStyle: "bearer",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
    envVar: "OPENAI_API_KEY",
    docsUrl: "https://platform.openai.com/api-keys",
    keyPrefixes: ["sk-proj-", "sk-svcacct-", "sk-"],
    tier: "paid",
    popular: true,
  },
  {
    id: "anthropic",
    name: "Anthropic",
    description: "Claude models. Strong long-document reasoning and writing.",
    protocol: "anthropic",
    authStyle: "x-api-key",
    baseUrl: "https://api.anthropic.com/v1",
    model: "claude-3-5-sonnet-latest",
    envVar: "ANTHROPIC_API_KEY",
    docsUrl: "https://console.anthropic.com/settings/keys",
    keyPrefixes: ["sk-ant-"],
    tier: "paid",
    popular: true,
  },
  {
    id: "google",
    name: "Google Gemini",
    description: "Gemini models. A generous free tier for everyday chat.",
    protocol: "google",
    authStyle: "x-goog-api-key",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    model: "gemini-2.0-flash",
    envVar: "GEMINI_API_KEY",
    docsUrl: "https://aistudio.google.com/app/apikey",
    keyPrefixes: ["AIza"],
    tier: "free-tier",
    popular: true,
  },
  {
    id: "deepseek",
    name: "DeepSeek",
    description: "Low-cost reasoning and coding models with an OpenAI-compatible API.",
    protocol: "openai",
    authStyle: "bearer",
    baseUrl: "https://api.deepseek.com/v1",
    model: "deepseek-chat",
    envVar: "DEEPSEEK_API_KEY",
    docsUrl: "https://platform.deepseek.com/api_keys",
    keyPrefixes: ["sk-"],
    tier: "paid",
    popular: true,
  },
  {
    id: "groq",
    name: "Groq",
    description: "Very fast open models (Llama, Gemma) with a free tier.",
    protocol: "openai",
    authStyle: "bearer",
    baseUrl: "https://api.groq.com/openai/v1",
    model: "llama-3.3-70b-versatile",
    envVar: "GROQ_API_KEY",
    docsUrl: "https://console.groq.com/keys",
    keyPrefixes: ["gsk_"],
    tier: "free-tier",
    popular: true,
  },
  {
    id: "openrouter",
    name: "OpenRouter",
    description: "One key for hundreds of models from many providers.",
    protocol: "openai",
    authStyle: "bearer",
    baseUrl: "https://openrouter.ai/api/v1",
    model: "openai/gpt-4o-mini",
    envVar: "OPENROUTER_API_KEY",
    docsUrl: "https://openrouter.ai/keys",
    keyPrefixes: ["sk-or-"],
    tier: "paid",
    popular: true,
  },
  {
    id: "opencode",
    name: "OpenCode Zen",
    description: "Curated coding models through the OpenCode Console gateway.",
    protocol: "openai",
    authStyle: "bearer",
    baseUrl: "https://opencode.ai/inference/openai/v1",
    model: "glm-5.3",
    envVar: "OPENCODE_API_KEY",
    docsUrl: "https://opencode.ai/console",
    tier: "paid",
    popular: true,
  },
  {
    id: "opencode-go",
    name: "OpenCode Go",
    description: "The OpenCode Go subscription gateway. Uses the same Console key.",
    protocol: "openai",
    authStyle: "bearer",
    baseUrl: "https://opencode.ai/inference/go/openai/v1",
    model: "kimi-k3",
    envVar: "OPENCODE_API_KEY",
    docsUrl: "https://opencode.ai/docs/console/go/",
    tier: "paid",
    popular: true,
  },
  {
    id: "mistral",
    name: "Mistral",
    description: "European open-weight and commercial models.",
    protocol: "openai",
    authStyle: "bearer",
    baseUrl: "https://api.mistral.ai/v1",
    model: "mistral-large-latest",
    envVar: "MISTRAL_API_KEY",
    docsUrl: "https://console.mistral.ai/api-keys/",
    tier: "paid",
    popular: true,
  },
  {
    id: "xai",
    name: "xAI Grok",
    description: "Grok models with real-time search capability.",
    protocol: "openai",
    authStyle: "bearer",
    baseUrl: "https://api.x.ai/v1",
    model: "grok-2-latest",
    envVar: "XAI_API_KEY",
    docsUrl: "https://console.x.ai/",
    keyPrefixes: ["xai-"],
    tier: "paid",
    popular: true,
  },
  {
    id: "together",
    name: "Together AI",
    description: "Hosted open models with an OpenAI-compatible API.",
    protocol: "openai",
    authStyle: "bearer",
    baseUrl: "https://api.together.xyz/v1",
    model: "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    envVar: "TOGETHER_API_KEY",
    docsUrl: "https://api.together.xyz/settings/api-keys",
    tier: "paid",
  },
  {
    id: "perplexity",
    name: "Perplexity",
    description: "Search-grounded models — useful for news and catalyst research.",
    protocol: "openai",
    authStyle: "bearer",
    baseUrl: "https://api.perplexity.ai",
    model: "sonar",
    envVar: "PERPLEXITY_API_KEY",
    docsUrl: "https://www.perplexity.ai/settings/api",
    keyPrefixes: ["pplx-"],
    tier: "paid",
  },
  {
    id: "fireworks",
    name: "Fireworks AI",
    description: "Fast hosted inference for open-weight models.",
    protocol: "openai",
    authStyle: "bearer",
    baseUrl: "https://api.fireworks.ai/inference/v1",
    model: "accounts/fireworks/models/llama-v3p3-70b-instruct",
    envVar: "FIREWORKS_API_KEY",
    docsUrl: "https://fireworks.ai/account/api-keys",
    tier: "paid",
  },
  {
    id: "ollama",
    name: "Ollama (local)",
    description: "Run models on your own machine. Free, private, no key.",
    protocol: "openai",
    authStyle: "none",
    baseUrl: "http://localhost:11434/v1",
    model: "llama3.1",
    envVar: "OLLAMA_BASE_URL",
    keyless: true,
    local: true,
    docsUrl: "https://ollama.com/download",
    tier: "free",
    popular: true,
    recommended: true,
    supportsModelList: true,
  },
  {
    id: "ollama-cloud",
    name: "Ollama Cloud",
    description: "Ollama's hosted models — no local GPU. Needs an ollama.com key.",
    protocol: "openai",
    authStyle: "bearer",
    baseUrl: "https://ollama.com/v1",
    model: "gemma4:31b",
    envVar: "OLLAMA_API_KEY",
    docsUrl: "https://ollama.com/settings/keys",
    tier: "free-tier",
    popular: true,
  },
  {
    id: "lmstudio",
    name: "LM Studio (local)",
    description: "A local desktop app that serves GGUF models. Free, no key.",
    protocol: "openai",
    authStyle: "none",
    baseUrl: "http://localhost:1234/v1",
    model: "local-model",
    keyless: true,
    local: true,
    docsUrl: "https://lmstudio.ai/",
    tier: "free",
    supportsModelList: true,
  },
  {
    id: "custom",
    name: "Custom / other",
    description: "Any OpenAI-compatible URL — vLLM, LiteLLM, a company gateway.",
    protocol: "openai",
    authStyle: "bearer",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
    // A custom gateway may need a key or be keyless; the vault slot is shared so
    // the status UI can still report "connected" for a keyed custom endpoint.
    envVar: "CUSTOM_LLM_API_KEY",
    keyless: true,
    docsUrl: "https://platform.openai.com/docs/api-reference/authentication",
    tier: "paid",
    popular: true,
    supportsModelList: true,
  },
];

const BY_ID = new Map(PROVIDERS.map((p) => [p.id, p]));

export function getProvider(id: string): ProviderDescriptor | undefined {
  return BY_ID.get(id);
}

/** Providers shown in the onboarding/popular set, in registry order. */
export const POPULAR_PROVIDERS = PROVIDERS.filter((p) => p.popular);

/** Remote providers that accept a model list probe. */
export function supportsModelList(id: string): boolean {
  return BY_ID.get(id)?.supportsModelList !== false;
}

/**
 * True when a base URL points at the local machine. Local inference servers
 * (Ollama, LM Studio) legitimately need no API key.
 */
export function isLocalUrl(baseUrl: string): boolean {
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

/**
 * Normalise a base URL typed or pasted by a user.
 *
 * - trims whitespace, surrounding quotes and a leading `Bearer `
 * - adds `https://` when the scheme is missing
 * - strips a trailing slash and a trailing `/chat/completions` (people copy the
 *   full endpoint from docs; the runtime appends the path itself)
 *
 * Returns null when the value cannot be a URL.
 */
export function normalizeBaseUrl(raw: string): string | null {
  let value = raw.trim().replace(/^["'`]+|["'`]+$/g, "");
  if (!value) return null;
  value = value.replace(/^bearer\s+/i, "").trim();
  if (!/^https?:\/\//i.test(value)) {
    // A bare local address is almost always an HTTP dev server; everything else
    // defaults to HTTPS.
    const hostPart = value.split("/")[0].toLowerCase();
    const localHost = /^(localhost|127\.0\.0\.1|\[::1\]|::1)(:\d+)?$/.test(hostPart);
    value = `${localHost ? "http" : "https"}://${value}`;
  }
  value = value.replace(/\/+$/, "");
  value = value.replace(/\/chat\/completions$/i, "");
  try {
    const url = new URL(value);
    if (!url.hostname) return null;
    return value;
  } catch {
    return null;
  }
}

/** Remove whitespace and accidental `Bearer `/quotes from a pasted key. */
export function normalizeApiKey(raw: string): string {
  return raw
    .trim()
    .replace(/^["'`]+|["'`]+$/g, "")
    .replace(/^bearer\s+/i, "")
    .replace(/\s+/g, "");
}

/**
 * Recognise a provider from a pasted key. Only unambiguous prefixes are used:
 * a bare `sk-` is shared by OpenAI, DeepSeek and others, so it never wins.
 * Longest prefix first, so `sk-ant-` beats a hypothetical `sk-`.
 */
export function detectProviderFromKey(rawKey: string): ProviderDescriptor | null {
  const key = normalizeApiKey(rawKey);
  if (key.length < 6) return null;
  const candidates: Array<{ provider: ProviderDescriptor; prefix: string }> = [];
  for (const provider of PROVIDERS) {
    for (const prefix of provider.keyPrefixes ?? []) {
      if (key.startsWith(prefix)) candidates.push({ provider, prefix });
    }
  }
  if (candidates.length === 0) return null;
  candidates.sort((a, b) => b.prefix.length - a.prefix.length);
  const best = candidates[0];
  // If another provider shares the exact winning prefix, the key is ambiguous.
  const tied = candidates.filter((c) => c.prefix === best.prefix && c.provider.id !== best.provider.id);
  return tied.length > 0 ? null : best.provider;
}

/**
 * Resolve a saved base URL back to its provider descriptor. Local servers are
 * routinely saved with or without the `/v1` suffix, so both forms match.
 */
export function providerForBaseUrl(baseUrl: string): ProviderDescriptor | undefined {
  const normalized = (baseUrl || "").replace(/\/+$/, "");
  return PROVIDERS.find((p) => {
    const presetUrl = p.baseUrl.replace(/\/+$/, "");
    if (presetUrl === normalized) return true;
    return Boolean(p.local && p.id !== "custom" && presetUrl.replace(/\/v1$/, "") === normalized);
  });
}

/**
 * The auth headers for a provider. Returns an empty object for keyless/local.
 * `x-goog-api-key` is preferred over a query parameter so the key never lands
 * in a URL.
 */
export function authHeadersFor(
  provider: ProviderDescriptor | undefined,
  apiKey: string | undefined,
): Record<string, string> {
  const key = (apiKey ?? "").trim();
  if (!key || !provider || provider.authStyle === "none") return {};
  if (provider.authStyle === "x-api-key") {
    return { "x-api-key": key, "anthropic-version": "2023-06-01" };
  }
  if (provider.authStyle === "x-goog-api-key") {
    return { "x-goog-api-key": key };
  }
  return { authorization: `Bearer ${key}` };
}

/** The native API origin for an Anthropic/Google base URL. */
export function nativeOrigin(provider: ProviderDescriptor, baseUrl: string): string {
  const raw = normalizeBaseUrl(baseUrl) || provider.baseUrl;
  try {
    return new URL(raw).origin;
  } catch {
    return new URL(provider.baseUrl).origin;
  }
}
