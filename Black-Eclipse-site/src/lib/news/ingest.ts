// News ingestion — fetches RSS feeds in the background, enriches each item
// (ticker via JDDS universe, sentiment via shared heuristic) and persists
// into the NewsItem table with idempotent upserts. /api/news then reads the
// DB instead of hammering ~55 feeds on every request.
//
// Called by the scheduler's news_refresh CronJob and by /api/cron/run
// (for hosted platforms without persistent processes).

import Parser from "rss-parser";
import crypto from "crypto";
import { prisma } from "@/lib/db";
import { getNewsFeeds, getConfigJSON, setConfigJSON, type NewsFeed } from "@/lib/settings";
import { checkOutboundUrl } from "@/lib/api-guard";
import { guessSentiment } from "@/lib/sentiment";
import { yieldToEventLoop } from "@/lib/db";

export const NEWS_REFRESH_TYPE = "news_refresh";
export const DEFAULT_NEWS_INTERVAL_MIN = 15;
// How many items to pull per feed (feeds typically expose 20-50).
const PER_FEED = 20;
// Prune items older than this so the DB stays bounded.
const RETENTION_DAYS = 14;
// Ticker candidates shorter than this are almost never real symbols.
const MIN_TICKER_LEN = 2;

// Several publishers (Seeking Alpha, WSJ, Economist) reject scraper
// user-agents with 403/HTML; present as a regular browser instead.
const BROWSER_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

const parser = new Parser({
  requestOptions: {
    headers: { "User-Agent": BROWSER_UA, Accept: "application/rss+xml, application/xml, text/xml, */*" },
  },
});

// Common words that look like tickers but never are. The candidate is also
// validated against the JDDS universe below, so this list only needs to
// cover the noisy cases that appear before a DB lookup is worth doing.
const TICKER_STOP_WORDS = new Set([
  "A", "I", "AN", "THE", "AND", "OR", "FOR", "CEO", "CFO", "CTO", "US", "UK",
  "EU", "UN", "FED", "SEC", "IRS", "GDP", "CPI", "IPO", "ETF", "YOY", "Q1",
  "Q2", "Q3", "Q4", "H1", "H2", "AI", "API", "APR", "AUG", "NYSE", "NASDAQ",
  "WSJ", "CNBC", "NEW", "BIG", "TOP", "ALL", "NOW", "WHY", "HOW", "GDP",
]);

function extractTickerCandidates(headline: string): string[] {
  const matches = headline.match(/\b[A-Z]{2,5}\b/g) || [];
  return matches.filter((t) => !TICKER_STOP_WORDS.has(t) && t.length >= MIN_TICKER_LEN);
}

/**
 * Validate a candidate against the live JDDS asset universe so headlines like
 * "Apple Is The Big Winner" don't invent a phantom "AAPL"-lookalike ticker.
 * Loads active symbols once per run and caches them in-module.
 */
let universeCache: { symbols: Set<string>; loadedAt: number } | null = null;
async function getUniverseSymbols(): Promise<Set<string>> {
  const TTL = 10 * 60 * 1000; // 10 min
  if (universeCache && Date.now() - universeCache.loadedAt < TTL) return universeCache.symbols;
  try {
    const assets = await prisma.asset.findMany({
      where: { isActive: true },
      select: { symbol: true },
      take: 20000,
    });
    const symbols = new Set(assets.map((a) => a.symbol.toUpperCase()));
    universeCache = { symbols, loadedAt: Date.now() };
    return symbols;
  } catch {
    return universeCache?.symbols ?? new Set();
  }
}

/** Strip HTML tags/entities and collapse whitespace for clean card text. */
export function stripHtml(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .replace(/\s+/g, " ")
    .trim();
}

function dedupKeyFor(url: string | undefined, headline: string): string {
  const base = url && url.startsWith("http") ? url : headline;
  return crypto.createHash("sha256").update(base.toLowerCase().trim()).digest("hex").slice(0, 64);
}

export interface IngestSummary {
  feeds: number;
  ok: number;
  failed: number;
  created: number;
  total: number;
}

/** Ingest one feed: parse, enrich, and upsert items. Returns created count. */
async function ingestFeed(feed: NewsFeed, universe: Set<string>): Promise<number> {
  const started = Date.now();
  try {
    const parsed = await parser.parseURL(feed.url);
    const items = (parsed.items || []).slice(0, PER_FEED);
    let created = 0;
    for (const item of items) {
      const title = item.title || "";
      if (!title) continue;
      const summary =
        stripHtml(item["content:encoded"] || item.content || item.summary || item.contentSnippet || "").slice(0, 400) ||
        (item.contentSnippet || "").slice(0, 400);
      const url = item.link || undefined;
      // Some feeds (Investing.com) emit local-time timestamps tagged as UTC, so
      // parsed dates can be hours in the future. Clamp to "now" — a future
      // timestamp would break age sorting and make every item look brand-new.
      let timestamp = item.isoDate ? new Date(item.isoDate) : new Date();
      if (timestamp.getTime() > Date.now() + 60_000) timestamp = new Date();
      const text = `${title} ${summary}`;

      // Ticker: first candidate that exists in the universe; fall back to the
      // first candidate only for crypto-feeds (BTC/ETH rarely in stock universe).
      const candidates = extractTickerCandidates(title);
      let ticker: string | undefined;
      for (const c of candidates) {
        if (universe.has(c)) {
          ticker = c;
          break;
        }
      }
      if (!ticker && feed.category === "CRYPTO" && candidates.length > 0) ticker = candidates[0];

      const key = dedupKeyFor(url, title);
      const result = await prisma.newsItem.upsert({
        where: { dedupKey: key },
        update: {},
        create: {
          dedupKey: key,
          source: feed.source,
          ticker,
          headline: title,
          summary,
          sentiment: guessSentiment(text),
          timestamp,
          url,
          category: feed.category,
          region: feed.region,
          tier: feed.tier,
        },
      });
      if (result) created++;
      // Yield periodically so bulk SQLite writes never starve HTTP requests.
      if (created % 10 === 0) await yieldToEventLoop();
    }
    await recordFeedHealth(feed, "ok", Date.now() - started);
    return created;
  } catch (err) {
    await recordFeedHealth(feed, "error", Date.now() - started, String((err as Error).message || err));
    throw err;
  }
}

let ingesting = false;

// ─── Feed health tracking ───────────────────────────────────────────────
// Persisted per feed id in SystemConfig ("news_feed_health") so the data
// settings screen can surface dead/broken feeds for pruning.

export interface FeedHealth {
  [feedId: string]: {
    status: "ok" | "error";
    lastError?: string;
    lastOkAt?: string;
    lastErrorAt?: string;
    durationMs?: number;
    consecutiveFails?: number;
  };
}

const FEED_HEALTH_KEY = "news_feed_health";

async function recordFeedHealth(feed: NewsFeed, status: "ok" | "error", durationMs: number, error?: string): Promise<void> {
  try {
    const health = await getConfigJSON<FeedHealth>(FEED_HEALTH_KEY, {});
    const prev = health[feed.id];
    health[feed.id] = {
      status,
      lastError: status === "error" ? (error || "fetch failed").slice(0, 200) : prev?.lastError,
      lastOkAt: status === "ok" ? new Date().toISOString() : prev?.lastOkAt,
      lastErrorAt: status === "error" ? new Date().toISOString() : prev?.lastErrorAt,
      durationMs,
      consecutiveFails: status === "error" ? (prev?.consecutiveFails ?? 0) + 1 : 0,
    };
    await setConfigJSON(FEED_HEALTH_KEY, health);
  } catch { /* best-effort — never break ingestion over health bookkeeping */ }
}

export async function getFeedHealth(): Promise<FeedHealth> {
  return getConfigJSON<FeedHealth>(FEED_HEALTH_KEY, {});
}

/** Run a full news ingestion cycle. Guards against concurrent runs. */
export async function runNewsIngest(): Promise<IngestSummary> {
  if (ingesting) return { feeds: 0, ok: 0, failed: 0, created: 0, total: 0 };
  ingesting = true;
  try {
    const feeds = (await getNewsFeeds()).filter(
      (f) => f.enabled && checkOutboundUrl(f.url).safe
    );
    const universe = await getUniverseSymbols();
    let ok = 0;
    let failed = 0;
    let created = 0;
    let total = 0;
    const results = await Promise.allSettled(feeds.map((f) => ingestFeed(f, universe)));
    for (let i = 0; i < results.length; i++) {
      const r = results[i];
      total++;
      if (r.status === "fulfilled") {
        ok++;
        created += r.value;
      } else {
        failed++;
        await recordFeedHealth(feeds[i], "error", 0, String(r.reason?.message || r.reason || "fetch failed").slice(0, 200));
      }
      // Yield between feed batches.
      if (i % 5 === 0) await yieldToEventLoop();
    }

    // Retention: drop items older than RETENTION_DAYS.
    const cutoff = new Date(Date.now() - RETENTION_DAYS * 24 * 60 * 60 * 1000);
    const removed = await prisma.newsItem.deleteMany({ where: { timestamp: { lt: cutoff } } });

    await prisma.cronJob.upsert({
      where: { type: NEWS_REFRESH_TYPE },
      update: { lastRunAt: new Date() },
      create: { type: NEWS_REFRESH_TYPE, lastRunAt: new Date(), intervalMinutes: DEFAULT_NEWS_INTERVAL_MIN, enabled: true },
    });

    console.log(`[NewsIngest] ${ok}/${total} feeds ok, ${created} new items, ${removed.count} pruned`);
    return { feeds: total, ok, failed, created, total: created };
  } finally {
    ingesting = false;
  }
}