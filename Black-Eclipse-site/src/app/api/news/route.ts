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

type NewsRow = {
  id: string;
  source: string;
  ticker?: string | null;
  headline: string;
  summary?: string | null;
  sentiment: string;
  timestamp: Date;
  url?: string | null;
  category?: string | null;
  region?: string | null;
  tier?: number | null;
  sourceCount?: number;
  clusterSources?: string[];
};

/** Group near-duplicate headlines (same story, different outlets) so the feed
 *  shows one card per story with "covered by N sources". Similarity: word-level
 *  Jaccard over a normalized headline, threshold 0.55, only within a ±36h window. */
function clusterRows(rows: NewsRow[], page: number, limit: number): { rows: NewsRow[]; total: number } {
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
  const clustered: NewsRow[] = [];
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
  // Paginate AFTER clustering so every page is a full window of stories.
  const start = (page - 1) * limit;
  return { rows: clustered.slice(start, start + limit), total: clustered.length };
}

/** Run the full news query (fetch + cluster + pulse + score). Throws on DB errors. */
async function queryNews(opts: {
  where: Record<string, unknown>;
  sort: "asc" | "desc";
  page: number;
  limit: number;
  cluster: boolean;
}) {
  const { where, sort, page, limit, cluster } = opts;
  const [rawTotal, news, pulse] = await Promise.all([
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

  let rows: NewsRow[] = news as NewsRow[];
  let total = rawTotal;
  if (cluster) {
    const c = clusterRows(rows, page, limit);
    rows = c.rows;
    total = c.total;
  }

  const totalPages = Math.ceil(total / limit);
  const pulseMap = Object.fromEntries(pulse.map((p) => [p.sentiment, p._count._all]));

  // ─── News sentiment score (drives the app-wide aurora glow) ──────────
  // Raw bullish-vs-bearish counts over-weighted Tier-4 blogs that churn
  // dozens of hot-take posts. The 24h pulse is now tier-weighted
  // (T1 wires ×4 … T4 blogs ×1) so a wire flash outweighs a blog pile-on.
  const pulse24h = await prisma.newsItem.groupBy({
    by: ["sentiment", "tier"],
    where: { timestamp: { gte: new Date(Date.now() - 24 * 60 * 60 * 1000) } },
    _count: { _all: true },
  });
  const TIER_W: Record<number, number> = { 1: 4, 2: 2.5, 3: 1.5, 4: 1 };
  let wBull = 0;
  let wBear = 0;
  for (const g of pulse24h) {
    const w = TIER_W[g.tier ?? 3] ?? 1.5;
    if (g.sentiment === "bullish") wBull += g._count._all * w;
    else if (g.sentiment === "bearish") wBear += g._count._all * w;
  }
  const wTotal = wBull + wBear;
  const newsScore = wTotal > 0 ? (wBull - wBear) / wTotal : 0;

  return {
    rows,
    total,
    totalPages,
    pulseMap,
    newsScore: +newsScore.toFixed(3),
  };
}

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
    if (list.length > 0) {
      // Match either the enriched ticker OR the symbol/company name
      // appearing in the headline text, so "Apple rises 7%" shows even
      // before the ticker enrichment backfills.
      const nameMap: Record<string, string> = {
        AAPL: "apple", MSFT: "microsoft", NVDA: "nvidia", TSLA: "tesla",
        AMZN: "amazon", GOOGL: "google", META: "meta", NFLX: "netflix",
        INTC: "intel", AMD: "amd", ORCL: "oracle", AVGO: "broadcom",
        COIN: "coinbase", PLTR: "palantir", HOOD: "robinhood",
      };
      const or: Array<Record<string, unknown>> = [{ ticker: { in: list } }];
      for (const t of list) {
        if (nameMap[t]) or.push({ headline: { contains: nameMap[t] } });
      }
      where.OR = or;
    }
  }
  if (q) where.OR = [{ headline: { contains: q } }, { summary: { contains: q } }];

  try {
    const result = await queryNews({ where, sort, page, limit, cluster });
    return NextResponse.json({
      news: result.rows,
      source: "jdds",
      lastIngestAt: (await prisma.cronJob.findUnique({ where: { type: "news_refresh" } }))?.lastRunAt ?? null,
      pulse: result.pulseMap,
      newsScore: result.newsScore,
      pagination: { page, limit, total: result.total, totalPages: result.totalPages },
    });
  } catch (err) {
    // Distinguish a corrupt/unavailable DB from a transient query error so the
    // UI can surface actionable guidance instead of a generic "try again".
    const msg = String((err as Error)?.message || err);
    const dbCorrupt = /malformed|disk image|no such table|no such column/i.test(msg);
    console.error("[api/news] Error:", err);

    // Runtime self-heal: if the DB is corrupt, trigger db-guard to repair it
    // in place (rolling backup → git snapshot → prisma db push) and retry once.
    // This recovers the feed WITHOUT requiring a server restart.
    if (dbCorrupt) {
      try {
        const { execFile } = await import("child_process");
        const { promisify } = await import("util");
        const path = await import("path");
        const execFileP = promisify(execFile);
        const guardScript = path.join(process.cwd(), "scripts", "db-guard.js");
        await execFileP(process.execPath, [guardScript, "repair"], { timeout: 120_000 });
        console.log("[api/news] db-guard repair completed — retrying query");
        const result = await queryNews({ where, sort, page, limit, cluster });
        return NextResponse.json({
          news: result.rows,
          source: "jdds",
          lastIngestAt: (await prisma.cronJob.findUnique({ where: { type: "news_refresh" } }))?.lastRunAt ?? null,
          pulse: result.pulseMap,
          newsScore: result.newsScore,
          pagination: { page, limit, total: result.total, totalPages: result.totalPages },
        });
      } catch (repairErr) {
        console.error("[api/news] auto-repair failed:", repairErr);
      }
    }

    return NextResponse.json(
      {
        news: [],
        source: "error",
        pulse: {},
        error: dbCorrupt
          ? "The news database is corrupt — restart the site (db-guard will repair it automatically)."
          : "Could not read the news database.",
        pagination: { page, limit, total: 0, totalPages: 0 },
      },
      { status: 502 }
    );
  }
}
