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
      return NextResponse.json({ error: "Symbol not found in backtesting database universe." }, { status: 404 });
    }

    const start = startDate ? new Date(startDate) : new Date(Date.now() - 365 * 24 * 60 * 60 * 1000);
    const end = endDate ? new Date(endDate) : new Date();

    const candlesCount = await prisma.historicalCandle.count({
      where: {
        symbolId: symObj.id,
        timeframe: timeframe || "1d",
        timestamp: { gte: start, lte: end }
      }
    });

    if (candlesCount < 1) {
      return NextResponse.json({
        success: false,
        error: "No historical candle data ready. Please download the historical candles first."
      }, { status: 400 });
    }

    return NextResponse.json({
      success: true,
      message: "Data validated successfully. Backtesting engine is starting...",
      candlesCount
    });

  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || "Failed to initiate backtest run." },
      { status: 500 }
    );
  }
}
