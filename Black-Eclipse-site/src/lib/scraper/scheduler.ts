// Scheduler — runs price_scraper on a user-configurable interval.
// Reads the interval + mode from JDDS. In-process (runs while app runs).
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
      // right path internally.
      const markets = allMarkets.slice(marketCursor, marketCursor + MARKET_BATCH_PER_TICK);
      marketCursor = (marketCursor + MARKET_BATCH_PER_TICK) % Math.max(allMarkets.length, 1);
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
  // Poll every minute to evaluate if a refresh is due (respects interval changes).
  scheduledTask = cron.schedule("* * * * *", async () => {
    try {
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

/** Sync every TradingView-covered market's universe (prices + new listings). */
export async function runUniverseSync(): Promise<{
  markets: number;
  ok: number;
  created: number;
}> {
  if (syncRunning) return { markets: 0, ok: 0, created: 0 };
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
  syncTask = cron.schedule("*/30 * * * *", async () => {
    try {
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

/**
 * Pre-warm JDDS at server boot: price every market's full universe in the
 * background (chunked bridge calls), so the moment a user clicks a country
 * every row already has a live price. Fails silently — the cron cycle keeps
 * everything fresh afterwards. Also marks the CronJob row as just-run so the
 * first scheduled tick doesn't double-work.
 *
 * Markets that already have prices for every asset get a quick shallow keep
 * (page-size) pass — deep refresh is left to the round-robin cycle — so boot
 * warm-up finishes in a couple of minutes, not a half hour.
 */
export async function warmUpAllMarkets() {
  try {
    const markets = (await getConfiguredMarkets()).filter((m) => !YAHOO_GAP_MARKETS.has(m));
    const started = Date.now();
    console.log(`[WarmUp] pricing ${markets.length} markets (full universes)...`);
    let total = 0;
    for (const market of markets) {
      const unpriced = await prisma.asset.count({
        where: { marketId: market, isActive: true, price: { is: null } },
      });
      // Full universe when rows are missing; otherwise a shallow keep-fresh pass.
      const r = await refreshMarketBatch(market, unpriced > 0 ? 0 : 20);
      total += r.ok;
      console.log(`[WarmUp] ${market}: ${r.ok}/${r.total} priced`);
    }
    console.log(`[WarmUp] done in ${((Date.now() - started) / 1000).toFixed(0)}s — ${total} prices written`);
    await prisma.cronJob.upsert({
      where: { type: "price_refresh" },
      update: { lastRunAt: new Date(), enabled: true },
      create: { type: "price_refresh", lastRunAt: new Date(), intervalMinutes: DEFAULT_INTERVAL_MIN, enabled: true },
    });
  } catch (err) {
    console.error("[WarmUp] failed:", err);
  }
}
