import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import {
  scoreNewsImportance,
  type ImportanceResult,
  type NewsAlertLevel,
  type NewsConfidence,
  type NewsDirection,
  type NewsHorizon,
} from "@/lib/news/importance";
import { clusterNewsRows } from "@/lib/news/cluster";

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

/** A row plus the flattened importance fields the UI consumes. */
type ScoredNewsRow = NewsRow & {
  importance: number;
  alertLevel: NewsAlertLevel;
  importanceReasons: string[];
  isBreaking: boolean;
  confidence: NewsConfidence;
  direction: NewsDirection;
  horizon: NewsHorizon;
  invalidates: string[];
  affected: string[];
};

/** Flatten the deterministic importance result onto the row the UI receives. */
function decorate(row: NewsRow, ctx: { watchlist: string[]; portfolio: string[] }): ScoredNewsRow {
  const importance: ImportanceResult = scoreNewsImportance(row, ctx);
  return {
    ...row,
    importance: importance.score,
    alertLevel: importance.level,
    importanceReasons: importance.reasons,
    isBreaking: importance.isBreaking,
    confidence: importance.confidence,
    direction: importance.direction,
    horizon: importance.horizon,
    invalidates: importance.invalidates,
    affected: importance.affected,
  };
}

/** Run the full news query (fetch + cluster + pulse + score). Throws on DB errors. */
async function queryNews(opts: {
  where: Record<string, unknown>;
  sort: "asc" | "desc";
  page: number;
  limit: number;
  cluster: boolean;
  /** "importance" ranks the recent window by market-moving likelihood. */
  sortMode: "newest" | "importance";
  minImportance: number;
  watchlist: string[];
  portfolio: string[];
}) {
  const { where, sort, page, limit, cluster, sortMode, minImportance, watchlist, portfolio } = opts;
  const importanceMode = sortMode === "importance";
  // Importance ranking needs a wider recent window, then sorts AFTER scoring.
  // Default feed stays cheap and paginates in the DB as before.
  const takeRows = importanceMode
    ? 400
    : cluster
      ? Math.min(600, page * limit + limit * 2)
      : limit;

  const [rawTotal, news, pulse] = await Promise.all([
    prisma.newsItem.count({ where }),
    prisma.newsItem.findMany({
      where,
      orderBy: { timestamp: sort },
      skip: importanceMode || cluster ? 0 : (page - 1) * limit,
      take: takeRows,
    }),
    // Market pulse: sentiment split over the last 24h (unfiltered) so the
    // bar stays stable regardless of the user's active filters.
    prisma.newsItem.groupBy({
      by: ["sentiment"],
      where: { timestamp: { gte: new Date(Date.now() - 24 * 60 * 60 * 1000) } },
      _count: { _all: true },
    }),
  ]);

  const clustered: NewsRow[] = cluster
    ? clusterNewsRows(news as NewsRow[])
    : (news as NewsRow[]);
  const ctx = { watchlist, portfolio };

  let rows: ScoredNewsRow[];
  let total: number;
  if (importanceMode) {
    const scored = clustered
      .map((r) => decorate(r, ctx))
      .filter((r) => r.importance >= minImportance)
      .sort((a, b) => {
        const d = b.importance - a.importance;
        if (d !== 0) return d;
        return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
      });
    total = scored.length;
    const start = (page - 1) * limit;
    rows = scored.slice(start, start + limit);
  } else {
    const start = cluster ? (page - 1) * limit : 0;
    const pageRows = cluster ? clustered.slice(start, start + limit) : clustered;
    rows = pageRows.map((r) => decorate(r, ctx));
    total = cluster ? clustered.length : rawTotal;
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
  const portfolioParam = searchParams.get("portfolio"); // comma-separated holdings (context only)
  const cluster = searchParams.get("cluster") !== "0"; // on by default
  const rawQ = searchParams.get("q")?.trim() || "";
  const sortParam = searchParams.get("sort");
  const sort = sortParam === "oldest" ? "asc" : "desc";
  // "importance" ranks the recent window by market-moving likelihood; the
  // default stays chronological so the feed behaves exactly as before.
  const sortMode: "newest" | "importance" = sortParam === "importance" ? "importance" : "newest";
  const minImportance = Math.max(
    0,
    Math.min(100, parseInt(searchParams.get("minImportance") || "0", 10) || 0),
  );
  const watchlist = (tickersParam || "")
    .split(",")
    .map((t) => t.trim().toUpperCase())
    .filter(Boolean)
    .slice(0, 100);
  const portfolio = (portfolioParam || "")
    .split(",")
    .map((t) => t.trim().toUpperCase())
    .filter(Boolean)
    .slice(0, 200);

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
  if (watchlist.length > 0) {
    const list = watchlist;
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
    const result = await queryNews({
      where, sort, page, limit, cluster, sortMode, minImportance, watchlist, portfolio,
    });
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
        const result = await queryNews({
          where, sort, page, limit, cluster, sortMode, minImportance, watchlist, portfolio,
        });
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
