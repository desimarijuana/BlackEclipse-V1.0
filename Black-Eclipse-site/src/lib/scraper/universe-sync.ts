// Universe sync — keeps a market's JDDS universe + prices current from a
// single TradingView scan.
//
// For each TradingView-covered market, scanMarket() returns the ENTIRE listed
// universe with live prices and fundamentals. syncMarketUniverse() upserts
// every scanned symbol into JDDS (deduped on (marketId, symbol)):
//   - New listings (new IPOs / symbols not yet in JDDS)  → auto-added, priced.
//   - Existing symbols                                   → price + fundamentals refreshed.
//   - Symbols missing from N consecutive scans           → marked isActive=false (delisted).
//
// This replaces the manual scripts/import-*.js CSV importers and the slow
// per-symbol refresh path for whole-market refreshes.

import { prisma } from "@/lib/db";
import { scanMarket, isTradingViewMarket } from "./fetchers/tradingview";
import type { ScanRow } from "./types";

// Deactivate a symbol only after this many consecutive scans it's been absent
// from. Guards against a single glitched scan wrongly delisting valid rows.
export const DELIST_THRESHOLD = 2;

export interface SyncResult {
  market: string;
  scanned: number;
  created: number;
  updated: number;
  deactivated: number;
  ok: number; // prices written
  failed: number;
  totalCount?: number; // market-wide total reported by the scan
}

/** Build the securityType/assetClass hint from a TradingView scan row. */
function typeHints(row: ScanRow): { securityType: string; assetClass: string } {
  return { securityType: "Stock", assetClass: "Equity" };
}

/**
 * Sync one market's universe + prices from a TradingView scan.
 * Returns summary. No-op (empty result) for non-TradingView markets.
 */
export async function syncMarketUniverse(market: string): Promise<SyncResult> {
  if (!isTradingViewMarket(market)) {
    return { market, scanned: 0, created: 0, updated: 0, deactivated: 0, ok: 0, failed: 0 };
  }

  let rows: ScanRow[];
  try {
    rows = await scanMarket(market);
  } catch (err) {
    console.error(`[universe-sync] scan failed for ${market}:`, err);
    return { market, scanned: 0, created: 0, updated: 0, deactivated: 0, ok: 0, failed: 0 };
  }

  const result: SyncResult = {
    market,
    scanned: rows.length,
    created: 0,
    updated: 0,
    deactivated: 0,
    ok: 0,
    failed: 0,
  };

  if (rows.length === 0) return result;

  // Ensure the Market row exists (idempotent).
  await prisma.market.upsert({
    where: { id: market },
    update: { enabled: true },
    create: {
      id: market,
      country: market,
      exchange: market,
      timezone: "UTC",
      openHour: 0,
      closeHour: 0,
      enabled: true,
    },
  });

  // Track which symbols the scan returned so we can deactivate the rest.
  const scannedIds = new Set<string>();
  const misses = new Map<string, number>(); // symbol -> consecutive misses

  const existing = await prisma.asset.findMany({
    where: { marketId: market },
    select: { id: true, symbol: true, isActive: true },
  });
  const existingBySymbol = new Map(existing.map((a) => [a.symbol, a]));

  // Current miss counts for delist detection (persist across runs via
  // SystemConfig key "universe_misses:<market>").
  let missesBefore: Record<string, number> = {};
  try {
    const cfg = await prisma.systemConfig.findUnique({
      where: { key: `universe_misses:${market}` },
    });
    if (cfg?.value) missesBefore = JSON.parse(cfg.value);
  } catch {
    /* ignore — treat as no prior misses */
  }

  for (const row of rows) {
    const symbol = row.symbol;
    scannedIds.add(symbol);
    misses.set(symbol, 0);
    const { securityType, assetClass } = typeHints(row);

    const wasExisting = existingBySymbol.has(symbol);
    try {
      // Atomic upsert on the (marketId, symbol) unique constraint — safe under
      // concurrent syncs (boot warm-up + on-demand refresh can run in parallel),
      // which a create-if-absent path is NOT (two creates race → P2002).
      const asset = await prisma.asset.upsert({
        where: { marketId_symbol: { marketId: market, symbol } },
        update: {
          name: row.name,
          sector: row.sector ?? undefined,
          industry: row.industry ?? undefined,
          securityType,
          assetClass,
          isActive: true,
        },
        create: {
          symbol,
          name: row.name,
          marketId: market,
          sector: row.sector ?? null,
          industry: row.industry ?? null,
          securityType,
          assetClass,
          isActive: true,
        },
      });
      const assetId = asset.id;

      if (!wasExisting) result.created++;
      else result.updated++;

      await prisma.price.upsert({
        where: { assetId },
        update: {
          price: row.price,
          changePct: row.changePct,
          marketCap: row.marketCap ?? undefined,
          volume: row.volume ?? undefined,
          peRatio: row.peRatio ?? undefined,
          eps: row.eps ?? undefined,
          dividendYield: row.dividendYield ?? undefined,
          fiftyTwoWeekHigh: row.fiftyTwoWeekHigh ?? undefined,
          fiftyTwoWeekLow: row.fiftyTwoWeekLow ?? undefined,
          beta: row.beta ?? undefined,
          source: "tradingview",
        },
        create: {
          assetId,
          price: row.price,
          changePct: row.changePct,
          marketCap: row.marketCap,
          volume: row.volume,
          peRatio: row.peRatio,
          eps: row.eps,
          dividendYield: row.dividendYield,
          fiftyTwoWeekHigh: row.fiftyTwoWeekHigh,
          fiftyTwoWeekLow: row.fiftyTwoWeekLow,
          beta: row.beta,
          source: "tradingview",
        },
      });
      result.ok++;
    } catch (err) {
      console.error(`[universe-sync] write failed for ${market}:${symbol}:`, err);
      result.failed++;
    }
  }

  // Deactivate symbols absent from the scan (delisted) after threshold misses.
  for (const asset of existing) {
    if (scannedIds.has(asset.symbol)) continue;
    const prior = missesBefore[asset.symbol] ?? 0;
    const now = prior + 1;
    misses.set(asset.symbol, now);
    if (asset.isActive && now >= DELIST_THRESHOLD) {
      await prisma.asset.update({ where: { id: asset.id }, data: { isActive: false } });
      result.deactivated++;
    }
  }

  // Persist miss counts (only symbols not scanned this round).
  const nextMisses: Record<string, number> = {};
  for (const [sym, count] of misses) {
    if (count > 0) nextMisses[sym] = count;
  }
  await prisma.systemConfig.upsert({
    where: { key: `universe_misses:${market}` },
    update: { value: JSON.stringify(nextMisses) },
    create: { key: `universe_misses:${market}`, value: JSON.stringify(nextMisses) },
  });

  return result;
}
