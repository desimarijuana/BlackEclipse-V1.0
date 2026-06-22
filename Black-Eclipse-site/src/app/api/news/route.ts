import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

interface NewsItem {
  id: string;
  source: string;
  ticker?: string;
  timestamp: string;
  headline: string;
  summary: string;
  sentiment: 'bullish' | 'bearish' | 'neutral';
  impactPercent: number;
  url?: string;
}

function getRelativeTime(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${diffDays}d ago`;
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const page = parseInt(searchParams.get("page") || "1", 10);
    const limit = parseInt(searchParams.get("limit") || "10", 10);

    const startIndex = (page - 1) * limit;

    // Fetch total news articles count from DB
    const totalCount = await prisma.newsArticle.count();

    // Query news articles directly from PostgreSQL, ordered by publication date descending
    const dbArticles = await prisma.newsArticle.findMany({
      orderBy: { publishedAt: "desc" },
      skip: startIndex,
      take: limit,
    });

    const newsItems: NewsItem[] = dbArticles.map((art) => ({
      id: art.id,
      source: art.source,
      ticker: art.ticker || undefined,
      timestamp: getRelativeTime(new Date(art.publishedAt)),
      headline: art.headline,
      summary: art.summary,
      sentiment: art.sentiment as 'bullish' | 'bearish' | 'neutral',
      impactPercent: art.impactPercent,
      url: art.url || undefined
    }));

    return NextResponse.json({
      news: newsItems,
      pagination: {
        page,
        limit,
        totalItems: totalCount,
        totalPages: Math.ceil(totalCount / limit)
      }
    });

  } catch (err: any) {
    console.error("[api/news] General error:", err);
    return NextResponse.json({ error: "Failed to load cached news feed" }, { status: 500 });
  }
}
