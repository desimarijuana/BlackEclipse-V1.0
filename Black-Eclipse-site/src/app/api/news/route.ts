import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

// Serves news from JDDS (NewsItem table), ingested in the background by the
// news_refresh scheduler / /api/cron/run. Never fetches feeds live here —
// that keeps page loads fast and predictable.
//
// Features:
//   - search operators:  ticker:NVDA  sentiment:bearish  category:CRYPTO
//   - tickers=A,B,C      watchlist filter (My Stocks)
//   - story clustering   same-story articles from multiple sources collapse
//                        into one card with a sourceCount

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const page = Math.max(1, parseInt(searchParams.get("page") || "1", 10));
  const limit = Math.min(50, Math.max(1, parseInt(searchParams.get("limit") || "10", 10)));
  const category = searchParams.get("category");
  const region = searchParams.get("region");
  const tierParam = searchParams.get("tier");
  const sentiment = searchParams.get("sentiment");
  const ticker = searchParams.get("ticker");
  const tickersParam = searchParams.get("tickers"); // comma-separated watchlist
  const cluster = searchParams.get("cluster") !== "0"; // on by default
  const rawQ = searchParams.get("q")?.trim() || "";
  const sort = searchParams.get("sort") === "oldest" ? "asc" : "desc";

  try {
    const where: Record<string, unknown> = {};

    // ─── Search operators ────────────────────────────────────────────────
    // "ticker:NVDA fed rates" → ticker filter + free text "fed rates".
    const tokens: string[] = [];
    let opTicker = ticker;
    let opSentiment = sentiment;
    let opCategory = category;
    for (const rawTok of rawQ.split(/\s+/).filter(Boolean)) {
      const m = rawTok.match(/^(ticker|sentiment|category):(.+)$/i);
      if (!m) {
        tokens.push(rawTok);
        continue;
      }
      const [, key, val] = m;
      if (key.toLowerCase() === "ticker") opTicker = val.toUpperCase();
      else if (key.toLowerCase() === "sentiment") opSentiment = val.toLowerCase();
      else if (key.toLowerCase() === "category") opCategory = val.toUpperCase();
    }
    const q = tokens.join(" ").toLowerCase().trim();

    if (opCategory) where.category = opCategory;
    if (region) where.region = region;
    if (tierParam && !Number.isNaN(parseInt(tierParam, 10))) where.tier = parseInt(tierParam, 10);
    if (opSentiment) where.sentiment = opSentiment;
    if (opTicker) where.ticker = opTicker.toUpperCase();
    if (tickersParam) {
      const list = tickersParam.split(",").map((t) => t.trim().toUpperCase()).filter(Boolean).slice(0, 100);
      if (list.length > 0) where.ticker = { in: list };
    }
    if (q) where.OR = [{ headline: { contains: q } }, { summary: { contains: q } }];

    const [total, news, pulse] = await Promise.all([
      prisma.newsItem.count({ where }),
      prisma.newsItem.findMany({
        where,
        orderBy: { timestamp: sort },
        skip: cluster ? 0 : (page - 1) * limit,
        take: cluster ? Math.min(600, page * limit + limit * 2) : limit,
      }),
      // Market pulse: sentiment split over the last 24h (unfiltered) so the
      // bar stays stable regardless of the user's active filters.
      prisma.newsItem.groupBy({
        by: ["sentiment"],
        where: { timestamp: { gte: new Date(Date.now() - 24 * 60 * 60 * 1000) } },
        _count: { _all: true },
      }),
    ]);

    // ─── Story clustering ────────────────────────────────────────────────
    // Group near-duplicate headlines (same story, different outlets) so the
    // feed shows one card per story with "covered by N sources". Similarity:
    // word-level Jaccard over a normalized headline, threshold 0.55, only
    // within a ±36h window (old stories never absorb fresh ones).
    type Row = (typeof news)[number] & { sourceCount?: number; clusterSources?: string[] };
    let rows: Row[] = news;
    if (cluster) {
      const normalize = (h: string) =>
        h.toLowerCase().replace(/[^a-z0-9\s]/g, " ").split(/\s+/).filter((w) => w.length > 3);
      const jaccard = (a: string[], b: string[]) => {
        const sa = new Set(a);
        const sb = new Set(b);
        if (sa.size === 0 || sb.size === 0) return 0;
        let inter = 0;
        for (const w of sa) if (sb.has(w)) inter++;
        return inter / (sa.size + sb.size - inter);
      };

      const feats = rows.map((r) => normalize(r.headline));
      const used = new Array(rows.length).fill(false);
      const clustered: Row[] = [];
      for (let i = 0; i < rows.length; i++) {
        if (used[i]) continue;
        const rep = rows[i];
        const sources = new Set<string>([rep.source]);
        used[i] = true;
        const tsI = new Date(rep.timestamp).getTime();
        for (let j = i + 1; j < rows.length; j++) {
          if (used[j]) continue;
          const tsJ = new Date(rows[j].timestamp).getTime();
          if (Math.abs(tsI - tsJ) > 36 * 3600 * 1000) continue;
          if (jaccard(feats[i], feats[j]) >= 0.55) {
            used[j] = true;
            sources.add(rows[j].source);
          }
        }
        rep.sourceCount = sources.size;
        rep.clusterSources = Array.from(sources).slice(0, 5);
        clustered.push(rep);
      }
      rows = clustered;
      // Paginate AFTER clustering so every page is a full window of stories.
      const start = (page - 1) * limit;
      rows = rows.slice(start, start + limit);
    }

    const totalPages = Math.ceil(total / limit);
    const pulseMap = Object.fromEntries(pulse.map((p) => [p.sentiment, p._count._all]));

    return NextResponse.json({
      news: rows,
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