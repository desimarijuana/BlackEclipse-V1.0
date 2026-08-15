import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import {
  triggerScrape,
  getConfiguredMarkets,
  getIntervalMinutes,
  getPriceScraperConfig,
  setPriceScraperConfig,
  type PriceScraperConfig,
} from "@/lib/scraper";

export const dynamic = "force-dynamic";

// GET /api/scraper — returns current status, mode config, and source health.
export async function GET() {
  try {
    const [markets, interval, config, job] = await Promise.all([
      getConfiguredMarkets(),
      getIntervalMinutes(),
      getPriceScraperConfig(),
      prisma.cronJob.findUnique({ where: { type: "price_refresh" } }),
    ]);

    const sourceHealth = await prisma.sourceHealth.groupBy({
      by: ["source", "market"],
      _sum: { successCount: true, failCount: true },
      _max: { lastStatus: true },
    });

    return NextResponse.json({
      markets,
      intervalMinutes: interval,
      enabled: config.mode !== "off",
      mode: config.mode,
      pageSize: config.pageSize,
      config,
      lastRunAt: job?.lastRunAt || null,
      nextRunAt: job?.nextRunAt || null,
      sourceHealth,
    });
  } catch (err) {
    console.error("[api/scraper] GET error:", err);
    return NextResponse.json({ error: "Failed to load scraper status" }, { status: 500 });
  }
}

// POST /api/scraper — trigger a scrape.
// Body (all optional):
//   { market?: string }                 — scrape first `pageSize` assets of a market
//   { symbols?: string[] }              — scrape exactly these symbols (manual / page refresh)
//   { config?: { mode, pageSize } }     — update the mode config and persist it
export async function POST(request: Request) {
  try {
    const body = await request.json().catch(() => ({}));
    const { market, symbols, limit, config } = body;

    if (config) {
      const cfg: Partial<PriceScraperConfig> = {};
      if (config.mode === "auto" || config.mode === "off" || config.mode === "manual") {
        cfg.mode = config.mode;
      }
      if (typeof config.pageSize === "number" && config.pageSize > 0) {
        cfg.pageSize = config.pageSize;
      }
      if (cfg.mode || cfg.pageSize) {
        await setPriceScraperConfig(cfg);
      }
    }

    // A scrape runs only when explicitly requested. Config-only calls (mode /
    // page-size changes) just persist and return.
    const hasScrapeParams =
      (Array.isArray(symbols) && symbols.length > 0) ||
      typeof market === "string" ||
      typeof limit === "number";
    const wantsScrape = hasScrapeParams || Object.keys(body).length === 0;

    if (!wantsScrape) {
      return NextResponse.json({ success: true, total: 0, ok: 0, failed: 0 });
    }

    const summary = await triggerScrape(
      Array.isArray(symbols) && symbols.length > 0
        ? { market: typeof market === "string" ? market : undefined, symbols }
        : { market: typeof market === "string" ? market : undefined, limit: typeof limit === "number" ? limit : undefined }
    );

    return NextResponse.json({ success: true, ...summary });
  } catch (err) {
    console.error("[api/scraper] POST error:", err);
    return NextResponse.json({ error: "Failed to trigger scrape" }, { status: 500 });
  }
}
