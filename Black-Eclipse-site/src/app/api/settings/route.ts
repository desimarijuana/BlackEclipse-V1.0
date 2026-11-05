import { NextResponse } from "next/server";
import {
  getLLMConfig,
  setLLMConfig,
  getNewsFeeds,
  setNewsFeeds,
  getPreferences,
  setPreferences,
  getIntegrationsStatus,
} from "@/lib/settings";
import { guardMutation, checkOutboundUrl } from "@/lib/api-guard";
import { PrivacyViolationError } from "@/lib/privacy";

export const dynamic = "force-dynamic";

// In-memory SWR cache. The settings read is four SystemConfig lookups plus a
// provider-key vault read — fast when the DB is idle (~25 ms), but during
// startup the WarmUp/NewsIngest jobs hold SQLite for tens of seconds and any
// queued request waits behind them (the "settings never loads until refresh"
// hang). Serve the cached payload instantly; refresh in the background.
const CACHE_TTL_MS = 60 * 1000;

interface SettingsPayload {
  llm: ReturnType<typeof maskLLMConfig>;
  newsFeeds: Awaited<ReturnType<typeof getNewsFeeds>>;
  preferences: Awaited<ReturnType<typeof getPreferences>>;
  integrations: Awaited<ReturnType<typeof getIntegrationsStatus>>;
}

let settingsCache: { t: number; data: SettingsPayload } | null = null;
let rebuildInFlight = false;

async function buildSettingsPayload(): Promise<SettingsPayload> {
  const [llm, feeds, prefs, integrations] = await Promise.all([
    getLLMConfig(),
    getNewsFeeds(),
    getPreferences(),
    getIntegrationsStatus(),
  ]);
  return {
    llm: maskLLMConfig(llm),
    newsFeeds: feeds,
    preferences: prefs,
    integrations,
  };
}

function startBackgroundRebuild() {
  if (rebuildInFlight) return;
  rebuildInFlight = true;
  buildSettingsPayload()
    .then((data) => { settingsCache = { t: Date.now(), data }; })
    .catch((err) => console.error("[api/settings] background rebuild error:", err))
    .finally(() => { rebuildInFlight = false; });
}

// Never send the stored API key back to any caller — only whether one exists.
function maskLLMConfig(llm: Awaited<ReturnType<typeof getLLMConfig>>) {
  return {
    provider: llm.provider,
    baseUrl: llm.baseUrl,
    model: llm.model,
    hasApiKey: Boolean(llm.apiKey),
    // The declared context window is not a secret; it round-trips so the UI can
    // show/edit it. Absent = unknown.
    contextWindow: llm.contextWindow,
    // The reasoning-effort override ("model variant") is not a secret either;
    // round-trip it so the picker reflects the saved choice. Absent = Auto.
    reasoningEffort: llm.reasoningEffort,
    // The model-routing preference is not a secret either; round-trip it.
    routingPolicy: llm.routingPolicy,
  };
}

// GET /api/settings — return all current settings + integration status.
// The LLM API key is intentionally omitted (masked as `hasApiKey`).
export async function GET() {
  try {
    if (settingsCache) {
      if (Date.now() - settingsCache.t < CACHE_TTL_MS) {
        return NextResponse.json(settingsCache.data);
      }
      // Stale — serve it now and refresh quietly.
      startBackgroundRebuild();
      return NextResponse.json(settingsCache.data);
    }
    // Cold process: build once, synchronously, then cache.
    const data = await buildSettingsPayload();
    settingsCache = { t: Date.now(), data };
    return NextResponse.json(data);
  } catch (err) {
    console.error("[api/settings] GET error:", err);
    return NextResponse.json({ error: "Failed to load settings" }, { status: 500 });
  }
}

// POST /api/settings — update settings. Body may contain any/all of:
//   { llm?: { provider, baseUrl, apiKey?, model } }
//   { newsFeeds?: NewsFeed[] }
//   { preferences?: Partial<AppPreferences> }
//
// `apiKey` handling: an empty/undefined apiKey keeps the previously stored key
// so the masked UI doesn't force re-entry. News feed URLs are validated against
// the SSRF guard before being persisted.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "settings");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = await request.json().catch(() => ({}));

    if (body.llm) {
      const incoming = { ...body.llm };
      if (!incoming.apiKey) delete incoming.apiKey; // keep stored key
      // An empty context-window field means "unknown" and must CLEAR any prior
      // declaration (setLLMConfig treats null as an explicit clear), not silently
      // keep it.
      await setLLMConfig(incoming);
    }
    if (Array.isArray(body.newsFeeds)) {
      const unsafe = body.newsFeeds.filter(
        (f: { url?: string }) => typeof f.url !== "string" || !checkOutboundUrl(f.url).safe
      );
      if (unsafe.length > 0) {
        return NextResponse.json(
          { error: `Blocked feed URL(s): ${unsafe.map((f: { url: string }) => f.url).join(", ")}` },
          { status: 400 }
        );
      }
      await setNewsFeeds(body.newsFeeds);
    }
    if (body.preferences) {
      await setPreferences(body.preferences);
    }

    const [llm, feeds, prefs] = await Promise.all([
      getLLMConfig(),
      getNewsFeeds(),
      getPreferences(),
    ]);
    const payload = {
      llm: maskLLMConfig(llm),
      newsFeeds: feeds,
      preferences: prefs,
    };
    // Keep the GET cache coherent with what was just written.
    if (settingsCache) {
      settingsCache = {
        t: Date.now(),
        data: {
          ...settingsCache.data,
          llm: payload.llm,
          newsFeeds: payload.newsFeeds,
          preferences: payload.preferences,
        },
      };
    }
    return NextResponse.json({ success: true, ...payload });
  } catch (err) {
    if (err instanceof PrivacyViolationError) {
      return NextResponse.json({ error: err.message, code: err.code }, { status: 403 });
    }
    console.error("[api/settings] POST error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to save settings" },
      { status: 500 }
    );
  }
}
