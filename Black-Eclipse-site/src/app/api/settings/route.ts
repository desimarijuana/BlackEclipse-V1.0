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

export const dynamic = "force-dynamic";

// GET /api/settings — return all current settings + integration status.
export async function GET() {
  try {
    const [llm, feeds, prefs, integrations] = await Promise.all([
      getLLMConfig(),
      getNewsFeeds(),
      getPreferences(),
      getIntegrationsStatus(),
    ]);
    return NextResponse.json({
      llm,
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
//   { llm?: { provider, baseUrl, apiKey, model } }
//   { newsFeeds?: NewsFeed[] }
//   { preferences?: Partial<AppPreferences> }
export async function POST(request: Request) {
  try {
    const body = await request.json().catch(() => ({}));

    if (body.llm) {
      await setLLMConfig(body.llm);
    }
    if (Array.isArray(body.newsFeeds)) {
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
    return NextResponse.json({ success: true, llm, newsFeeds: feeds, preferences: prefs });
  } catch (err) {
    console.error("[api/settings] POST error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to save settings" },
      { status: 500 }
    );
  }
}
