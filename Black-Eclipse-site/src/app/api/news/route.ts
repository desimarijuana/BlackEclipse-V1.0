import { NextResponse } from "next/server";
import Parser from "rss-parser";
import { getNewsFeeds } from "@/lib/settings";
import { checkOutboundUrl } from "@/lib/api-guard";
import { guessSentiment } from "@/lib/sentiment";

export const dynamic = "force-dynamic";
// Feed fetching is network-bound; cap it so a slow feed cannot pin the route.
export const maxDuration = 30;

const parser = new Parser();

// How many items to pull per feed (feeds typically expose 20-50).
const PER_FEED = 20;

interface RawNews {
  id: string;
  source: string;
  ticker?: string;
  timestamp: string;
  headline: string;
  summary: string;
  sentiment: "bullish" | "bearish" | "neutral";
  impactPercent: number;
  url?: string;
}

// Common words that look like tickers but never are. The candidate is also
// validated against the JDDS universe below, so this list only needs to
// cover the noisy cases that appear before a DB lookup is worth doing.
const TICKER_STOP_WORDS = new Set([
  "A", "I", "AN", "THE", "AND", "OR", "FOR", "CEO", "CFO", "CTO", "US", "UK",
  "EU", "UN", "FED", "SEC", "IRS", "GDP", "CPI", "IPO", "ETF", "YOY", "Q1",
  "Q2", "Q3", "Q4", "H1", "H2", "AI", "API", "APR", "AUG", "NYSE", "NASDAQ",
  "WSJ", "CNBC", "Reuters", "NEW", "BIG", "TOP", "ALL", "NOW", "WHY", "HOW",
]);

function extractTickerCandidates(headline: string): string[] {
  const matches = headline.match(/\b[A-Z]{2,5}\b/g) || [];
  return matches.filter((t) => !TICKER_STOP_WORDS.has(t));
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const page = Math.max(1, parseInt(searchParams.get("page") || "1", 10));
  const limit = Math.min(50, Math.max(1, parseInt(searchParams.get("limit") || "10", 10)));

  try {
    // SSRF guard: only fetch feeds whose URLs point at public http(s) hosts.
    const feeds = filterSafeFeeds(await getNewsFeeds());
    const results = await Promise.allSettled(
      feeds.map(async (feed) => {
        const parsed = await parser.parseURL(feed.url);
        return (parsed.items || []).slice(0, PER_FEED).map((item, i) => {
          const title = item.title || "";
          const summary = item.contentSnippet || item.content || "";
          const raw: RawNews = {
            id: `${feed.source}-${i}`,
            source: feed.source,
            ticker: extractTickerCandidates(title)[0],
            timestamp: item.isoDate ? new Date(item.isoDate).toLocaleString() : "recent",
            headline: title,
            summary: summary.slice(0, 300),
            sentiment: guessSentiment(`${title} ${summary}`),
            impactPercent: 0,
            url: item.link,
          };
          return raw;
        });
      })
    );

    const allNews: RawNews[] = [];
    for (const r of results) {
      if (r.status === "fulfilled") allNews.push(...r.value);
    }

    if (allNews.length === 0) {
      // Not an error per se — every feed was unreachable or empty. Keep 200
      // so the client renders an empty state instead of an error banner.
      return NextResponse.json({ news: [], source: "empty", pagination: { page, limit, total: 0, totalPages: 0 } });
    }

    // Paginate server-side.
    const total = allNews.length;
    const totalPages = Math.ceil(total / limit);
    const start = (page - 1) * limit;
    const news = allNews.slice(start, start + limit);

    return NextResponse.json({
      news,
      source: "rss",
      pagination: { page, limit, total, totalPages },
    });
  } catch (err) {
    console.error("[api/news] Error:", err);
    return NextResponse.json({ news: [], source: "error", pagination: { page, limit, total: 0, totalPages: 0 } }, { status: 502 });
  }
}

function filterSafeFeeds<T extends { url: string }>(feeds: T[]): T[] {
  return feeds.filter((f) => checkOutboundUrl(f.url).safe);
}
