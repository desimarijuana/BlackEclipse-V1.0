import { NextResponse } from "next/server";
import Parser from "rss-parser";

export const dynamic = "force-dynamic";

const parser = new Parser();

// Free, open RSS feeds — no API key required.
const FEEDS = [
  { url: "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC,^IXIC,^DJI&region=US&lang=en-US", source: "Yahoo Finance" },
  { url: "https://www.coindesk.com/arc/outboundfeeds/rss/", source: "CoinDesk" },
  { url: "https://cointelegraph.com/rss", source: "CoinTelegraph" },
  { url: "https://www.cnbc.com/id/100003114/device/rss/rss.html", source: "CNBC" },
];

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

// Simple keyword-based sentiment heuristic (no external service).
function guessSentiment(text: string): "bullish" | "bearish" | "neutral" {
  const t = text.toLowerCase();
  const bull = ["surge", "gain", "rally", "record", "beat", "up", "jump", "soar", "growth", "bullish"];
  const bear = ["drop", "fall", "decline", "loss", "miss", "down", "plunge", "slump", "bearish", "crash"];
  let score = 0;
  for (const w of bull) if (t.includes(w)) score++;
  for (const w of bear) if (t.includes(w)) score--;
  if (score > 0) return "bullish";
  if (score < 0) return "bearish";
  return "neutral";
}

function extractTicker(headline: string): string | undefined {
  const match = headline.match(/\b([A-Z]{2,5})\b/);
  return match ? match[1] : undefined;
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const page = Math.max(1, parseInt(searchParams.get("page") || "1", 10));
  const limit = Math.min(50, Math.max(1, parseInt(searchParams.get("limit") || "10", 10)));

  try {
    const results = await Promise.allSettled(
      FEEDS.map(async (feed) => {
        const parsed = await parser.parseURL(feed.url);
        return (parsed.items || []).slice(0, PER_FEED).map((item, i) => {
          const title = item.title || "";
          const summary = item.contentSnippet || item.content || "";
          const raw: RawNews = {
            id: `${feed.source}-${i}`,
            source: feed.source,
            ticker: extractTicker(title),
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
    return NextResponse.json({ news: [], source: "error", pagination: { page, limit, total: 0, totalPages: 0 } }, { status: 200 });
  }
}
