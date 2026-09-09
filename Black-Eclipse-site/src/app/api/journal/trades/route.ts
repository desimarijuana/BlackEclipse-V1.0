import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { getOrCreateProfile, createTrade, loadTrades } from "@/lib/journal/data";

export const dynamic = "force-dynamic";

// GET /api/journal/trades — list all trades for the profile.
export async function GET() {
  try {
    const profileId = await getOrCreateProfile();
    const trades = await loadTrades(profileId);
    return NextResponse.json({ trades });
  } catch (err) {
    console.error("[api/journal/trades] GET error:", err);
    return NextResponse.json({ error: "Failed to load trades" }, { status: 500 });
  }
}

// POST /api/journal/trades — create a trade.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "journal-trades");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = await request.json().catch(() => ({}));
    const profileId = await getOrCreateProfile();
    const trade = await createTrade(profileId, body);
    return NextResponse.json({ success: true, trade });
  } catch (err) {
    console.error("[api/journal/trades] POST error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to create trade" },
      { status: 500 }
    );
  }
}
