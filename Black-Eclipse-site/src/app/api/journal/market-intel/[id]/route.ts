import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { getOrCreateProfile, saveMarketContext, updateTradeMfeMae } from "@/lib/journal/data";
import { computeMfeMae } from "@/lib/journal/analytics/mfe-mae";
import { computeMarketContext } from "@/lib/journal/analytics/market-context";
import type { PricePoint } from "@/lib/journal/analytics/mfe-mae";

export const dynamic = "force-dynamic";

// GET /api/journal/market-intel/[id]
// Fetches the price series for a trade's symbol, computes MFE/MAE + market
// context, persists them, and returns everything for the trade replay chart.
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const profileId = await getOrCreateProfile();
    const trade = await prisma.trade.findFirst({
      where: { id, profileId },
      include: { marketContext: true },
    });
    if (!trade) {
      return NextResponse.json({ error: "Trade not found" }, { status: 404 });
    }

    // Fetch the price series (daily, 3 months) for the symbol.
    const yahooTicker = yahooTickerFor(trade.symbol);
    const market = inferMarket(yahooTicker);
    const histRes = await fetch(
      `${process.env.NEXT_PUBLIC_BASE_URL || "http://localhost:3000"}/api/price-history?symbol=${encodeURIComponent(yahooTicker)}&market=${market}&range=3mo`,
      { cache: "no-store" },
    );
    const hist = await histRes.json().catch(() => ({}));
    const series: PricePoint[] = Array.isArray(hist.series) ? hist.series : [];

    // Compute MFE/MAE.
    const mfeMae = computeMfeMae(
      series,
      trade.entry,
      trade.stopLoss,
      trade.direction as "LONG" | "SHORT",
      trade.entryTime.toISOString(),
      trade.exitTime.toISOString(),
    );
    if (mfeMae.mfe != null || mfeMae.mae != null) {
      await updateTradeMfeMae(profileId, trade.id, mfeMae.mfe, mfeMae.mae);
    }

    // Compute market context.
    const ctx = computeMarketContext(series, trade.entry, trade.entryTime.toISOString());
    const savedCtx = await saveMarketContext(profileId, trade.id, {
      trend: ctx.trend,
      vwap: ctx.vwap,
      ema50AboveEma200: ctx.ema50AboveEma200,
      adx: ctx.adx,
      atr: ctx.atr,
      regime: ctx.regime,
      volatility: ctx.volatility,
      session: ctx.session,
    });

    return NextResponse.json({
      trade: {
        id: trade.id,
        symbol: trade.symbol,
        direction: trade.direction,
        entry: trade.entry,
        exit: trade.exit,
        stopLoss: trade.stopLoss,
        takeProfit: trade.takeProfit,
        entryTime: trade.entryTime,
        exitTime: trade.exitTime,
        rMultiple: trade.rMultiple,
        mfe: mfeMae.mfe,
        mae: mfeMae.mae,
      },
      series,
      marketContext: savedCtx ?? trade.marketContext,
      source: hist.source ?? "none",
    });
  } catch (err) {
    console.error("[api/journal/market-intel] GET error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to load market intel" },
      { status: 500 },
    );
  }
}

/** Infer a market id from a symbol (crypto vs US). */
function inferMarket(symbol: string): string {
  const s = symbol.toUpperCase();
  if (s.endsWith("USD") || s.endsWith("USDT") || s.includes("-")) return "CRYPTO";
  return "US";
}

/** Map common journal symbols to their Yahoo chart tickers. */
function yahooTickerFor(symbol: string): string {
  const s = symbol.toUpperCase();
  const map: Record<string, string> = {
    XAUUSD: "GC=F",
    XAGUSD: "SI=F",
    NQ: "NQ=F",
    ES: "ES=F",
    YM: "YM=F",
    CL: "CL=F",
    WTI: "CL=F",
    BRENT: "BZ=F",
    BTCUSD: "BTC-USD",
    ETHUSD: "ETH-USD",
    EURUSD: "EURUSD=X",
    GBPUSD: "GBPUSD=X",
    USDJPY: "JPY=X",
    AUDUSD: "AUDUSD=X",
    USDCAD: "CAD=X",
    USDCHF: "CHF=X",
    NZDUSD: "NZDUSD=X",
  };
  return map[s] ?? s;
}
