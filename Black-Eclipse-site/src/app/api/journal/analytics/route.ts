import { NextResponse } from "next/server";
import { getOrCreateProfile, loadTrades, getProfile } from "@/lib/journal/data";
import { computeJournalAnalytics } from "@/lib/journal/analytics";

export const dynamic = "force-dynamic";

// GET /api/journal/analytics — full deterministic analytics bundle. Reads the
// trader's settings so currency equity reflects account size / risk-per-trade.
export async function GET() {
  try {
    const profileId = await getOrCreateProfile();
    const [trades, profile] = await Promise.all([loadTrades(profileId), getProfile(profileId)]);
    const analytics = computeJournalAnalytics(trades, {
      accountSize: profile?.accountSize ?? null,
      riskPerTrade: profile?.riskPerTrade ?? null,
    });
    return NextResponse.json({ analytics });
  } catch (err) {
    console.error("[api/journal/analytics] GET error:", err);
    return NextResponse.json({ error: "Failed to compute analytics" }, { status: 500 });
  }
}
