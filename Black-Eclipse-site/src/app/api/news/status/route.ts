import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { getFeedHealth, NEWS_REFRESH_TYPE, DEFAULT_NEWS_INTERVAL_MIN } from "@/lib/news/ingest";
import { getNewsFeeds } from "@/lib/settings";

export const dynamic = "force-dynamic";

// GET /api/news/status — ingestion health for the data settings screen:
// last run, item counts, and per-feed ok/error breakdown.

export async function GET() {
  try {
    const [job, health, feeds, totalItems, lastItem] = await Promise.all([
      prisma.cronJob.findUnique({ where: { type: NEWS_REFRESH_TYPE } }),
      getFeedHealth(),
      getNewsFeeds(),
      prisma.newsItem.count(),
      prisma.newsItem.findFirst({ orderBy: { timestamp: "desc" }, select: { timestamp: true } }),
    ]);

    const feedRows = feeds.map((f) => ({
      id: f.id,
      source: f.source,
      category: f.category,
      tier: f.tier,
      enabled: f.enabled,
      health: health[f.id] ?? null,
    }));

    return NextResponse.json({
      enabled: job?.enabled ?? true,
      intervalMinutes: job?.intervalMinutes ?? DEFAULT_NEWS_INTERVAL_MIN,
      lastRunAt: job?.lastRunAt ?? null,
      nextRunAt: job?.nextRunAt ?? null,
      totalItems,
      newestItemAt: lastItem?.timestamp ?? null,
      feeds: feedRows,
      failing: feedRows.filter((f) => f.health?.status === "error" && (f.health.consecutiveFails ?? 0) >= 3).length,
    });
  } catch (err) {
    console.error("[api/news/status] Error:", err);
    return NextResponse.json({ error: "failed to load news status" }, { status: 500 });
  }
}