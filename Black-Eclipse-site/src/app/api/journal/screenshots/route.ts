import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { getOrCreateProfile, addTradeScreenshot, listTradeScreenshots } from "@/lib/journal/data";

export const dynamic = "force-dynamic";

// GET /api/journal/screenshots?tradeId=... — list screenshots for a trade.
export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const tradeId = searchParams.get("tradeId") ?? "";
    if (!tradeId) return NextResponse.json({ screenshots: [] });
    const profileId = await getOrCreateProfile();
    const screenshots = await listTradeScreenshots(profileId, tradeId);
    return NextResponse.json({ screenshots });
  } catch (err) {
    console.error("[api/journal/screenshots] GET error:", err);
    return NextResponse.json({ error: "Failed to load screenshots" }, { status: 500 });
  }
}

// POST /api/journal/screenshots — add a screenshot.
// Body: { tradeId, url, phase?, caption? }
export async function POST(request: Request) {
  const blocked = guardMutation(request, "journal-screenshots");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = await request.json().catch(() => ({}));
    const profileId = await getOrCreateProfile();
    const shot = await addTradeScreenshot(
      profileId,
      String(body.tradeId || ""),
      String(body.url || ""),
      typeof body.phase === "string" ? body.phase : null,
      typeof body.caption === "string" ? body.caption : null,
    );
    if (!shot) return NextResponse.json({ error: "Trade not found" }, { status: 404 });
    return NextResponse.json({ success: true, screenshot: shot });
  } catch (err) {
    console.error("[api/journal/screenshots] POST error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to add screenshot" },
      { status: 500 },
    );
  }
}
