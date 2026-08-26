import { NextResponse } from "next/server";
import { prisma, yieldToEventLoop } from "@/lib/db";
import { fetchYahooBatchQuote } from "@/lib/scraper/fetchers/yfinance";
import { isTradingViewMarket } from "@/lib/scraper/fetchers/tradingview";
import { syncMarketUniverse } from "@/lib/scraper/universe-sync";
import { guardExpensiveMutation } from "@/lib/api-guard";
import { toMarketId } from "@/lib/markets";

export const dynamic = "force-dynamic";

// The yfinance bridge batches all symbols over ONE shared Python session
// (fast_info, chart endpoint only) — no per-symbol HTTP round-trips, no
// Yahoo 404/429 bursts on full-page refreshes.

// Guards against concurrent refreshes for the same market.
const refreshInFlight = new Set<string>();

// Persist a batch of quote results into JDDS. Shared by the yfinance paths.
// Writes are grouped into small chunked transactions with event-loop yields
// between them — SQLite statements block the loop, so this keeps live
// requests responsive during bulk refreshes.
const WRITE_CHUNK = 250;

async function persistQuotes(
  assets: Array<{ id: string; symbol: string }>,
  results: Awaited<ReturnType<typeof fetchYahooBatchQuote>>
) {
  const ops: ReturnType<typeof prisma.price.upsert>[] = [];

  for (let j = 0; j < results.length; j++) {
    const result = results[j];
    if (!result || result.status !== "ok" || !result.quote) continue;
    const asset = assets[j];
    if (!asset) continue;

    // Only persist columns that exist on the Price model. (Day high/low,
    // open, previous close, 52w range are NOT stored in JDDS. The v7
    // fundamentals endpoint is 401-blocked by Yahoo, so we rely on the
    // price + volume the chart endpoint already returns and leave the
    // fundamental fields untouched.)
    const data = {
      price: result.quote.price,
      changePct: result.quote.changePct,
      volume: result.quote.volume ?? undefined,
      source: "yfinance",
    };

    ops.push(
      prisma.price.upsert({
        where: { assetId: asset.id },
        update: data,
        create: { assetId: asset.id, ...data },
      })
    );
  }

  for (let i = 0; i < ops.length; i += WRITE_CHUNK) {
    await prisma.$transaction(ops.slice(i, i + WRITE_CHUNK));
    await yieldToEventLoop();
  }
  return { ok: ops.length, failed: results.length - ops.length };
}

// POST /api/refresh — fetch live prices for a market's assets and write them
// into JDDS. Body: { market: "US" | "PK" | "CRYPTO" | ..., symbols?: string[] }
// When `symbols` is provided ONLY those symbols are refreshed (the visible
// screener page) — this keeps country switches fast; the background
// schedulers cover the rest of each universe.
export async function POST(request: Request) {
  const blocked = guardExpensiveMutation(request, "refresh", { limit: 30, windowMs: 60_000 });
  if (blocked) {
    return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  }
  try {
    const body = await request.json().catch(() => ({}));
    const market = toMarketId((body.market || "US").toUpperCase());
    const symbols: string[] = Array.isArray(body.symbols)
      ? body.symbols.filter((s: unknown) => typeof s === "string" && s.trim()).map((s: string) => s.trim().toUpperCase())
      : [];

    if (refreshInFlight.has(market)) {
      return NextResponse.json({ success: true, total: 0, ok: 0, failed: 0, skipped: true });
    }
    refreshInFlight.add(market);

    try {
      // TradingView-covered markets: a whole-market scan syncs the full
      // universe + prices. That scan is expensive (large markets can take
      // minutes), so when the caller passes explicit symbols we first try the
      // fast scoped yfinance bridge and only fall back to the full scan when
      // Yahoo yields nothing (e.g. PSX, which Yahoo no longer carries).
      if (isTradingViewMarket(market)) {
        if (symbols.length > 0) {
          const assets = await prisma.asset.findMany({
            where: { marketId: market, isActive: true, symbol: { in: symbols } },
            select: { id: true, symbol: true },
          });
          if (assets.length > 0) {
            const results = await fetchYahooBatchQuote(assets.map((a) => a.symbol), market);
            const { ok, failed } = await persistQuotes(assets, results);
            if (ok > 0) {
              return NextResponse.json({ success: true, total: assets.length, ok, failed, source: "yfinance" });
            }
          }
        }
        const sync = await syncMarketUniverse(market);
        return NextResponse.json({
          success: true,
          total: sync.scanned,
          ok: sync.ok,
          failed: sync.failed,
          source: "tradingview",
        });
      }

      // Pull the market's active assets. When no explicit symbols are given,
      // refresh the ENTIRE universe (no cap).
      const assets = await prisma.asset.findMany({
        where: {
          marketId: market,
          isActive: true,
          ...(symbols.length > 0 ? { symbol: { in: symbols } } : {}),
        },
        select: { id: true, symbol: true },
      });

      // Batched bridge calls (chunked for big universes) — the bridge keeps one
      // shared session and a small thread pool per call, then we persist each hit.
      let ok = 0;
      let failed = 0;
      const CHUNK = 200;
      for (let i = 0; i < assets.length; i += CHUNK) {
        const chunk = assets.slice(i, i + CHUNK);
        const chunkResults = await fetchYahooBatchQuote(
          chunk.map((a) => a.symbol),
          market
        );
        const res = await persistQuotes(chunk, chunkResults);
        ok += res.ok;
        failed += res.failed;
      }

      return NextResponse.json({ success: true, total: assets.length, ok, failed });
    } finally {
      refreshInFlight.delete(market);
    }
  } catch (err) {
    console.error("[api/refresh] Error:", err);
    return NextResponse.json({ error: "Failed to refresh prices" }, { status: 500 });
  }
}
