// price_scraper — the self-healing web scraping agent.
// Loop: SCRAPE → DETECT → DIAGNOSE → RECOVER → LEARN → SERVE.
//
// For each selected market, it scrapes prices for that market's assets,
// stores them in JDDS, and learns source reliability so it self-heals.

import { prisma, yieldToEventLoop } from "@/lib/db";
import { MARKET_SEEDS } from "./markets";
import { fetchQuoteWithFallback } from "./fetchers";
import { fetchYahooBatchQuote } from "./fetchers/yfinance";
import { isTradingViewMarket } from "./fetchers/tradingview";
import { syncMarketUniverse } from "./universe-sync";
import type { FetchResult, ScrapeOutcome } from "./types";

// Rows per transaction when persisting quote batches — small chunks plus
// event-loop yields keep bulk writes from stalling live requests.
const WRITE_CHUNK = 250;

/**
 * Seed JDDS with markets + assets that aren't yet present.
 * Idempotent — safe to run on every start.
 */
export async function seedUniverse(markets: string[] = ["US", "CRYPTO"]) {
  for (const seed of MARKET_SEEDS) {
    if (!markets.includes(seed.id)) continue;

    const market = await prisma.market.upsert({
      where: { id: seed.id },
      update: { enabled: true },
      create: {
        id: seed.id,
        country: seed.country,
        exchange: seed.exchange,
        timezone: seed.timezone,
        openHour: seed.openHour,
        closeHour: seed.closeHour,
        isCrypto: seed.isCrypto,
      },
    });

    // Best-effort per symbol: a transient SQLite lock (Prisma P1008) on one
    // row must not abort the entire seed. The seed is idempotent and runs on
    // every boot and every scrape cycle, so a later pass heals any skips.
    for (const s of seed.symbols) {
      try {
        await prisma.asset.upsert({
          where: { marketId_symbol: { marketId: market.id, symbol: s.symbol } },
          update: { name: s.name, sector: s.sector, industry: s.industry, isActive: true },
          create: {
            symbol: s.symbol,
            name: s.name,
            sector: s.sector,
            industry: s.industry,
            marketId: market.id,
          },
        });
      } catch (err) {
        console.warn(`[seedUniverse] skipping ${market.id}:${s.symbol} — ${(err as Error).message}`);
        break; // DB is busy; stop this market and let a later pass finish it.
      }
      // Let queued HTTP requests run between writes — seeding is a bulk,
      // synchronous-SQLite write path that must never starve the web server.
      if (seed.symbols.length > 40) await yieldToEventLoop();
    }
  }
}

/**
 * Record a scrape outcome into SourceHealth (the self-healing memory).
 *
 * Health is tracked per (source × market) with the wildcard symbol '*'
 * instead of per symbol: one row per source/market bounds table growth and
 * matches how shouldUseStrategy() reads it. The counter updates are atomic
 * increments, so concurrent scrapes can't clobber each other.
 */
async function learn(outcome: ScrapeOutcome) {
  try {
    const id = `${outcome.source}:${outcome.market}:*`;
    await prisma.sourceHealth.upsert({
      where: { id },
      create: {
        id,
        source: outcome.source,
        market: outcome.market,
        symbol: "*",
        successCount: outcome.status === "ok" ? 1 : 0,
        failCount: outcome.status === "ok" ? 0 : 1,
        lastStatus: outcome.status,
        lastError: outcome.error || null,
      },
      update: {
        successCount: { increment: outcome.status === "ok" ? 1 : 0 },
        failCount: { increment: outcome.status === "ok" ? 0 : 1 },
        lastStatus: outcome.status,
        lastError: outcome.error || null,
      },
    });
  } catch (err) {
    console.error("[price_scraper] learn() failed:", err);
  }
}

/**
 * Scrape one asset's price and store it in JDDS.
 */
async function scrapeAsset(market: string, symbol: string): Promise<ScrapeOutcome> {
  const result: FetchResult = await fetchQuoteWithFallback(symbol, market);

  const outcome: ScrapeOutcome = {
    symbol,
    market,
    status: result.status,
    source: result.source,
    price: result.quote?.price,
    error: result.error,
  };

  if (result.status === "ok" && result.quote) {
    try {
      const asset = await prisma.asset.findUnique({
        where: { marketId_symbol: { marketId: market, symbol } },
      });
      if (asset) {
        await prisma.price.upsert({
          where: { assetId: asset.id },
          update: {
            price: result.quote.price,
            changePct: result.quote.changePct,
            marketCap: result.quote.marketCap ?? undefined,
            volume: result.quote.volume ?? undefined,
            source: "scraper",
          },
          create: {
            assetId: asset.id,
            price: result.quote.price,
            changePct: result.quote.changePct,
            marketCap: result.quote.marketCap,
            volume: result.quote.volume,
            source: "scraper",
          },
        });
      }
    } catch (err) {
      outcome.status = "network_error";
      outcome.error = "Failed to store price in JDDS";
      console.error(`[price_scraper] store error for ${symbol}:`, err);
    }
  }

  await learn(outcome);
  return outcome;
}

export interface ScrapeOptions {
  /** Only scrape these symbols (page-scoped / manual per-row refreshes). */
  symbols?: string[];
  /** Cap how many assets to scrape (defaults to page size). */
  limit?: number;
}

/**
 * Refresh live prices for a market's assets.
 *
 * TradingView-covered markets: a single whole-market scan syncs the full
 * universe + prices in one call (fast, scalable — no per-symbol loop, no 60s
 * bridge timeout on big universes like CN/DE/CA).
 *
 * Non-TradingView markets (e.g. US): batched yfinance bridge calls, falling
 * back to per-symbol scraping only for symbols the bridge could not resolve.
 * limit=0 refreshes every active asset. Large universes are chunked (200/round)
 * so one full pass never blocks for minutes.
 */
export async function refreshMarketBatch(market: string, limit: number): Promise<{ total: number; ok: number; failed: number }> {
  // TradingView path — the scalable whole-market sync. Honor `limit` so
  // shallow passes (boot warm-up) don't write the entire universe at once.
  if (isTradingViewMarket(market)) {
    const result = await syncMarketUniverse(market, limit);
    return { total: result.scanned, ok: result.ok, failed: result.failed };
  }

  const assets = await prisma.asset.findMany({
    where: { marketId: market, isActive: true },
    select: { id: true, symbol: true },
    take: limit > 0 ? limit : undefined,
  });
  if (assets.length === 0) return { total: 0, ok: 0, failed: 0 };

  let ok = 0;
  let failed = 0;

  // Batched bridge calls (chunked for big universes). Successful quotes are
  // grouped into chunked transactions — SQLite statements block the event
  // loop, so N individual awaits become N/CHUNK transactions. Only symbols
  // the bridge missed pay the sequential adaptive-chain fallback.
  const CHUNK = 200;
  for (let i = 0; i < assets.length; i += CHUNK) {
    const chunk = assets.slice(i, i + CHUNK);
    const results = await fetchYahooBatchQuote(
      chunk.map((a) => a.symbol),
      market
    );

    const hits: Array<{ assetId: string; price: number; changePct: number; volume?: number; source: string }> = [];
    const misses: Array<{ asset: { id: string; symbol: string }; result: (typeof results)[number] }> = [];
    for (let j = 0; j < results.length; j++) {
      const result = results[j];
      const asset = chunk[j];
      if (!asset) continue;
      if (result.status === "ok" && result.quote) {
        hits.push({
          assetId: asset.id,
          price: result.quote.price,
          changePct: result.quote.changePct,
          volume: result.quote.volume ?? undefined,
          source: "yfinance",
        });
      } else {
        misses.push({ asset, result });
      }
    }

    if (hits.length > 0) {
      const ops = hits.map((h) =>
        prisma.price.upsert({
          where: { assetId: h.assetId },
          update: {
            price: h.price,
            changePct: h.changePct,
            volume: h.volume ?? undefined,
            source: h.source,
          },
          create: {
            assetId: h.assetId,
            price: h.price,
            changePct: h.changePct,
            volume: h.volume ?? undefined,
            source: h.source,
          },
        })
      );
      for (let k = 0; k < ops.length; k += WRITE_CHUNK) {
        await prisma.$transaction(ops.slice(k, k + WRITE_CHUNK));
        await yieldToEventLoop();
      }
      ok += hits.length;
    }

    // Bridge miss (e.g. delisted / Yahoo data gap) — try the adaptive chain once.
    for (const miss of misses) {
      const fallback: FetchResult = await fetchQuoteWithFallback(miss.asset.symbol, market);
      if (fallback.status === "ok" && fallback.quote) {
        await prisma.price.upsert({
          where: { assetId: miss.asset.id },
          update: {
            price: fallback.quote.price,
            changePct: fallback.quote.changePct,
            volume: fallback.quote.volume ?? undefined,
            source: fallback.source,
          },
          create: {
            assetId: miss.asset.id,
            price: fallback.quote.price,
            changePct: fallback.quote.changePct,
            volume: fallback.quote.volume ?? undefined,
            source: fallback.source,
          },
        });
        ok++;
      } else {
        failed++;
      }
    }
  }
  return { total: assets.length, ok, failed };
}

/**
 * Run a scrape cycle for the selected markets.
 * - Without options: refreshes the first `limit` assets of each market.
 * - With symbols: refreshes exactly those symbols (in the given markets).
 * Returns a summary of outcomes.
 */
export async function runPriceScraper(
  markets: string[] = ["US", "CRYPTO"],
  options: ScrapeOptions = {}
): Promise<{ total: number; ok: number; failed: number; outcomes: ScrapeOutcome[] }> {
  await seedUniverse(markets);

  const where =
    options.symbols && options.symbols.length > 0
      ? { marketId: { in: markets }, symbol: { in: options.symbols }, isActive: true }
      : { market: { id: { in: markets }, enabled: true }, isActive: true };

  const assets = await prisma.asset.findMany({ where });

  // If no explicit symbol list, honor the limit (scrape as many as displayed per page).
  const targets = options.symbols?.length ? assets : assets.slice(0, options.limit ?? assets.length);

  const outcomes: ScrapeOutcome[] = [];
  let ok = 0;
  let failed = 0;

  // Small random delay between requests to look human + avoid rate limits.
  for (const asset of targets) {
    const outcome = await scrapeAsset(asset.marketId, asset.symbol);
    outcomes.push(outcome);
    if (outcome.status === "ok") ok++;
    else failed++;
    await new Promise((r) => setTimeout(r, 400 + Math.random() * 600));
  }

  return { total: targets.length, ok, failed, outcomes };
}
