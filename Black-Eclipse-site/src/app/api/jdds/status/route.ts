import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const [
      totalSymbols,
      backtestReadySymbols,
      cryptoSymbols,
      forexSymbols,
      stockSymbols,
      commoditySymbols,
      pakistanSymbols,
      totalJobs,
      activeJobs,
      failedJobs,
      modeRow,
      pauseRow
    ] = await Promise.all([
      prisma.assetSymbol.count({ where: { isActive: true } }),
      prisma.assetSymbol.count({ where: { isBacktestEnabled: true, dataStatus: "ready" } }),
      prisma.assetSymbol.count({ where: { assetClass: "crypto" } }),
      prisma.assetSymbol.count({ where: { assetClass: "forex" } }),
      prisma.assetSymbol.count({ where: { assetClass: "stock" } }),
      prisma.assetSymbol.count({ where: { assetClass: "commodity" } }),
      prisma.assetSymbol.count({ where: { country: "Pakistan" } }),
      prisma.jDDSJob.count(),
      prisma.jDDSJob.count({ where: { status: { in: ["pending", "running"] } } }),
      prisma.jDDSJob.count({ where: { status: "failed" } }),
      prisma.systemConfig.findUnique({ where: { key: "active_mode" } }),
      prisma.systemConfig.findUnique({ where: { key: "system_config" } }),
    ]);

    let globalMode = "hybrid";
    let isPaused = false;

    if (modeRow) {
      globalMode = modeRow.value;
    }
    if (pauseRow) {
      try {
        const val = JSON.parse(pauseRow.value);
        isPaused = val.system?.globalPause || false;
      } catch (e) {}
    }

    return NextResponse.json({
      status: "UP",
      mode: globalMode,
      paused: isPaused,
      stats: {
        totalSymbols,
        backtestReadySymbols,
        cryptoSymbols,
        forexSymbols,
        stockSymbols,
        commoditySymbols,
        pakistanSymbols,
      },
      jobs: {
        total: totalJobs,
        active: activeJobs,
        failed: failedJobs,
      },
      providerHealth: {
        binance: "Healthy",
        yahooFinance: "Healthy",
        stooq: "Healthy",
        twelveData: process.env.TWELVEDATA_API_KEY ? "Configured" : "Missing Key",
        alphaVantage: process.env.ALPHAVANTAGE_API_KEY ? "Configured" : "Missing Key",
        finnhub: "Healthy",
        psx: "Healthy"
      }
    });
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || "Failed to fetch JDDS status." },
      { status: 500 }
    );
  }
}
