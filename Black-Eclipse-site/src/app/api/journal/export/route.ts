import { NextResponse } from "next/server";
import { getOrCreateProfile, loadTrades } from "@/lib/journal/data";
import { tradesToCsv } from "@/lib/journal/export";

export const dynamic = "force-dynamic";

// GET /api/journal/export?format=csv — download the full journal as CSV.
export async function GET() {
  try {
    const profileId = await getOrCreateProfile();
    const trades = await loadTrades(profileId);
    const csv = tradesToCsv(trades);
    const stamp = new Date().toISOString().slice(0, 10);
    return new NextResponse(csv, {
      status: 200,
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": `attachment; filename="trading-journal-${stamp}.csv"`,
        "Cache-Control": "no-store",
      },
    });
  } catch (err) {
    console.error("[api/journal/export] GET error:", err);
    return NextResponse.json({ error: "Failed to export trades" }, { status: 500 });
  }
}
