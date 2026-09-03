import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

// Serves news from JDDS (NewsItem table), ingested in the background by the
// news_refresh scheduler / /api/cron/run. Never fetches feeds live here —
// that keeps page loads fast and predictable.

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const page = Math.max(1, parseInt(searchParams.get("page") || "1", 10));
  const limit = Math.min(50, Math.max(1, parseInt(searchParams.get("limit") || "10", 10)));
  const category = searchParams.get("category");
  const region = searchParams.get("region");
  const tierParam = searchParams.get("tier");
  const sentiment = searchParams.get("sentiment");
  const ticker = searchParams.get("ticker");
  const q = searchParams.get("q")?.toLowerCase().trim() || "";
  const sort = searchParams.get("sort") === "oldest" ? "asc" : "desc";

  try {
    const where: Record<string, unknown> = {};
    if (category) where.category = category;
    if (region) where.region = region;
    if (tierParam && !Number.isNaN(parseInt(tierParam, 10))) where.tier = parseInt(tierParam, 10);
    if (sentiment) where.sentiment = sentiment;
    if (ticker) where.ticker = ticker.toUpperCase();
    if (q) where.OR = [{ headline: { contains: q } }, { summary: { contains: q } }];

    const [total, news, pulse] = await Promise.all([
      prisma.newsItem.count({ where }),
      prisma.newsItem.findMany({
        where,
        orderBy: { timestamp: sort },
        skip: (page - 1) * limit,
        take: limit,
      }),
      // Market pulse: sentiment split over the last 24h (unfiltered) so the
      // bar stays stable regardless of the user's active filters.
      prisma.newsItem.groupBy({
        by: ["sentiment"],
        where: { timestamp: { gte: new Date(Date.now() - 24 * 60 * 60 * 1000) } },
        _count: { _all: true },
      }),
    ]);

    const totalPages = Math.ceil(total / limit);
    const pulseMap = Object.fromEntries(pulse.map((p) => [p.sentiment, p._count._all]));

    return NextResponse.json({
      news,
      source: "jdds",
      lastIngestAt: (await prisma.cronJob.findUnique({ where: { type: "news_refresh" } }))?.lastRunAt ?? null,
      pulse: pulseMap,
      pagination: { page, limit, total, totalPages },
    });
  } catch (err) {
    console.error("[api/news] Error:", err);
    return NextResponse.json({ news: [], source: "error", pulse: {}, pagination: { page, limit, total: 0, totalPages: 0 } }, { status: 502 });
  }
}