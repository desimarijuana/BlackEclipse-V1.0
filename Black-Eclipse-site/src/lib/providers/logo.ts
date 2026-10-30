// ── Provider logo registry ─────────────────────────────────────────────────
// One mapping from a provider id/label (as the runtime reports it) to the local
// brand mark in `public/providers/`. Vendored on purpose: the UI must render
// provider identity without calling a CDN (offline, private, zero-config).
//
// Assets are silhouettes; `ProviderLogo` masks them with `currentColor` so they
// adapt to the active theme instead of depending on the brand's original fill.

export const PROVIDER_LOGO_ASSETS: Record<string, string> = {
  openai: '/providers/openai.svg',
  anthropic: '/providers/anthropic.svg',
  google: '/providers/google.svg',
  mistral: '/providers/mistral.svg',
  deepseek: '/providers/deepseek.svg',
  openrouter: '/providers/openrouter.svg',
  perplexity: '/providers/perplexity.svg',
  fireworks: '/providers/fireworks.svg',
  opencode: '/providers/opencode.svg',
  groq: '/providers/groq.svg',
  together: '/providers/together.svg',
  ollama: '/providers/ollama.svg',
  xai: '/providers/xai.svg',
  lmstudio: '/providers/lmstudio.svg',
  // The agent itself is not a model provider, but its pill is a provider slot.
  eclipse: '/branding/FAVICON.svg',
};

const ALIASES: Record<string, string> = {
  x: 'xai',
  grok: 'xai',
  xaigrok: 'xai',
  googlegemini: 'google',
  gemini: 'google',
  mistralai: 'mistral',
  fireworksai: 'fireworks',
  opencodezen: 'opencode',
  togetherai: 'together',
  lmstudiocommunity: 'lmstudio',
  eclipseagent: 'eclipse',
  eclipsebot: 'eclipse',
};

/**
 * Resolve a provider id or human label to a known logo id.
 *
 * Accepts labels with qualifiers ("Ollama (local)", "OpenAI", "Google Gemini")
 * because the composer sometimes only knows the display label. Unknown,
 * custom and `auto` providers return null so the caller can use a neutral
 * fallback instead of inventing a brand.
 */
export function providerLogoId(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const key = raw
    .toLowerCase()
    .replace(/\([^)]*\)/g, ' ')
    .replace(/[^a-z0-9]+/g, '');
  if (!key) return null;
  const id = ALIASES[key] ?? key;
  return PROVIDER_LOGO_ASSETS[id] ? id : null;
}

export function providerLogoAsset(raw: string | null | undefined): string | null {
  const id = providerLogoId(raw);
  return id ? PROVIDER_LOGO_ASSETS[id] : null;
}
