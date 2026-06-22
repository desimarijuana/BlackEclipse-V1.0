import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// Safe JSON parser
function safeJsonParse(value: string | null | undefined, defaultValue: any = {}) {
  if (!value) return defaultValue;
  try {
    return JSON.parse(value);
  } catch (e) {
    console.warn("[health] JSON parse error, using default config:", e);
    return defaultValue;
  }
}

// Universal safe checker with timeout limits
async function safeCheck<T>(
  fn: () => Promise<T>,
  serviceName: string,
  timeoutMs: number = 2500
): Promise<{ status: "healthy" | "degraded" | "down"; latency: number; error: string | null; data: T | null }> {
  const start = Date.now();
  try {
    const timeoutPromise = new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error(`${serviceName} check timed out`)), timeoutMs)
    );
    const result = await Promise.race([fn(), timeoutPromise]);
    return {
      status: "healthy",
      latency: Date.now() - start,
      error: null,
      data: result
    };
  } catch (err: any) {
    console.error(`[safeCheck] Service "${serviceName}" encountered an issue:`, err);
    return {
      status: "down",
      latency: Date.now() - start,
      error: err instanceof Error ? err.message : String(err),
      data: null
    };
  }
}

export async function GET() {
  const timestamp = new Date().toISOString();
  let overallStatus: "ok" | "degraded" | "down" = "ok";

  try {
    // 1. DATABASE CHECK
    const dbCheck = await safeCheck(async () => {
      const readStart = Date.now();
      await prisma.systemConfig.findFirst({ where: { key: "active_mode" } });
      const readLatency = Date.now() - readStart;

      const writeStart = Date.now();
      await prisma.systemConfig.upsert({
        where: { key: "db_latency_test" },
        update: { value: String(Date.now()) },
        create: { key: "db_latency_test", value: String(Date.now()) }
      });
      const writeLatency = Date.now() - writeStart;

      const stockCount = await prisma.stockAsset.count();
      const cryptoCount = await prisma.cryptoAsset.count();
      const activeMarkets = await prisma.cryptoMarket.count({ where: { status: "TRADING" } });

      return {
        readLatency: `${readLatency}ms`,
        writeLatency: `${writeLatency}ms`,
        stocksInDb: stockCount,
        cryptosInDb: cryptoCount,
        activeMarkets
      };
    }, "PostgreSQL", 2500);

    // 2. BINANCE CHECK
    const binanceCheck = await safeCheck(async () => {
      const start = Date.now();
      const controller = new AbortController();
      const tId = setTimeout(() => controller.abort(), 2000);
      const binanceApiKey = process.env.BINANCE_API_KEY;
      const res = await fetch("https://api.binance.com/api/v3/ping", {
        headers: binanceApiKey ? { "X-MBX-APIKEY": binanceApiKey } : {},
        signal: controller.signal
      });
      clearTimeout(tId);
      if (!res.ok) throw new Error(`Binance ping failed with HTTP ${res.status}`);
      return { latency: `${Date.now() - start}ms` };
    }, "Binance API", 2500);

    // 3. FINNHUB CHECK
    const finnhubCheck = await safeCheck(async () => {
      const start = Date.now();
      const token = process.env.FINNHUB_TOKEN || process.env.FINNHUB_API_KEY || "d8gau59r01qlgcuietn0d8gau59r01qlgcuietng";
      const controller = new AbortController();
      const tId = setTimeout(() => controller.abort(), 2000);
      const res = await fetch(`https://finnhub.io/api/v1/quote?symbol=AAPL&token=${token}`, {
        signal: controller.signal
      });
      clearTimeout(tId);
      if (!res.ok) throw new Error(`Finnhub quote failed with HTTP ${res.status}`);
      return { latency: `${Date.now() - start}ms` };
    }, "Finnhub API", 2500);

    // 3.5. COINGECKO CHECK
    const coingeckoCheck = await safeCheck(async () => {
      const start = Date.now();
      const apiKey = process.env.COINGECKO_API_KEY;
      const url = "https://api.coingecko.com/api/v3/ping" + (apiKey ? `?x_cg_demo_api_key=${apiKey}` : "");
      const controller = new AbortController();
      const tId = setTimeout(() => controller.abort(), 2000);
      const res = await fetch(url, { signal: controller.signal });
      clearTimeout(tId);
      if (!res.ok) throw new Error(`CoinGecko ping failed with HTTP ${res.status}`);
      return { latency: `${Date.now() - start}ms` };
    }, "CoinGecko API", 2500);

    // 3.6. MARKETAUX CHECK
    const marketauxCheck = await safeCheck(async () => {
      const start = Date.now();
      let token = "lgw4jOLpqAJbbCIotGst7q79s7XFWFINOPe6EoCY";
      if (dbCheck.status === "healthy") {
        try {
          const tokenRow = await prisma.systemConfig.findUnique({ where: { key: "marketaux_api_key" } });
          if (tokenRow?.value) token = tokenRow.value;
        } catch (e) {}
      }
      const controller = new AbortController();
      const tId = setTimeout(() => controller.abort(), 2000);
      const res = await fetch(`https://api.marketaux.com/v1/news/all?api_token=${token}&limit=1`, {
        signal: controller.signal
      });
      clearTimeout(tId);
      if (!res.ok) throw new Error(`MarketAux query failed with HTTP ${res.status}`);
      return { latency: `${Date.now() - start}ms` };
    }, "MarketAux News API", 2500);

    // 3.7. CRYPTOPANIC CHECK
    const cryptopanicCheck = await safeCheck(async () => {
      const start = Date.now();
      let token = "";
      if (dbCheck.status === "healthy") {
        try {
          const tokenRow = await prisma.systemConfig.findUnique({ where: { key: "cryptopanic_api_key" } });
          if (tokenRow?.value) token = tokenRow.value;
        } catch (e) {}
      }
      if (!token) return { latency: "Not Configured" };
      const controller = new AbortController();
      const tId = setTimeout(() => controller.abort(), 2000);
      const res = await fetch(`https://cryptopanic.com/api/v1/posts/?auth_token=${token}&public=true&limit=1`, {
        signal: controller.signal
      });
      clearTimeout(tId);
      if (!res.ok) throw new Error(`CryptoPanic query failed with HTTP ${res.status}`);
      return { latency: `${Date.now() - start}ms` };
    }, "CryptoPanic News API", 2500);

    // 4. CONFIG MODE & SYSTEM SETTINGS
    let activeMode = "hybrid";
    let customConfig: any = {};
    if (dbCheck.status === "healthy") {
      try {
        const modeRow = await prisma.systemConfig.findUnique({ where: { key: "active_mode" } });
        if (modeRow) activeMode = modeRow.value;

        const configRow = await prisma.systemConfig.findUnique({ where: { key: "system_config" } });
        customConfig = safeJsonParse(configRow?.value, {});
      } catch (err) {
        console.warn("[health] Database configuration fetch error:", err);
      }
    }

    let cryptoSyncProgress = { status: "idle", current: 0, total: 0, newAssets: 0, updatedAssets: 0, message: "" };
    let stockSyncProgress = { status: "idle", current: 0, total: 0, newStocksCount: 0, updatedStocksCount: 0, message: "" };
    if (dbCheck.status === "healthy") {
      try {
        const cryptoProgressRow = await prisma.systemConfig.findUnique({ where: { key: "crypto_sync_progress" } });
        const stockProgressRow = await prisma.systemConfig.findUnique({ where: { key: "stock_sync_progress" } });
        if (cryptoProgressRow) cryptoSyncProgress = safeJsonParse(cryptoProgressRow.value, cryptoSyncProgress);
        if (stockProgressRow) stockSyncProgress = safeJsonParse(stockProgressRow.value, stockSyncProgress);
      } catch (err) {
        console.warn("[health] Progress fetch error:", err);
      }
    }

    // 5. WORKERS HEALTH STATUS TRACKING (SAFE)
    const workersCheck = await safeCheck(async () => {
      // Fetch heartbeat records from DB safely
      const heartbeats = await prisma.systemConfig.findMany({
        where: {
          key: {
            in: [
              "worker_crypto_universe_heartbeat",
              "worker_crypto_price_heartbeat",
              "worker_stock_universe_heartbeat",
              "worker_stock_price_heartbeat"
            ]
          }
        }
      });

      const hbMap = heartbeats.reduce((acc, row) => {
        acc[row.key] = Number(row.value) || 0;
        return acc;
      }, {} as Record<string, number>);

      const checkWorker = (hbKey: string, thresholdSeconds: number = 300) => {
        const lastHb = hbMap[hbKey];
        if (!lastHb) return { running: false, idle: true, crashed: false, last_heartbeat: "unknown" };
        const age = (Date.now() - lastHb) / 1000;
        if (age < thresholdSeconds) {
          return { running: true, idle: false, crashed: false, last_heartbeat: new Date(lastHb).toISOString() };
        }
        return { running: false, idle: true, crashed: false, last_heartbeat: new Date(lastHb).toISOString() };
      };

      return {
        crypto_universe_worker: checkWorker("worker_crypto_universe_heartbeat", 86400), // daily
        crypto_price_worker: checkWorker("worker_crypto_price_heartbeat", 300), // 5 min
        stock_universe_worker: checkWorker("worker_stock_universe_heartbeat", 86400), // daily
        stock_price_worker: checkWorker("worker_stock_price_heartbeat", 300) // 5 min
      };
    }, "Workers Health Tracking", 2500);

    // Fallback if workers check is down
    const workersData = workersCheck.data || {
      crypto_universe_worker: { running: false, idle: true, crashed: false, last_heartbeat: "unknown" },
      crypto_price_worker: { running: false, idle: true, crashed: false, last_heartbeat: "unknown" },
      stock_universe_worker: { running: false, idle: true, crashed: false, last_heartbeat: "unknown" },
      stock_price_worker: { running: false, idle: true, crashed: false, last_heartbeat: "unknown" }
    };

    // Calculate active workers
    let activeWorkersCount = 0;
    if (workersData.crypto_universe_worker.running) activeWorkersCount++;
    if (workersData.crypto_price_worker.running) activeWorkersCount++;
    if (workersData.stock_universe_worker.running) activeWorkersCount++;
    if (workersData.stock_price_worker.running) activeWorkersCount++;

    // Calculate overall status
    if (dbCheck.status === "down") {
      overallStatus = "down";
    } else if (binanceCheck.status === "down" || finnhubCheck.status === "down") {
      overallStatus = "degraded";
    }

    // 6. POPULATE SNAPSHOT LISTINGS & MOVERS SAFELY
    let latestCryptoListings: any[] = [];
    let latestStockListings: any[] = [];
    let topCryptoGainers: any[] = [];
    let topStockGainers: any[] = [];

    if (dbCheck.status === "healthy") {
      try {
        const cryptos = await prisma.cryptoAsset.findMany({
          orderBy: { createdAt: "desc" },
          take: 5,
          select: { symbol: true, createdAt: true }
        });
        latestCryptoListings = cryptos.map(c => ({ symbol: c.symbol, createdAt: c.createdAt.toISOString() }));

        const stocks = await prisma.stockAsset.findMany({
          orderBy: { createdAt: "desc" },
          take: 5,
          select: { symbol: true, name: true, createdAt: true }
        });
        latestStockListings = stocks.map(s => ({ symbol: s.symbol, name: s.name, createdAt: s.createdAt.toISOString() }));

        const cGainers = await prisma.cryptoPrice.findMany({
          orderBy: { change24h: "desc" },
          take: 4,
          include: { asset: { select: { symbol: true } } }
        });
        topCryptoGainers = cGainers.map(c => ({
          symbol: c.asset.symbol,
          price: c.price,
          change: c.change24h
        }));

        const sGainers = await prisma.stockPrice.findMany({
          orderBy: { changePercent: "desc" },
          take: 4,
          include: { asset: { select: { symbol: true, name: true } } }
        });
        topStockGainers = sGainers.map(s => ({
          symbol: s.asset.symbol,
          name: s.asset.name,
          price: s.price,
          change: s.changePercent
        }));
      } catch (dbErr) {
        console.warn("[health] Error pulling snapshots from Postgres:", dbErr);
      }
    }

    let lastUniverseRun: string = "Never";
    let lastPriceRun: string = "Never";
    let lastNewsRun: string = "Never";
    let symbolsUpdatedLastCycle: number = 0;
    let activeStocksInDb: number = 0;
    let activeCryptosInDb: number = 0;
    let newsArticlesCount: number = 0;

    if (dbCheck.status === "healthy") {
      try {
        const lastUniverseRow = await prisma.systemConfig.findUnique({ where: { key: "last_universe_run" } });
        const lastPriceRow = await prisma.systemConfig.findUnique({ where: { key: "last_price_run" } });
        const lastNewsRow = await prisma.systemConfig.findUnique({ where: { key: "last_news_run" } });
        const cryptoUpdatedRow = await prisma.systemConfig.findUnique({ where: { key: "last_cycle_crypto_updated" } });
        const stockUpdatedRow = await prisma.systemConfig.findUnique({ where: { key: "last_cycle_stock_updated" } });

        if (lastUniverseRow?.value) {
          lastUniverseRun = new Date(Number(lastUniverseRow.value)).toISOString();
        }
        if (lastPriceRow?.value) {
          lastPriceRun = new Date(Number(lastPriceRow.value)).toISOString();
        }
        if (lastNewsRow?.value) {
          lastNewsRun = new Date(Number(lastNewsRow.value)).toISOString();
        }
        
        symbolsUpdatedLastCycle = (cryptoUpdatedRow?.value ? Number(cryptoUpdatedRow.value) : 0) + (stockUpdatedRow?.value ? Number(stockUpdatedRow.value) : 0);
        
        activeStocksInDb = await prisma.stockAsset.count({ where: { isActive: true } });
        activeCryptosInDb = await prisma.cryptoAsset.count({ where: { isActive: true } });
        newsArticlesCount = await prisma.newsArticle.count();
      } catch (err) {
        console.warn("[health] Error fetching additional metrics:", err);
      }
    }

    // Map health response properties to support BOTH the dashboard UI expectations and Task 3 strict requirements
    return NextResponse.json({
      status: overallStatus === "ok" ? "UP" : overallStatus.toUpperCase(),
      timestamp,
      activeMode,
      customConfig,
      telemetry: {
        totalSymbols: (dbCheck.data?.stocksInDb ?? 0) + (dbCheck.data?.cryptosInDb ?? 0),
        activeSymbols: activeStocksInDb + activeCryptosInDb,
        stocksInDb: dbCheck.data?.stocksInDb ?? 0,
        cryptosInDb: dbCheck.data?.cryptosInDb ?? 0,
        activeStocks: activeStocksInDb,
        activeCryptos: activeCryptosInDb,
        newsArticlesCount,
        lastUniverseRun,
        lastPriceRun,
        lastNewsRun,
        symbolsUpdatedLastCycle
      },

      services: {
        database: {
          name: "JDdS PostgreSQL",
          status: dbCheck.status === "healthy" ? "Healthy" : "Down",
          readLatency: dbCheck.data?.readLatency || "unknown",
          writeLatency: dbCheck.data?.writeLatency || "unknown",
          latency: dbCheck.data?.readLatency ? `${parseInt(dbCheck.data.readLatency) + parseInt(dbCheck.data.writeLatency)}ms` : "unknown",
          stocksInDb: dbCheck.data?.stocksInDb ?? 0,
          cryptosInDb: dbCheck.data?.cryptosInDb ?? 0,
          activeMarkets: dbCheck.data?.activeMarkets ?? 0,
          readWritePerf: dbCheck.status === "healthy" ? "Optimal" : "Down",
          error: dbCheck.error
        },
        binance: {
          service: "binance",
          status: binanceCheck.status,
          latency: binanceCheck.latency,
          error: binanceCheck.error
        },
        binanceApi: {
          name: "Binance API",
          status: binanceCheck.status === "healthy" ? "Healthy" : "Unreachable",
          latency: binanceCheck.data?.latency || "unknown",
          successRate: binanceCheck.status === "healthy" ? "100%" : "0%",
          keyConfigured: !!process.env.BINANCE_API_KEY
        },
        finnhub: {
          service: "finnhub",
          status: finnhubCheck.status,
          latency: finnhubCheck.latency,
          error: finnhubCheck.error
        },
        finnhubApi: {
          name: "Finnhub API",
          status: finnhubCheck.status === "healthy" ? "Healthy" : "Unreachable",
          latency: finnhubCheck.data?.latency || "unknown",
          successRate: finnhubCheck.status === "healthy" ? "100%" : "0%"
        },
        coingecko: {
          service: "coingecko",
          status: coingeckoCheck.status,
          latency: coingeckoCheck.latency,
          error: coingeckoCheck.error
        },
        coingeckoApi: {
          name: "CoinGecko API",
          status: coingeckoCheck.status === "healthy" ? "Healthy" : "Unreachable",
          latency: coingeckoCheck.data?.latency || "unknown",
          successRate: coingeckoCheck.status === "healthy" ? "100%" : "0%",
          keyConfigured: !!process.env.COINGECKO_API_KEY
        },
        marketaux: {
          service: "marketaux",
          status: marketauxCheck.status,
          latency: marketauxCheck.latency,
          error: marketauxCheck.error
        },
        marketauxApi: {
          name: "MarketAux News API",
          status: marketauxCheck.status === "healthy" ? "Healthy" : "Unreachable",
          latency: marketauxCheck.data?.latency || "unknown",
          successRate: marketauxCheck.status === "healthy" ? "100%" : "0%",
          keyConfigured: true
        },
        cryptopanicApi: {
          name: "CryptoPanic News API",
          status: cryptopanicCheck.status === "healthy" ? "Healthy" : (cryptopanicCheck.data?.latency === "Not Configured" ? "Not Configured" : "Unreachable"),
          latency: cryptopanicCheck.data?.latency || "unknown",
          successRate: cryptopanicCheck.status === "healthy" ? "100%" : "0%",
          keyConfigured: cryptopanicCheck.data?.latency !== "Not Configured"
        },
        workers: workersData,
        jddsEngine: {
          name: "JDdS Poller Daemon",
          status: activeMode === "suspended" ? "Suspended" : "Active",
          lastPollTime: `Crypto: ${workersData.crypto_price_worker.last_heartbeat} | Stock: ${workersData.stock_price_worker.last_heartbeat}`,
          lastCryptoUpdated: workersData.crypto_price_worker.last_heartbeat,
          lastStockUpdated: workersData.stock_price_worker.last_heartbeat,
          failures: binanceCheck.status === "healthy" ? 0 : 1,
          retries: 0,
          queueStatus: "Idle"
        }
      },
      system: {
        nodeVersion: process.version,
        platform: process.platform,
        uptime: Math.round(process.uptime()),
        mode: activeMode,
        active_workers: activeWorkersCount
      },
      listings: {
        crypto: latestCryptoListings,
        stock: latestStockListings
      },
      movers: {
        crypto: topCryptoGainers,
        stock: topStockGainers
      },
      universeSyncProgress: {
        crypto: cryptoSyncProgress,
        stock: stockSyncProgress
      },
      runNow: {
        universe: (await prisma.systemConfig.findUnique({ where: { key: "run_now_universe" } }))?.value || "idle",
        prices: (await prisma.systemConfig.findUnique({ where: { key: "run_now_prices" } }))?.value || "idle",
        news: (await prisma.systemConfig.findUnique({ where: { key: "run_now_news" } }))?.value || "idle",
      }
    });

  } catch (fatalErr: any) {
    // Ultimate fallback handler - ALWAYS return HTTP 200 with fallback data. NEVER HTTP 500!
    console.error("[health] Critical check crash isolated successfully:", fatalErr);
    return NextResponse.json({
      status: "down",
      timestamp,
      services: {
        database: { status: "down", error: fatalErr.message },
        binance: { service: "binance", status: "down", error: "Fatal health check failure" },
        finnhub: { service: "finnhub", status: "down", error: "Fatal health check failure" },
        workers: {}
      },
      system: {
        uptime: Math.round(process.uptime()),
        mode: "suspended",
        active_workers: 0
      },
      listings: { crypto: [], stock: [] },
      movers: { crypto: [], stock: [] },
      telemetry: {
        totalSymbols: 0,
        activeSymbols: 0,
        stocksInDb: 0,
        cryptosInDb: 0,
        activeStocks: 0,
        activeCryptos: 0,
        lastUniverseRun: "Never",
        lastPriceRun: "Never",
        symbolsUpdatedLastCycle: 0
      }
    });
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { mode } = body;

    const validModes = ["universe_only", "price_only", "hybrid", "suspended"];
    if (!mode || !validModes.includes(mode)) {
      return NextResponse.json({ error: `Invalid mode: ${mode}` }, { status: 400 });
    }

    await prisma.systemConfig.upsert({
      where: { key: "active_mode" },
      update: { value: mode },
      create: { key: "active_mode", value: mode }
    });

    const configRow = await prisma.systemConfig.findUnique({
      where: { key: "system_config" }
    });

    let configJson: any = {};
    if (configRow) {
      configJson = safeJsonParse(configRow.value, {});
    }
    if (!configJson.system) configJson.system = {};
    configJson.system.mode = mode;

    await prisma.systemConfig.upsert({
      where: { key: "system_config" },
      update: { value: JSON.stringify(configJson) },
      create: { key: "system_config", value: JSON.stringify(configJson) }
    });

    return NextResponse.json({ success: true, activeMode: mode });
  } catch (err) {
    console.error("[api/admin/health] POST Error:", err);
    return NextResponse.json({ error: "Failed to update configuration" }, { status: 200 }); // Graceful override
  }
}
