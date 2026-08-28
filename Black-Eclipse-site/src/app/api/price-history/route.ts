import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { MARKET_CURRENCY } from "@/lib/market-currency";
import { yahooSymbol } from "@/lib/scraper/fetchers/yfinance";

export const dynamic = "force-dynamic";

// GET /api/price-history?symbol=OGDC&market=PK
//
// Returns a live 1-month daily closing series for the stock detail sparkline.
// Resolution order:
//   1. yfinance bridge (live, one Python call for one symbol — ~5s)
//   2. persisted Price row snapshot (single point; series = [prevClose, price])
// Response: { symbol, currency, points: number[], source: "yfinance" | "snapshot" }
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const symbol = (searchParams.get("symbol") || "").trim().toUpperCase();
  const market = (searchParams.get("market") || "US").trim().toUpperCase();

  if (!symbol) {
    return NextResponse.json({ points: [], source: "none" });
  }

  try {
    const { fetchYahooBatchRaw } = await import("@/lib/scraper/fetchers/yfinance");
    const ticker = yahooSymbol(symbol, market);
    // 1mo of daily closes → the growth sparkline series.
    const raw = await fetchYahooBatchRaw([symbol], market, "1d", "1mo");
    const history = raw.history?.[ticker];
    if (Array.isArray(history) && history.length >= 2) {
      const points = history.map((h: { close: number }) => Number(h.close)).filter((n: number) => Number.isFinite(n) && n > 0);
      if (points.length >= 2) {
        return NextResponse.json({
          symbol,
          currency: MARKET_CURRENCY[market] || "$",
          points,
          source: "yfinance",
        });
      }
    }
    // Bridge returned no history — fall through to the DB snapshot.
  } catch {
    // Bridge unavailable (no Python / offline) — fall through.
  }

  try {
    const asset = await prisma.asset.findFirst({
      where: { symbol, marketId: market, isActive: true },
      select: { price: { select: { price: true, previousClose: true } } },
    });
    if (asset?.price && asset.price.price > 0) {
      const points = [asset.price.previousClose ?? asset.price.price * 0.99, asset.price.price];
      return NextResponse.json({
        symbol,
        currency: MARKET_CURRENCY[market] || "$",
        points,
        source: "snapshot",
      });
    }
  } catch { /* ignore */ }

  return NextResponse.json({ symbol, points: [], source: "none" });
}