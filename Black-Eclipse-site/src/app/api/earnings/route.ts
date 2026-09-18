import { NextResponse } from "next/server";
import { getEarningsCalendar } from "@/lib/earnings";

export const dynamic = "force-dynamic";

// GET /api/earnings — upcoming company earnings (Alpha Vantage EARNINGS_CALENDAR).
// The API key stays server-side; the client only ever sees rows + provenance.
// A missing key or provider failure returns an explicit `unavailable` state.
export async function GET() {
  try {
    const result = await getEarningsCalendar();
    return NextResponse.json(result);
  } catch (err) {
    console.error("[api/earnings] GET error:", err);
    return NextResponse.json(
      { rows: [], source: "unavailable", fetchedAt: new Date().toISOString(), reason: "Earnings fetch failed." },
      { status: 200 },
    );
  }
}
