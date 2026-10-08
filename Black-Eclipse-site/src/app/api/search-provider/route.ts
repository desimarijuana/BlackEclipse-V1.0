// Search-provider status + a REAL connectivity test.
//
// GET  → which search route is configured (operator provider + keyless chain),
//        without ever echoing the key.
// POST → run one live probe query through the ordered providers and report who
//        answered (or the honest per-provider diagnostics). Never fabricates a
//        result and never claims success because a key merely exists.

import { NextResponse } from "next/server";
import { guardMutation, rateLimit } from "@/lib/api-guard";
import { resolveProviderKey } from "@/lib/provider-keys";
import {
  CustomJsonSearchProvider,
  buildPresetSearchProvider,
  firstConfiguredPreset,
  resolveSearchApiConfig,
  resolveSearchProviders,
  SEARCH_PROVIDER_PRESETS,
} from "@/lib/web-search";
import { searchWeb } from "@/lib/web-research";

export const dynamic = "force-dynamic";

async function currentProvider(): Promise<{ configured: boolean; preset: string | null; keyless: string[] }> {
  let raw: string | null = null;
  try {
    raw = await resolveProviderKey("SEARCH_API_CONFIG");
  } catch {
    raw = null;
  }
  const config = raw ? resolveSearchApiConfig(raw) : null;
  if (config?.url) {
    return {
      configured: true,
      preset: raw?.trim().startsWith("{") ? "custom" : raw?.trim() || null,
      keyless: ["duckduckgo-html", "duckduckgo-lite", "mojeek", "bing-html"],
    };
  }
  // A named provider added directly in Settings is a configured provider too.
  let named: ReturnType<typeof firstConfiguredPreset> = null;
  try {
    named = firstConfiguredPreset((envVar) => process.env[envVar] ?? null);
    if (!named) {
      // The vault may hold the key even when process.env was not hydrated yet.
      for (const p of SEARCH_PROVIDER_PRESETS) {
        const v = await resolveProviderKey(p.keyEnv).catch(() => null);
        if (v && v.trim()) {
          named = { preset: p, value: v };
          break;
        }
      }
    }
  } catch {
    named = null;
  }
  return {
    configured: Boolean(named),
    preset: named?.preset.id ?? null,
    keyless: ["duckduckgo-html", "duckduckgo-lite", "mojeek", "bing-html"],
  };
}

export async function GET() {
  try {
    return NextResponse.json({
      provider: await currentProvider(),
      presets: SEARCH_PROVIDER_PRESETS.map((p) => ({
        id: p.id,
        name: p.name,
        keyUrl: p.keyUrl,
        keyEnv: p.keyEnv,
        publicValue: p.publicValue ?? false,
      })),
    });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "failed to read search provider status" },
      { status: 500 },
    );
  }
}

export async function POST(request: Request) {
  const blocked = guardMutation(request, "search-provider-test");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const limited = rateLimit("search-provider-test", { limit: 10, windowMs: 60_000 });
  if (!limited.ok) {
    return NextResponse.json({ error: `Too many tests — retry in ${limited.retryAfterSec}s` }, { status: 429 });
  }

  let query = "BlackEclipse search connectivity probe";
  try {
    const body = (await request.json()) as { query?: string };
    if (typeof body.query === "string" && body.query.trim()) query = body.query.trim();
  } catch {
    /* an empty/invalid body uses the default probe query */
  }

  let custom: CustomJsonSearchProvider | null = null;
  try {
    const raw = await resolveProviderKey("SEARCH_API_CONFIG");
    const config = raw ? resolveSearchApiConfig(raw) : null;
    if (config?.url) {
      const apiKey = await resolveProviderKey("SEARCH_API_KEY").catch(() => null);
      custom = new CustomJsonSearchProvider({ ...config, apiKey });
    } else {
      // Fall back to the first named provider added directly in Settings.
      let named = firstConfiguredPreset((envVar) => process.env[envVar] ?? null);
      if (!named) {
        for (const p of SEARCH_PROVIDER_PRESETS) {
          const v = await resolveProviderKey(p.keyEnv).catch(() => null);
          if (v && v.trim()) {
            named = { preset: p, value: v };
            break;
          }
        }
      }
      if (named) {
        const value = (await resolveProviderKey(named.preset.keyEnv).catch(() => null)) ?? named.value;
        custom = buildPresetSearchProvider(named.preset, value);
      }
    }
  } catch {
    custom = null;
  }

  const providers = await resolveSearchProviders(custom);
  const outcome = await searchWeb(query, 3, providers);
  const configuredProvider = custom ? "custom-search" : null;
  return NextResponse.json({
    ok: outcome.results.length > 0,
    provider: outcome.provider,
    configuredProvider,
    resultCount: outcome.results.length,
    sample: outcome.results.slice(0, 3).map((r) => ({ title: r.title, url: r.url })),
    diagnostics: outcome.diagnostics.map((d) => ({
      provider: d.provider,
      category: d.category,
      detail: d.detail,
      latencyMs: d.latencyMs,
    })),
  });
}
