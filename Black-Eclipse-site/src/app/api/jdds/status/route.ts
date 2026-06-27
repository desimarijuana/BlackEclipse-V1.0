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

    // Calculate symbol health metrics dynamically
    const allActiveSymbols = await prisma.assetSymbol.findMany({
      where: { isActive: true }
    });

    let fullyLoaded = 0;
    let missing = 0;
    let partial = 0;
    let broken = 0;
    let downloading = 0;

    for (const sym of allActiveSymbols) {
      if (sym.dataStatus === "downloading") {
        downloading++;
      } else if (sym.dataStatus === "failed") {
        broken++;
      } else if (sym.dataStatus === "needs_download") {
        missing++;
      } else {
        const count = await prisma.historicalCandle.count({
          where: { symbolId: sym.id }
        });
        if (count >= 100) {
          fullyLoaded++;
        } else if (count > 0) {
          partial++;
        } else {
          missing++;
        }
      }
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
        health: {
          fullyLoaded,
          missing,
          partial,
          broken,
          downloading
        }
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
