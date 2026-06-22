import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { symbol, timeframe, startDate, endDate } = body;

    if (!symbol) {
      return NextResponse.json({ error: "Missing symbol parameter." }, { status: 400 });
    }

    const cleanSymbol = symbol.toUpperCase().trim();
    const symObj = await prisma.assetSymbol.findFirst({
      where: { symbol: cleanSymbol }
    });

    if (!symObj) {
      return NextResponse.json({
        available: false,
        status: "needs_download",
        message: `Symbol ${cleanSymbol} not found in universe. Will queue for download.`
      });
    }

    const start = startDate ? new Date(startDate) : new Date(Date.now() - 365 * 24 * 60 * 60 * 1000);
    const end = endDate ? new Date(endDate) : new Date();

    const candlesCount = await prisma.historicalCandle.count({
      where: {
        symbolId: symObj.id,
        timeframe: timeframe || "1d",
        timestamp: {
          gte: start,
          lte: end
        }
      }
    });

    const isAvailable = candlesCount >= 10; // at least 10 candles
    
    let message = "Click Download Data to continue.";
    if (isAvailable) {
      message = `Historical data available (${candlesCount} candles cached from ${start.toISOString().split("T")[0]} to ${end.toISOString().split("T")[0]}).`;
    } else if (symObj.dataStatus === "downloading") {
      message = "Data download in progress. Please wait...";
    } else if (timeframe === "5m" && !["crypto", "forex"].includes(symObj.assetClass)) {
      message = "5m data not available for this symbol type. Daily candles available.";
    }

    return NextResponse.json({
      symbolId: symObj.id,
      available: isAvailable,
      candlesCount,
      status: symObj.dataStatus,
      message,
      lastSyncedAt: symObj.lastSyncedAt
    });

  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || "Failed to request data availability." },
      { status: 500 }
    );
  }
}
