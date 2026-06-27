import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

const HOT_SYMBOLS = new Set([
  "BTC", "ETH", "SOL", "XRP", "BNB", "ADA", "DOT", "DOGE",
  "GC=F", "EURUSD=X", "AAPL", "MSFT", "TSLA", "NVDA", "AMZN"
]);

interface CacheEntry {
  response: any;
  expiresAt: number;
}

const memoryCache = new Map<string, CacheEntry>();
const CACHE_TTL = 30 * 1000; // 30 seconds cache for hot symbols

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const rawSymbol = searchParams.get("symbol") || "";
    const timeframe = searchParams.get("timeframe") || "1d";
    const startParam = searchParams.get("start");
    const endParam = searchParams.get("end");

    if (!rawSymbol) {
      return NextResponse.json({ error: "Missing symbol parameter." }, { status: 400 });
    }

    let symbol = rawSymbol.toUpperCase().trim();

    // Check cache first for hot symbols
    const cacheKey = `${symbol}_${timeframe}_${startParam || ""}_${endParam || ""}`;
    if (HOT_SYMBOLS.has(symbol)) {
      const cached = memoryCache.get(cacheKey);
      if (cached && cached.expiresAt > Date.now()) {
        return NextResponse.json(cached.response);
      }
    }

    const cryptoList = ["BTC", "ETH", "SOL", "XRP", "BNB", "ADA", "DOT", "DOGE"];

    // Self-heal any misclassified crypto assets in the database
    if (cryptoList.includes(symbol)) {
      const misclassified = await prisma.assetSymbol.findFirst({
        where: { symbol, assetClass: "stock" }
      });
      if (misclassified) {
        await prisma.assetSymbol.update({
          where: { id: misclassified.id },
          data: {
            assetClass: "crypto",
            market: "Crypto",
            exchange: "Binance",
            country: "Global",
            dataStatus: "needs_download"
          }
        });
        // Delete any failed download jobs for this symbol to start clean
        await prisma.jDDSJob.deleteMany({
          where: { symbolId: misclassified.id }
        });
      }
    }

    // Check if the symbol exists in our universe
    let assetSymbol = await prisma.assetSymbol.findFirst({
      where: { symbol }
    });

    // If it doesn't exist, create it as a default Yahoo/Binance symbol
    if (!assetSymbol) {
      const isCrypto = cryptoList.includes(symbol) || symbol.endsWith("USDT") || symbol.endsWith("BTC");
      const assetClass = isCrypto ? "crypto" : "stock";
      const market = isCrypto ? "Crypto" : "US Stocks";
      const exchange = isCrypto ? "Binance" : "NASDAQ";
      const country = isCrypto ? "Global" : "US";
      
      assetSymbol = await prisma.assetSymbol.create({
        data: {
          symbol,
          displayName: symbol,
          assetClass,
          market,
          exchange,
          country,
          availableTimeframes: ["1m", "5m", "15m", "1h", "1d", "1w", "1M"],
          isBacktestEnabled: true,
          dataStatus: "needs_download"
        }
      });
    }

    const now = new Date();
    const startDate = startParam ? new Date(startParam) : new Date(now.getFullYear() - 1, now.getMonth(), now.getDate());
    const endDate = endParam ? new Date(endParam) : now;

    // Fetch candles from database
    const candles = await prisma.historicalCandle.findMany({
      where: {
        symbolId: assetSymbol.id,
        timeframe,
        timestamp: {
          gte: startDate,
          lte: endDate,
        },
      },
      orderBy: { timestamp: "asc" },
    });

    // Check if we need to request/trigger a download job
    const hasCachedData = candles.length > 0;
    
    // We decide to download if database is empty or if last synced was long ago
    const shouldDownload = !hasCachedData || 
                           assetSymbol.dataStatus === "needs_download" ||
                           (assetSymbol.lastSyncedAt && (now.getTime() - assetSymbol.lastSyncedAt.getTime() > 24 * 60 * 60 * 1000));

    if (shouldDownload && assetSymbol.dataStatus !== "downloading") {
      console.log(`[Candle API] Queueing download job for ${symbol} (${timeframe}) from ${startDate.toISOString()} to ${endDate.toISOString()}`);
      
      // Check if job already exists to avoid duplicate running tasks
      const existingJob = await prisma.jDDSJob.findFirst({
        where: {
          symbolId: assetSymbol.id,
          timeframe,
          status: { in: ["pending", "running"] }
        }
      });

      if (!existingJob) {
        // Create new download job
        const job = await prisma.jDDSJob.create({
          data: {
            type: "historical_download",
            status: "pending",
            priority: 3,
            symbolId: assetSymbol.id,
            timeframe,
            startDate,
            endDate,
            progress: 0
          }
        });

        await prisma.assetSymbol.update({
          where: { id: assetSymbol.id },
          data: { dataStatus: "downloading" }
        });

        const resPayload = {
          symbol,
          count: candles.length,
          candles: candles.map(c => ({
            date: c.timestamp.toISOString().split("T")[0] + (["1m", "5m", "15m", "1h"].includes(timeframe) ? ` ${c.timestamp.toTimeString().split(" ")[0].slice(0, 5)}` : ""),
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
            volume: c.volume || 0,
          })),
          dataStatus: "downloading",
          jobId: job.id,
          message: "Data download queued. Retrying background download."
        };

        return NextResponse.json(resPayload);
      } else {
        const resPayload = {
          symbol,
          count: candles.length,
          candles: candles.map(c => ({
            date: c.timestamp.toISOString().split("T")[0] + (["1m", "5m", "15m", "1h"].includes(timeframe) ? ` ${c.timestamp.toTimeString().split(" ")[0].slice(0, 5)}` : ""),
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
            volume: c.volume || 0,
          })),
          dataStatus: "downloading",
          jobId: existingJob.id,
          message: "Data download is already in progress."
        };

        return NextResponse.json(resPayload);
      }
    }

    const finalPayload = {
      symbol,
      count: candles.length,
      candles: candles.map(c => ({
        date: c.timestamp.toISOString().split("T")[0] + (["1m", "5m", "15m", "1h"].includes(timeframe) ? ` ${c.timestamp.toTimeString().split(" ")[0].slice(0, 5)}` : ""),
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
        volume: c.volume || 0,
      })),
      dataStatus: assetSymbol.dataStatus,
      lastSyncedAt: assetSymbol.lastSyncedAt
    };

    // Cache final payload if data is not downloading/missing
    if (HOT_SYMBOLS.has(symbol) && assetSymbol.dataStatus !== "downloading" && candles.length > 0) {
      memoryCache.set(cacheKey, {
        response: finalPayload,
        expiresAt: Date.now() + CACHE_TTL
      });
    }

    return NextResponse.json(finalPayload);

  } catch (error: any) {
    console.error("[Candle API Error]:", error);
    return NextResponse.json(
      { error: error.message || "Failed to fetch historical candle data." },
      { status: 500 }
    );
  }
}
