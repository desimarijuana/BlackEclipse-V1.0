import { NextResponse } from "next/server";
import { getOrCreateProfile, loadTrades } from "@/lib/journal/data";
import { buildRecentWeeklyReviews } from "@/lib/journal/analytics/weekly";
import { buildMonthlyWrapped } from "@/lib/journal/analytics/wrapped";

export const dynamic = "force-dynamic";

// GET /api/journal/reviews
// Query params:
//   type=weekly   -> { weeks: WeeklyReview[] } (last 4 weeks)
//   type=monthly  -> { wrapped: MonthlyWrapped } (current month)
export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const type = searchParams.get("type") ?? "weekly";
    const profileId = await getOrCreateProfile();
    const trades = await loadTrades(profileId);

    if (type === "monthly") {
      const year = Number(searchParams.get("year")) || new Date().getUTCFullYear();
      const month = Number(searchParams.get("month")) || new Date().getUTCMonth();
      const wrapped = buildMonthlyWrapped(trades, year, month);
      return NextResponse.json({ wrapped });
    }

    // weekly — last 4 weeks
    const weeks = buildRecentWeeklyReviews(trades, 4);
    return NextResponse.json({ weeks });
  } catch (err) {
    console.error("[api/journal/reviews] GET error:", err);
    return NextResponse.json({ error: "Failed to load reviews" }, { status: 500 });
  }
}
