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

import { prisma, yieldToEventLoop } from "@/lib/db";
import { getCachedMarketScan, isTradingViewMarket } from "./fetchers/tradingview";
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

// Security type / assetClass applied to every TradingView scan row (the
// scanner query already filters to `type === "stock"`).
const TYPE_HINTS = { securityType: "Stock", assetClass: "Equity" } as const;

// Rows per transaction. SQLite writes are synchronous and block the event
// loop per statement — chunks stay small and yield between transactions so
// HTTP requests are never starved for long.
const WRITE_CHUNK = 250;

/**
 * Sync one market's universe + prices from a TradingView scan.
 * `limit` caps how many scanned rows are actually upserted (0 = all) so
 * boot warm-ups can't hammer SQLite with 5k+ writes while pages load.
 * Returns summary. No-op (empty result) for non-TradingView markets.
 */
export async function syncMarketUniverse(market: string, limit = 0): Promise<SyncResult> {
  if (!isTradingViewMarket(market)) {
    return { market, scanned: 0, created: 0, updated: 0, deactivated: 0, ok: 0, failed: 0 };
  }

  let rows: ScanRow[];
  try {
    // Reuses a recent scan when one is already cached (e.g. populated by a
    // per-symbol fallback moments ago) instead of re-fetching the market.
    rows = await getCachedMarketScan(market);
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

  // Cap the write volume when requested (boot warm-up): sync the top rows by
  // market cap so the most visible instruments get fresh prices first.
  const effectiveRows = limit > 0 ? rows.slice(0, limit) : rows;
  result.scanned = rows.length;

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
    scannedIds.add(row.symbol);
    misses.set(row.symbol, 0);
  }

  // ── Phase A: batch-upsert assets ─────────────────────────────────────
  // Atomic upserts on the (marketId, symbol) unique constraint — safe under
  // concurrent syncs (boot warm-up + on-demand refresh can run in parallel),
  // which a create-if-absent path is NOT (two creates race → P2002).
  // Chunked transactions: SQLite writes are synchronous and block the event
  // loop per statement, so N individual awaits become rows/WRITE_CHUNK
  // transactions.
  const assetUpsert = (row: ScanRow) =>
    prisma.asset.upsert({
      where: { marketId_symbol: { marketId: market, symbol: row.symbol } },
      update: {
        name: row.name,
        sector: row.sector ?? undefined,
        industry: row.industry ?? undefined,
        securityType: TYPE_HINTS.securityType,
        assetClass: TYPE_HINTS.assetClass,
        country: market, // stamp so per-row currency detection works everywhere
        isActive: true,
      },
      create: {
        symbol: row.symbol,
        name: row.name,
        marketId: market,
        sector: row.sector ?? null,
        industry: row.industry ?? null,
        securityType: TYPE_HINTS.securityType,
        assetClass: TYPE_HINTS.assetClass,
        country: market,
        isActive: true,
      },
    });

  try {
    for (let i = 0; i < effectiveRows.length; i += WRITE_CHUNK) {
      const chunk = effectiveRows.slice(i, i + WRITE_CHUNK);
      await prisma.$transaction(chunk.map(assetUpsert));
      // Hand the event loop back to pending HTTP requests between chunks.
      // A short sleep (not just setImmediate) lets queued responses actually
      // drain — thousands of back-to-back transactions otherwise pin the
      // loop and freeze every API route for minutes.
      await yieldToEventLoop();
      await new Promise((r) => setTimeout(r, 25));
    }
  } catch (err) {
    console.error(`[universe-sync] asset upsert failed for ${market}:`, err);
    result.failed += effectiveRows.length;
    return result;
  }

  for (const row of effectiveRows) {
    if (existingBySymbol.has(row.symbol)) result.updated++;
    else result.created++;
  }

  // ── Phase B: resolve asset ids once ───────────────────────────────────
  const allAssets = await prisma.asset.findMany({
    where: { marketId: market },
    select: { id: true, symbol: true },
  });
  const idBySymbol = new Map(allAssets.map((a) => [a.symbol, a.id]));

  // ── Phase C: batch-upsert prices ──────────────────────────────────────
  const priceUpsert = (row: ScanRow) => {
    const assetId = idBySymbol.get(row.symbol)!;
    return prisma.price.upsert({
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
  };

  const pricedRows = effectiveRows.filter((row) => idBySymbol.has(row.symbol));
  result.failed += effectiveRows.length - pricedRows.length;
  try {
    for (let i = 0; i < pricedRows.length; i += WRITE_CHUNK) {
      const chunk = pricedRows.slice(i, i + WRITE_CHUNK);
      await prisma.$transaction(chunk.map(priceUpsert));
      await yieldToEventLoop();
      await new Promise((r) => setTimeout(r, 25));
    }
  } catch (err) {
    console.error(`[universe-sync] price upsert failed for ${market}:`, err);
    result.failed += pricedRows.length - result.ok;
    return result;
  }
  result.ok = pricedRows.length;

  // Deactivate symbols absent from the scan (delisted) after threshold misses.
  const delistedIds: string[] = [];
  for (const asset of existing) {
    if (scannedIds.has(asset.symbol)) continue;
    const prior = missesBefore[asset.symbol] ?? 0;
    const now = prior + 1;
    misses.set(asset.symbol, now);
    if (asset.isActive && now >= DELIST_THRESHOLD) {
      delistedIds.push(asset.id);
    }
  }
  if (delistedIds.length > 0) {
    await prisma.asset.updateMany({
      where: { id: { in: delistedIds } },
      data: { isActive: false },
    });
    result.deactivated = delistedIds.length;
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
