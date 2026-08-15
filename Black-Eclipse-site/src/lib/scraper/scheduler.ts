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
import { runPriceScraper } from "./price-scraper";

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
  return ["US"]; // US default (crypto disabled by default)
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
    await runPriceScraper(markets, { limit: config.pageSize }); // refresh immediately on market change
  }
}

export interface ScrapeSummary {
  total: number;
  ok: number;
  failed: number;
  disabled?: boolean;
}

/**
 * Run one scrape cycle. Guards against concurrent runs.
 * options.symbols scrapes exactly those symbols (used by the dashboard for
 * page-scoped refreshes and manual per-row scraping). Without symbols the
 * cycle refreshes the first `pageSize` assets of each selected market.
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
    const markets = options.market ? [options.market] : await getConfiguredMarkets();
    const limit = options.limit ?? config.pageSize;
    const summary = await runPriceScraper(markets, {
      symbols: options.symbols,
      limit,
    });
    await prisma.cronJob.upsert({
      where: { type: "price_refresh" },
      update: {
        lastRunAt: new Date(),
        nextRunAt: new Date(Date.now() + (await getIntervalMinutes()) * 60000),
        enabled: true,
      },
      create: { type: "price_refresh", lastRunAt: new Date(), enabled: true },
    });
    return { total: summary.total, ok: summary.ok, failed: summary.failed };
  } finally {
    isRunning = false;
  }
}

let scheduledTask: ScheduledTask | null = null;

/**
 * Start the cron scheduler. Called once at app startup.
 */
export function startScheduler() {
  if (scheduledTask) return;
  const run = async () => {
    await triggerScrape();
  };
  // Poll every minute to evaluate if a refresh is due (respects interval changes).
  scheduledTask = cron.schedule("* * * * *", async () => {
    try {
      const config = await getPriceScraperConfig();
      if (config.mode === "off" || config.mode === "manual") return;
      const job = await prisma.cronJob.findUnique({ where: { type: "price_refresh" } });
      if (!job?.enabled) return;
      const lastRun = job.lastRunAt?.getTime() || 0;
      const intervalMs = job.intervalMinutes * 60000;
      if (Date.now() - lastRun >= intervalMs) {
        await run();
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
  startScheduler();
}
