// price_scraper — the self-healing web scraping agent.
// Loop: SCRAPE → DETECT → DIAGNOSE → RECOVER → LEARN → SERVE.
//
// For each selected market, it scrapes prices for that market's assets,
// stores them in JDDS, and learns source reliability so it self-heals.

import { prisma } from "@/lib/db";
import { MARKET_SEEDS } from "./markets";
import { fetchQuoteWithFallback } from "./fetchers";
import { fetchYahooBatchQuote } from "./fetchers/yfinance";
import { isTradingViewMarket } from "./fetchers/tradingview";
import { syncMarketUniverse } from "./universe-sync";
import type { FetchResult, ScrapeOutcome } from "./types";

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

    for (const s of seed.symbols) {
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
    }
  }
}

/**
 * Record a scrape outcome into SourceHealth (the self-healing memory).
 */
async function learn(outcome: ScrapeOutcome) {
  try {
    const id = `${outcome.source}:${outcome.market}:${outcome.symbol}`;
    const existing = await prisma.sourceHealth.findUnique({ where: { id } });

    if (existing) {
      await prisma.sourceHealth.update({
        where: { id },
        data: {
          successCount: existing.successCount + (outcome.status === "ok" ? 1 : 0),
          failCount: existing.failCount + (outcome.status === "ok" ? 0 : 1),
          lastStatus: outcome.status,
          lastError: outcome.error || null,
        },
      });
    } else {
      await prisma.sourceHealth.create({
        data: {
          id,
          source: outcome.source,
          market: outcome.market,
          symbol: outcome.symbol,
          successCount: outcome.status === "ok" ? 1 : 0,
          failCount: outcome.status === "ok" ? 0 : 1,
          lastStatus: outcome.status,
          lastError: outcome.error || null,
        },
      });
    }
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
  // TradingView path — the scalable whole-market sync.
  if (isTradingViewMarket(market)) {
    const result = await syncMarketUniverse(market);
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

  const CHUNK = 200;
  for (let i = 0; i < assets.length; i += CHUNK) {
    const chunk = assets.slice(i, i + CHUNK);
    const results = await fetchYahooBatchQuote(
      chunk.map((a) => a.symbol),
      market
    );

    for (let j = 0; j < results.length; j++) {
      const result = results[j];
      const asset = chunk[j];
      if (!asset) continue;
      if (result.status === "ok" && result.quote) {
        await prisma.price.upsert({
          where: { assetId: asset.id },
          update: {
            price: result.quote.price,
            changePct: result.quote.changePct,
            volume: result.quote.volume ?? undefined,
            source: "yfinance",
          },
          create: {
            assetId: asset.id,
            price: result.quote.price,
            changePct: result.quote.changePct,
            volume: result.quote.volume ?? undefined,
            source: "yfinance",
          },
        });
        ok++;
        continue;
      }
      // Bridge miss (e.g. delisted / Yahoo data gap) — try the adaptive chain once.
      const fallback: FetchResult = await fetchQuoteWithFallback(asset.symbol, market);
      if (fallback.status === "ok" && fallback.quote) {
        await prisma.price.upsert({
          where: { assetId: asset.id },
          update: {
            price: fallback.quote.price,
            changePct: fallback.quote.changePct,
            volume: fallback.quote.volume ?? undefined,
            source: fallback.source,
          },
          create: {
            assetId: asset.id,
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
