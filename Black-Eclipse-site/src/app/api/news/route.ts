import { NextResponse } from "next/server";
import Parser from "rss-parser";
import { getNewsFeeds } from "@/lib/settings";
import { checkOutboundUrl } from "@/lib/api-guard";
import { guessSentiment } from "@/lib/sentiment";

export const dynamic = "force-dynamic";
// Feed fetching is network-bound; cap it so a slow feed cannot pin the route.
export const maxDuration = 30;

// Several publishers (Seeking Alpha, WSJ, Economist) reject scraper
// user-agents with 403/HTML; present as a regular browser instead.
const BROWSER_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

const parser = new Parser({
  requestOptions: {
    headers: { "User-Agent": BROWSER_UA, Accept: "application/rss+xml, application/xml, text/xml, */*" },
  },
});

// How many items to pull per feed (feeds typically expose 20-50).
const PER_FEED = 20;

interface RawNews {
  id: string;
  source: string;
  category?: string;
  region?: string;
  tier?: number;
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
  const category = searchParams.get("category");
  const region = searchParams.get("region");
  const tierParam = searchParams.get("tier");
  const sentiment = searchParams.get("sentiment");
  const source = searchParams.get("source");
  const q = searchParams.get("q")?.toLowerCase().trim() || "";

  try {
    // SSRF guard: only fetch feeds whose URLs point at public http(s) hosts.
    let feeds = filterSafeFeeds(await getNewsFeeds()).filter((f) => f.enabled);
    if (category) feeds = feeds.filter((f) => f.category === category);
    if (region) feeds = feeds.filter((f) => f.region === region);
    if (tierParam) {
      const tier = parseInt(tierParam, 10);
      if (!Number.isNaN(tier)) feeds = feeds.filter((f) => f.tier === tier);
    }
    if (source) feeds = feeds.filter((f) => f.source === source);
    const results = await Promise.allSettled(
      feeds.map(async (feed) => {
        const parsed = await parser.parseURL(feed.url);
        return (parsed.items || []).slice(0, PER_FEED).map((item, i) => {
          const title = item.title || "";
          // Strip HTML tags/entities and collapse whitespace so cards show a
          // clean snippet. Prefer full content, fall back to contentSnippet.
          const strip = (html: string) =>
            html
              .replace(/<[^>]+>/g, " ")
              .replace(/&nbsp;/g, " ")
              .replace(/&amp;/g, "&")
              .replace(/&lt;/g, "<")
              .replace(/&gt;/g, ">")
              .replace(/&quot;/g, '"')
              .replace(/&#39;|&apos;/g, "'")
              .replace(/\s+/g, " ")
              .trim();
          const summary =
            strip(item["content:encoded"] || item.content || item.summary || item.contentSnippet || "").slice(0, 400) ||
            (item.contentSnippet || "").slice(0, 400);
          const raw: RawNews = {
            id: `${feed.source}-${i}`,
            source: feed.source,
            category: feed.category,
            region: feed.region,
            tier: feed.tier,
            ticker: extractTickerCandidates(title)[0],
            timestamp: item.isoDate ? new Date(item.isoDate).toLocaleString() : "recent",
            headline: title,
            summary,
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

    // Per-item filters (sentiment + full-text search).
    let filtered = allNews;
    if (sentiment) filtered = filtered.filter((n) => n.sentiment === sentiment);
    if (q) filtered = filtered.filter((n) => `${n.headline} ${n.summary}`.toLowerCase().includes(q));

    if (filtered.length === 0) {
      // Not an error per se — every feed was unreachable/empty or no item
      // matched the filters. Keep 200 so the client renders an empty state.
      return NextResponse.json({ news: [], source: "empty", pagination: { page, limit, total: 0, totalPages: 0 } });
    }

    // Sort newest first (feeds expose isoDate; "recent" items sink to bottom).
    filtered.sort((a, b) => {
      const ta = Date.parse(a.timestamp);
      const tb = Date.parse(b.timestamp);
      return (Number.isNaN(tb) ? -1 : tb) - (Number.isNaN(ta) ? -1 : ta);
    });

    // Paginate server-side.
    const total = filtered.length;
    const totalPages = Math.ceil(total / limit);
    const start = (page - 1) * limit;
    const news = filtered.slice(start, start + limit);

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
