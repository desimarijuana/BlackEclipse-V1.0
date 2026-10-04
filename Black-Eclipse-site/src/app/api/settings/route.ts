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

export const dynamic = "force-dynamic";

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
    // The model-routing preference is not a secret either; round-trip it.
    routingPolicy: llm.routingPolicy,
  };
}

// GET /api/settings — return all current settings + integration status.
// The LLM API key is intentionally omitted (masked as `hasApiKey`).
export async function GET() {
  try {
    const [llm, feeds, prefs, integrations] = await Promise.all([
      getLLMConfig(),
      getNewsFeeds(),
      getPreferences(),
      getIntegrationsStatus(),
    ]);
    return NextResponse.json({
      llm: maskLLMConfig(llm),
      newsFeeds: feeds,
      preferences: prefs,
      integrations,
    });
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
    return NextResponse.json({
      success: true,
      llm: maskLLMConfig(llm),
      newsFeeds: feeds,
      preferences: prefs,
    });
  } catch (err) {
    console.error("[api/settings] POST error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to save settings" },
      { status: 500 }
    );
  }
}
