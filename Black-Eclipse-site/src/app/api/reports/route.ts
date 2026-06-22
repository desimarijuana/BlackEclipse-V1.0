import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { auth } from "@/lib/auth";
import { headers } from "next/headers";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const session = await auth.api.getSession({
      headers: await headers(),
    });

    if (!session || !session.user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const userId = session.user.id;

    // Fetch user reports
    let reports = await prisma.report.findMany({
      where: { userId },
      orderBy: { createdAt: "desc" },
    });

    // Seed dummy reports if empty
    if (reports.length === 0) {
      await prisma.report.createMany({
        data: [
          {
            userId,
            title: "BTC Momentum Breakout Strategy Report",
            asset: "BTC",
            marketType: "COMMODITIES", // Fallback enum match
            status: "COMPLETED",
            summary: "BTC Momentum strategy executed on 1-hour intervals. Generates strong Alpha during high volatility regimes, with a Profit Factor of 2.82 and Win Rate of 72.4%. Sharpe ratio is 1.84.",
            content: JSON.stringify({
              winRate: "72.4%",
              profitFactor: "2.82",
              totalTrades: 42,
              maxDrawdown: "6.4%",
              expectancy: "$120.50",
              sharpe: "1.84",
              sortino: "2.12"
            })
          },
          {
            userId,
            title: "ETH Mean Reversion Strategy Report",
            asset: "ETH",
            marketType: "COMMODITIES",
            status: "COMPLETED",
            summary: "ETH RSI oversold / Bollinger bounce strategy evaluated on 15m candle intervals. Offers high stability in consolidation ranges, with a Win Rate of 64.8% and Profit Factor of 3.12.",
            content: JSON.stringify({
              winRate: "64.8%",
              profitFactor: "3.12",
              totalTrades: 78,
              maxDrawdown: "4.8%",
              expectancy: "$45.20",
              sharpe: "1.65",
              sortino: "1.95"
            })
          },
          {
            userId,
            title: "SPY Trend Following Strategy Report",
            asset: "SPY",
            marketType: "STOCKS",
            status: "COMPLETED",
            summary: "SPY SMA crossover strategy evaluated on 1-day intervals. Captures major macro moves, showing a Win Rate of 58.1% and total net profit of +24.8%. Max drawdown is low at 3.2%.",
            content: JSON.stringify({
              winRate: "58.1%",
              profitFactor: "2.74",
              totalTrades: 19,
              maxDrawdown: "3.2%",
              expectancy: "$328.00",
              sharpe: "2.05",
              sortino: "2.40"
            })
          }
        ]
      });

      reports = await prisma.report.findMany({
        where: { userId },
        orderBy: { createdAt: "desc" },
      });
    }

    return NextResponse.json({ success: true, reports });
  } catch (error: any) {
    console.error("[GET /api/reports] Error:", error);
    return NextResponse.json({ error: error.message || "Failed to load reports" }, { status: 500 });
  }
}
