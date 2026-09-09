import { NextResponse } from "next/server";
import { getOrCreateProfile, loadTrades } from "@/lib/journal/data";
import { computeJournalAnalytics } from "@/lib/journal/analytics";

export const dynamic = "force-dynamic";

// GET /api/journal/analytics — full deterministic analytics bundle.
export async function GET() {
  try {
    const profileId = await getOrCreateProfile();
    const trades = await loadTrades(profileId);
    const analytics = computeJournalAnalytics(trades);
    return NextResponse.json({ analytics });
  } catch (err) {
    console.error("[api/journal/analytics] GET error:", err);
    return NextResponse.json({ error: "Failed to compute analytics" }, { status: 500 });
  }
}
