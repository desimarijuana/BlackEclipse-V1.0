// Scheduler — runs price_scraper on a user-configurable interval.
// Reads the interval + mode from JDDS. In-process (runs while app runs).
import { evaluatePortfolioAlerts } from "@/lib/alerts-evaluator";
//
// Modes:
//   auto   — scraper enabled; background cycle refreshes `pageSize` stocks
//            per market, and the dashboard triggers page-scoped refreshes.
//   off    — scraper disabled; prices come from API / imported CSV only.
//   manual — no automatic scraping; the user clicks a row's price to scrape
//            just that stock on demand.

import cron, { ScheduledTask } from "node-cron";
import { prisma } from "@/lib/db";
import { runPriceScraper, refreshMarketBatch } from "./price-scraper";
import { runNewsIngest, NEWS_REFRESH_TYPE, DEFAULT_NEWS_INTERVAL_MIN } from "@/lib/news/ingest";

export type ScraperMode = "auto" | "off" | "manual";

export interface PriceScraperConfig {
  mode: ScraperMode;
  pageSize: number;
}

export const DEFAULT_INTERVAL_MIN = 15;
export const DEFAULT_PAGE_SIZE = 20;
export const DEFAULT_CONFIG: PriceScraperConfig = { mode: "auto", pageSize: DEFAULT_PAGE_SIZE };

export const CONFIG_KEY = "price_scraper_config";

let isRunning = false;
// True while the boot warm-up owns the heavy whole-market refresh path.
let warmUpBusy = false;

/** Whether a bulk background job (warm-up) currently holds the write path. */
export function isWarmUpBusy(): boolean {
  return warmUpBusy;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Current wall-clock hour (0-23) and weekday (0=Sun..6=Sat) in a timezone.
 * Returns null when the timezone is invalid — callers then treat the market
 * as always open.
 */
function localTimeIn(tz: string): { hour: number; weekday: number } | null {
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: tz,
      hour: "numeric",
      hour12: false,
      weekday: "short",
    }).formatToParts(new Date());
    const hour = Number(parts.find((p) => p.type === "hour")?.value ?? NaN);
    const wdName = parts.find((p) => p.type === "weekday")?.value ?? "";
    const weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const weekday = weekdays.indexOf(wdName);
    if (!Number.isFinite(hour) || weekday < 0) return null;
    return { hour: hour % 24, weekday };
  } catch {
    return null;
  }
}

/**
 * Whether a market is currently trading, per its stored hours/timezone.
 *
 * Conservative by design: unknown hours (open == close, e.g. TradingView-synced
 * markets), invalid timezones, and DB errors all resolve to "open" so a data
 * gap can never silently stop refreshing.
 */
export async function isMarketOpen(marketId: string): Promise<boolean> {
  try {
    const m = await prisma.market.findUnique({ where: { id: marketId } });
    if (!m || m.isCrypto) return true;
    if (m.openHour === m.closeHour) return true; // hours unknown
    // Weekend: closed unless hours say otherwise (crypto handled above).
    const t = localTimeIn(m.timezone);
    if (!t) return true;
    if (t.weekday === 0 || t.weekday === 6) return false;
    return t.hour >= m.openHour && t.hour < m.closeHour;
  } catch {
    return true;
  }
}

export async function getConfiguredMarkets(): Promise<string[]> {
  try {
    const cfg = await prisma.systemConfig.findUnique({ where: { key: "scraper_markets" } });
    if (cfg?.value) return JSON.parse(cfg.value);
  } catch {}
  // Default: every market that has assets — so newly imported universes
  // (HK/JP/SG/AU/FR/...) are automatically kept fresh without config changes.
  try {
    const rows = await prisma.market.findMany({
      where: { enabled: true },
      select: { id: true },
    });
    if (rows.length > 0) return rows.map((r) => r.id);
  } catch {}
  return ["US"]; // last-resort fallback
}

export async function getIntervalMinutes(): Promise<number> {
  try {
    const job = await prisma.cronJob.findUnique({ where: { type: "price_refresh" } });
    if (job?.enabled) return job.intervalMinutes;
  } catch {}
  return DEFAULT_INTERVAL_MIN;
}

export async function getPriceScraperConfig(): Promise<PriceScraperConfig> {
  try {
    const cfg = await prisma.systemConfig.findUnique({ where: { key: CONFIG_KEY } });
    if (cfg?.value) {
      const parsed = JSON.parse(cfg.value);
      return {
        mode: parsed.mode === "off" || parsed.mode === "manual" || parsed.mode === "auto" ? parsed.mode : "auto",
        pageSize: typeof parsed.pageSize === "number" && parsed.pageSize > 0 ? parsed.pageSize : DEFAULT_PAGE_SIZE,
      };
    }
  } catch {}
  return { ...DEFAULT_CONFIG };
}

export async function setPriceScraperConfig(config: Partial<PriceScraperConfig>): Promise<PriceScraperConfig> {
  const current = await getPriceScraperConfig();
  const next: PriceScraperConfig = {
    mode: config.mode ?? current.mode,
    pageSize: config.pageSize && config.pageSize > 0 ? config.pageSize : current.pageSize,
  };
  await prisma.systemConfig.upsert({
    where: { key: CONFIG_KEY },
    update: { value: JSON.stringify(next) },
    create: { key: CONFIG_KEY, value: JSON.stringify(next) },
  });
  restartScheduler();
  return next;
}

export async function setIntervalMinutes(minutes: number): Promise<void> {
  await prisma.cronJob.upsert({
    where: { type: "price_refresh" },
    update: { intervalMinutes: minutes, enabled: true },
    create: { type: "price_refresh", intervalMinutes: minutes, enabled: true },
  });
  restartScheduler();
}

export async function setMarkets(markets: string[]): Promise<void> {
  await prisma.systemConfig.upsert({
    where: { key: "scraper_markets" },
    update: { value: JSON.stringify(markets) },
    create: { key: "scraper_markets", value: JSON.stringify(markets) },
  });
  const config = await getPriceScraperConfig();
  if (config.mode !== "off") {
    // Refresh immediately on market change (batched per market).
    for (const market of markets) {
      await refreshMarketBatch(market, config.pageSize);
    }
  }
}

export interface ScrapeSummary {
  total: number;
  ok: number;
  failed: number;
  disabled?: boolean;
}

// Round-robin: the background cycle refreshes MARKET_BATCH_PER_TICK markets
// per tick, cycling through the configured list. TradingView markets refresh
// as a SINGLE whole-market scan (~1s), so we can do more per tick than the
// old per-symbol yfinance loop ever allowed.
const MARKET_BATCH_PER_TICK = 4;

// Markets where Yahoo has no data (PSX/NSE-dead tickers) — skipped ONLY on the
// per-symbol yfinance fallback path. TradingView covers PSX, so these markets
// ARE refreshed via the whole-market scan and no longer need hard-skipping.
// Kept for the per-symbol path only (see fetchQuoteWithFallback health).
const YAHOO_GAP_MARKETS = new Set<string>([]);

let marketCursor = 0;

/**
 * Run one scrape cycle. Guards against concurrent runs.
 * options.symbols scrapes exactly those symbols (used by the dashboard for
 * page-scoped refreshes and manual per-row scraping). Without symbols the
 * cycle refreshes a slice of the selected markets (round-robin, FULL universes).
 */
export async function triggerScrape(
  options: { market?: string; symbols?: string[]; limit?: number } = {}
): Promise<ScrapeSummary> {
  const config = await getPriceScraperConfig();
  if (config.mode === "off") {
    return { total: 0, ok: 0, failed: 0, disabled: true };
  }
  if (isRunning) return { total: 0, ok: 0, failed: 0 };
  // Never run a whole-market cycle while the universe sync is mid-flight —
  // two heavy write storms at once freeze every API route.
  if (!options.symbols && syncBusy()) {
    return { total: 0, ok: 0, failed: 0 };
  }

  // Whole-market cycles must not compete with the boot warm-up — whichever
  // started first owns the write path. Page-scoped/manual refreshes
  // (options.symbols) are tiny and stay responsive either way.
  if (!options.symbols && warmUpBusy) {
    return { total: 0, ok: 0, failed: 0 };
  }

  isRunning = true;
  try {
    const allMarkets = options.market
      ? [options.market]
      : (await getConfiguredMarkets()).filter((m) => !YAHOO_GAP_MARKETS.has(m));
    const limit = options.limit ?? (options.symbols ? config.pageSize : 0);

    let summary: { total: number; ok: number; failed: number };
    if (options.symbols) {
      // Page-scoped / manual refreshes use the existing per-symbol path.
      summary = await runPriceScraper(options.market ? [options.market] : allMarkets, {
        symbols: options.symbols,
        limit,
      });
    } else {
      // Background cycle: refresh MARKET_BATCH_PER_TICK markets per tick
      // (round-robin), each with a whole-market TradingView scan OR batched
      // bridge calls (for non-TV markets). refreshMarketBatch() routes to the
      // right path internally. Closed markets are skipped — refreshing them
      // wastes provider quota and serves frozen changePct anyway. An explicit
      // options.market (manual trigger) is always honored.
      const openMarkets: string[] = [];
      for (const market of allMarkets) {
        if (await isMarketOpen(market)) openMarkets.push(market);
      }
      if (openMarkets.length === 0) {
        return { total: 0, ok: 0, failed: 0 };
      }
      const markets = openMarkets.slice(marketCursor, marketCursor + MARKET_BATCH_PER_TICK);
      marketCursor = (marketCursor + MARKET_BATCH_PER_TICK) % Math.max(openMarkets.length, 1);
      summary = { total: 0, ok: 0, failed: 0 };
      for (const market of markets) {
        const r = await refreshMarketBatch(market, 0);
        summary.total += r.total;
        summary.ok += r.ok;
        summary.failed += r.failed;
      }
    }
    await prisma.cronJob.upsert({
      where: { type: "price_refresh" },
      update: {
        lastRunAt: new Date(),
        nextRunAt: new Date(Date.now() + (await getIntervalMinutes()) * 60000),
        enabled: true,
      },
      create: {
        type: "price_refresh",
        lastRunAt: new Date(),
        nextRunAt: new Date(Date.now() + (await getIntervalMinutes()) * 60000),
        enabled: true,
      },
    });
    return { total: summary.total, ok: summary.ok, failed: summary.failed };
  } finally {
    isRunning = false;
  }
}

let scheduledTask: ScheduledTask | null = null;

/**
 * Start the cron scheduler. Called once at app startup.
 * Self-heals the CronJob row on boot so the first tick fires.
 */
export async function startScheduler() {
  if (scheduledTask) return;
  try {
    await prisma.cronJob.upsert({
      where: { type: "price_refresh" },
      update: {},
      create: {
        type: "price_refresh",
        intervalMinutes: DEFAULT_INTERVAL_MIN,
        enabled: true,
        nextRunAt: new Date(Date.now() + DEFAULT_INTERVAL_MIN * 60000),
      },
    });
  } catch (err) {
    console.error("[Scheduler] cron job init failed:", err);
  }
  const run = async () => {
    await triggerScrape();
  };
  // Grace period after boot: don't run a heavy refresh cycle while the first
  // page loads are compiling/competing — it starves the event loop.
  const bootTime = Date.now();
  const PRICE_BOOT_GRACE_MS = 45 * 1000;
  // Poll every minute to evaluate if a refresh is due (respects interval changes).
  scheduledTask = cron.schedule("* * * * *", async () => {
    try {
      if (Date.now() - bootTime < PRICE_BOOT_GRACE_MS) return;
      const config = await getPriceScraperConfig();
      if (config.mode === "off" || config.mode === "manual") return;
      const job = await prisma.cronJob.findUnique({ where: { type: "price_refresh" } });
      // Self-heal: missing row or disabled → enable with the configured interval.
      const enabled = job?.enabled ?? true;
      if (!enabled) return;
      const lastRun = job?.lastRunAt?.getTime() || 0;
      const intervalMs = (job?.intervalMinutes ?? (await getIntervalMinutes())) * 60000;
      if (Date.now() - lastRun >= intervalMs) {
        console.log(`[Scheduler] tick: due (lastRun ${lastRun}, interval ${intervalMs}ms) — running`);
        await run();
        console.log("[Scheduler] tick: cycle complete");
      }
      // Portfolio alerts evaluate every minute against live JDDS prices so
      // triggers fire even when the user's tab is closed.
      void evaluatePortfolioAlerts();
    } catch (err) {
      console.error("[Scheduler] cycle error:", err);
    }
  });
}

export function restartScheduler() {
  if (scheduledTask) {
    scheduledTask.stop();
    scheduledTask = null;
  }
  void startScheduler();
}

// ─── Universe sync (auto-add new listings) ────────────────────────────────
// Runs on a separate daily cron. Every TradingView-covered market is scanned
// and its universe + prices upserted into JDDS, so NEW listings (IPOs) auto-
// appear and delisted symbols get deactivated after the miss threshold.

const UNIVERSE_SYNC_TYPE = "universe_sync";
const DEFAULT_SYNC_INTERVAL_MIN = 24 * 60; // daily

let syncTask: ScheduledTask | null = null;
let syncRunning = false;

/** Whether the daily universe-sync write storm is currently running. */
export function syncBusy(): boolean {
  return syncRunning;
}

/** Sync every TradingView-covered market's universe (prices + new listings). */
export async function runUniverseSync(): Promise<{
  markets: number;
  ok: number;
  created: number;
}> {
  if (syncRunning) return { markets: 0, ok: 0, created: 0 };
  // Mutual exclusion with the boot warm-up: two heavy whole-market jobs
  // writing thousands of SQLite rows at once starve every HTTP request.
  // Wait (bounded) for the warm-up to finish instead of competing with it.
  const waitStart = Date.now();
  while ((warmUpBusy || isRunning) && Date.now() - waitStart < 10 * 60 * 1000) {
    await sleep(10_000);
  }
  syncRunning = true;
  const { syncMarketUniverse } = await import("./universe-sync");
  const { isTradingViewMarket } = await import("./fetchers/tradingview");
  try {
    const allMarkets = await getConfiguredMarkets();
    const tvMarkets = allMarkets.filter((m) => isTradingViewMarket(m));
    let ok = 0;
    let created = 0;
    for (const market of tvMarkets) {
      try {
        const r = await syncMarketUniverse(market);
        ok += r.ok;
        created += r.created;
        console.log(
          `[UniverseSync] ${market}: scanned ${r.scanned}, created ${r.created}, updated ${r.updated}, deactivated ${r.deactivated}`
        );
      } catch (err) {
        console.error(`[UniverseSync] ${market} failed:`, err);
      }
      // Pause between markets so pending HTTP responses drain — back-to-back
      // whole-market write storms are what freeze the API.
      await sleep(3_000);
    }
    await prisma.cronJob.upsert({
      where: { type: UNIVERSE_SYNC_TYPE },
      update: { lastRunAt: new Date(), enabled: true },
      create: {
        type: UNIVERSE_SYNC_TYPE,
        lastRunAt: new Date(),
        intervalMinutes: DEFAULT_SYNC_INTERVAL_MIN,
        enabled: true,
      },
    });
    return { markets: tvMarkets.length, ok, created };
  } finally {
    syncRunning = false;
  }
}

/** Start the daily universe-sync cron. Called once at app startup. */
export async function startUniverseSync() {
  if (syncTask) return;
  try {
    await prisma.cronJob.upsert({
      where: { type: UNIVERSE_SYNC_TYPE },
      update: {},
      create: {
        type: UNIVERSE_SYNC_TYPE,
        intervalMinutes: DEFAULT_SYNC_INTERVAL_MIN,
        enabled: true,
      },
    });
  } catch (err) {
    console.error("[UniverseSync] init failed:", err);
  }
  // Grace period after boot: a due sync must NOT fire while the first page
  // loads are compiling routes and fetching data — thousands of synchronous
  // SQLite writes starve the event loop and freeze every API request.
  const bootTime = Date.now();
  const BOOT_GRACE_MS = 5 * 60 * 1000; // 5 minutes
  syncTask = cron.schedule("*/30 * * * *", async () => {
    try {
      if (Date.now() - bootTime < BOOT_GRACE_MS) return;
      const job = await prisma.cronJob.findUnique({ where: { type: UNIVERSE_SYNC_TYPE } });
      const enabled = job?.enabled ?? true;
      if (!enabled) return;
      const lastRun = job?.lastRunAt?.getTime() || 0;
      const intervalMs = (job?.intervalMinutes ?? DEFAULT_SYNC_INTERVAL_MIN) * 60000;
      if (Date.now() - lastRun >= intervalMs) {
        console.log("[UniverseSync] due — running daily universe sync");
        await runUniverseSync();
      }
    } catch (err) {
      console.error("[UniverseSync] cycle error:", err);
    }
  });
}

export function restartUniverseSync() {
  if (syncTask) {
    syncTask.stop();
    syncTask = null;
  }
  void startUniverseSync();
}

// ─── News ingestion (background RSS → JDDS) ─────────────────────────────
// Runs on its own cron tick so /api/news serves fresh items from the DB
// instead of re-fetching ~55 feeds live on every request.

let newsTask: ScheduledTask | null = null;
let newsRunning = false;

/** Run one news ingestion cycle (idempotent, concurrency-guarded). */
export async function triggerNewsIngest(): Promise<void> {
  if (newsRunning) return;
  newsRunning = true;
  try {
    await runNewsIngest();
  } finally {
    newsRunning = false;
  }
}

/** Start the news-refresh cron. Called once at app startup. */
export async function startNewsRefresh() {
  if (newsTask) return;
  try {
    await prisma.cronJob.upsert({
      where: { type: NEWS_REFRESH_TYPE },
      update: { intervalMinutes: DEFAULT_NEWS_INTERVAL_MIN },
      create: {
        type: NEWS_REFRESH_TYPE,
        intervalMinutes: DEFAULT_NEWS_INTERVAL_MIN,
        enabled: true,
        nextRunAt: new Date(Date.now() + DEFAULT_NEWS_INTERVAL_MIN * 60000),
      },
    });
  } catch (err) {
    console.error("[NewsRefresh] init failed:", err);
  }
  const bootTime = Date.now();
  const BOOT_GRACE_MS = 30 * 1000;
  newsTask = cron.schedule("* * * * *", async () => {
    try {
      if (Date.now() - bootTime < BOOT_GRACE_MS) return;
      const job = await prisma.cronJob.findUnique({ where: { type: NEWS_REFRESH_TYPE } });
      const enabled = job?.enabled ?? true;
      if (!enabled) return;
      const lastRun = job?.lastRunAt?.getTime() || 0;
      const intervalMs = (job?.intervalMinutes ?? DEFAULT_NEWS_INTERVAL_MIN) * 60000;
      if (Date.now() - lastRun >= intervalMs) {
        console.log("[NewsRefresh] due — ingesting feeds");
        await triggerNewsIngest();
      }
    } catch (err) {
      console.error("[NewsRefresh] cycle error:", err);
    }
  });
}

export function restartNewsRefresh() {
  if (newsTask) {
    newsTask.stop();
    newsTask = null;
  }
  void startNewsRefresh();
}

/**
 * Pre-warm JDDS after server boot so the moment a user clicks a country every
 * row already has a live price.
 *
 * Responsiveness rules (learned the hard way — this used to freeze the whole
 * site for minutes):
 *   - Waits `delayMs` before starting, so the first page loads never compete
 *     with bulk writes.
 *   - Only warms OPEN markets (per stored hours/timezone). Closed markets are
 *     picked up by the scheduled cycle when they open.
 *   - Yields to user-triggered scrapes: if a manual scrape starts mid-warm-up,
 *     the warm-up pauses until it finishes.
 *   - Sleeps between markets so the event loop (and node-cron) can breathe.
 */
export async function warmUpAllMarkets(options: { delayMs?: number } = {}) {
  // Dev guard: bulk boot warm-up hammers SQLite and starves first page loads.
  // Opt in with BE_WARMUP=1 when you actually want dev prices prewarmed.
  if (process.env.NODE_ENV !== "production" && process.env.BE_WARMUP !== "1") {
    console.log("[WarmUp] skipped in dev (set BE_WARMUP=1 to enable)");
    return;
  }
  const delayMs = options.delayMs ?? 20_000;
  if (delayMs > 0) await sleep(delayMs);
  // Let an already-running universe sync finish first — the two jobs
  // together would block the event loop for minutes.
  const waitStart = Date.now();
  while (syncRunning && Date.now() - waitStart < 10 * 60 * 1000) {
    await sleep(10_000);
  }
  if (warmUpBusy || isRunning) return;
  warmUpBusy = true;
  try {
    const allMarkets = (await getConfiguredMarkets()).filter((m) => !YAHOO_GAP_MARKETS.has(m));

    // Only open markets need pricing right now — refreshing a closed market
    // wastes provider quota and blocks the loop for nothing.
    const openMarkets: string[] = [];
    for (const market of allMarkets) {
      if (await isMarketOpen(market)) openMarkets.push(market);
    }

    const started = Date.now();
    console.log(`[WarmUp] warming ${openMarkets.length}/${allMarkets.length} OPEN markets (skipping closed)...`);
    let total = 0;
    for (const market of openMarkets) {
      // Defer to explicit user-triggered scrapes; they take priority.
      while (isRunning) {
        await sleep(2_000);
      }
      try {
        const unpriced = await prisma.asset.count({
          where: { marketId: market, isActive: true, price: { is: null } },
        });
        // Full universe when rows are missing; otherwise a shallow keep-fresh
        // pass. Cap the full-universe pass at 1000 rows: a boot warm-up that
        // scans 5k+ symbols (CN/JP/KR/DE...) hammers SQLite for minutes and
        // freezes every API route. The scheduled cycle covers the rest.
        const r = await refreshMarketBatch(market, unpriced > 0 ? Math.min(1000, unpriced) : 20);
        total += r.ok;
        console.log(`[WarmUp] ${market}: ${r.ok}/${r.total} priced`);
      } catch (err) {
        console.error(`[WarmUp] ${market} failed:`, err);
      }
      // Let queued HTTP requests and timers run before the next heavy batch.
      // Longer pause: bulk writes are synchronous and starve in-flight requests.
      await sleep(4_000);
    }
    console.log(`[WarmUp] done in ${((Date.now() - started) / 1000).toFixed(0)}s — ${total} prices written`);
    await prisma.cronJob.upsert({
      where: { type: "price_refresh" },
      update: { lastRunAt: new Date(), enabled: true },
      create: { type: "price_refresh", lastRunAt: new Date(), intervalMinutes: DEFAULT_INTERVAL_MIN, enabled: true },
    });
  } catch (err) {
    console.error("[WarmUp] failed:", err);
  } finally {
    warmUpBusy = false;
  }
}
