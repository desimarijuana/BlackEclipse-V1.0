// ── Search provider resolution (the ONE place a provider is chosen) ──────────
// The data bridge asks this module which search provider to try first. Two
// paths, advanced first:
//   1. `SEARCH_API_CONFIG` (a preset name or full JSON) + `SEARCH_API_KEY`;
//   2. any named provider key added directly in Settings (Tavily/Brave/Exa/
//      Serper/SerpApi/Bing/Google CSE/SearXNG) — the first configured one wins.
// The keyless HTML chain is always appended LAST by `resolveSearchProviders`, so
// configuration is an optimisation, never a requirement.
//
// Extracted from `data-bridge.ts` so the bridge stays within its size budget and
// the resolution rule lives in exactly one module.

import { resolveProviderKey } from "@/lib/provider-keys";
import {
  CustomJsonSearchProvider,
  buildPresetSearchProvider,
  firstConfiguredPreset,
  resolveSearchApiConfig,
  SEARCH_PROVIDER_PRESETS,
  type SearchProvider,
} from "@/lib/web-search";

/**
 * The operator-configured search provider, or null when none is set. Never
 * invents an endpoint: a bad config yields null, and the caller falls back to the
 * keyless chain.
 */
export async function resolveCustomSearchProvider(): Promise<SearchProvider | null> {
  let raw: string | null = null;
  try {
    raw = await resolveProviderKey("SEARCH_API_CONFIG");
  } catch {
    raw = null;
  }
  if (raw && raw.trim()) {
    const config = resolveSearchApiConfig(raw);
    if (config && config.url) {
      let apiKey: string | null = null;
      try {
        apiKey = await resolveProviderKey("SEARCH_API_KEY");
      } catch {
        apiKey = null;
      }
      return new CustomJsonSearchProvider({ ...config, apiKey });
    }
  }
  // No advanced config: use the first named provider key the user added.
  try {
    let named = firstConfiguredPreset((envVar) => {
      const fromEnv = process.env[envVar];
      return fromEnv && fromEnv.trim() ? fromEnv : null;
    });
    if (!named) {
      // The vault may hold the key even when process.env was not hydrated yet.
      for (const preset of SEARCH_PROVIDER_PRESETS) {
        const value = await resolveProviderKey(preset.keyEnv).catch(() => null);
        if (value && value.trim()) {
          named = { preset, value };
          break;
        }
      }
    }
    if (!named) return null;
    const value = (await resolveProviderKey(named.preset.keyEnv).catch(() => null)) ?? named.value;
    return buildPresetSearchProvider(named.preset, value);
  } catch {
    return null;
  }
}

/** A concise, user-safe summary of a set of diagnostics. */
export function describeDiagnostics(diagnostics: Array<{ provider: string; category: string; detail?: string }>): string {
  return diagnostics
    .map((d) => `${d.provider}: ${d.category}${d.detail ? ` (${d.detail})` : ""}`)
    .join("; ");
}
