import { NextResponse } from "next/server";
import { getIntervalMinutes, setIntervalMinutes, setMarkets, getConfiguredMarkets } from "@/lib/scraper";
import { guardMutation } from "@/lib/api-guard";
import { NEWS_REFRESH_TYPE } from "@/lib/news/ingest";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

// GET /api/cron — current interval + selected markets.
export async function GET() {
  try {
    const [intervalMinutes, markets] = await Promise.all([getIntervalMinutes(), getConfiguredMarkets()]);
    return NextResponse.json({ intervalMinutes, markets });
  } catch (err) {
    console.error("[api/cron] GET error:", err);
    return NextResponse.json({ error: "Failed to load cron config" }, { status: 500 });
  }
}

// POST /api/cron — set interval and/or markets.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "cron");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = await request.json();
    const { intervalMinutes, markets } = body;

    if (typeof intervalMinutes === "number" && intervalMinutes > 0) {
      await setIntervalMinutes(intervalMinutes);
      // Keep the news-refresh cron on the same cadence.
      await prisma.cronJob.upsert({
        where: { type: NEWS_REFRESH_TYPE },
        update: { intervalMinutes, enabled: true },
        create: { type: NEWS_REFRESH_TYPE, intervalMinutes, enabled: true },
      });
    }
    if (Array.isArray(markets) && markets.length > 0) {
      await setMarkets(markets);
    }

    const [currentInterval, currentMarkets] = await Promise.all([getIntervalMinutes(), getConfiguredMarkets()]);
    return NextResponse.json({ success: true, intervalMinutes: currentInterval, markets: currentMarkets });
  } catch (err) {
    console.error("[api/cron] POST error:", err);
    return NextResponse.json({ error: "Failed to save cron config" }, { status: 500 });
  }
}
