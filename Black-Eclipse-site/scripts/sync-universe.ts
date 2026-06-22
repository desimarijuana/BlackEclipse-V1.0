import "dotenv/config";
import { prisma } from "../src/lib/prisma";

const finnhubToken = process.env.FINNHUB_TOKEN || process.env.FINNHUB_API_KEY || "d8gau59r01qlgcuietn0d8gau59r01qlgcuietng";

// Retry wrapper helper
async function retryOperation<T>(operation: () => Promise<T>, label: string, retries: number = 3): Promise<T> {
  let attempt = 0;
  while (true) {
    try {
      return await operation();
    } catch (err) {
      attempt++;
      console.warn(`[sync-retry] ${label} attempt ${attempt} failed:`, err instanceof Error ? err.message : err);
      if (attempt >= retries) {
        throw new Error(`${label} failed after ${retries} attempts.`);
      }
      await new Promise(r => setTimeout(r, 2000));
    }
  }
}

export async function syncCryptoUniverse() {
  console.log("Universe sync started (crypto)");

  // Set initial status to PostgreSQL
  await prisma.systemConfig.upsert({
    where: { key: "crypto_sync_progress" },
    update: { value: JSON.stringify({ current: 0, total: 100, newAssets: 0, updatedAssets: 0, status: "running", message: "Fetching exchange data..." }) },
    create: { key: "crypto_sync_progress", value: JSON.stringify({ current: 0, total: 100, newAssets: 0, updatedAssets: 0, status: "running", message: "Fetching exchange data..." }) }
  });

  let info: any = null;

  try {
    info = await retryOperation(async () => {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 8000);
      const res = await fetch("https://api.binance.com/api/v3/exchangeInfo", { signal: controller.signal });
      clearTimeout(timeout);
      if (!res.ok) throw new Error(`Binance exchangeInfo HTTP ${res.status}`);
      return await res.json();
    }, "Fetch Binance ExchangeInfo");
  } catch (err: any) {
    await prisma.systemConfig.upsert({
      where: { key: "crypto_sync_progress" },
      update: { value: JSON.stringify({ current: 0, total: 0, newAssets: 0, updatedAssets: 0, status: "failed", message: err.message }) },
      create: { key: "crypto_sync_progress", value: JSON.stringify({ current: 0, total: 0, newAssets: 0, updatedAssets: 0, status: "failed", message: err.message }) }
    });
    console.error("[crypto-sync] Fatal: Failed to fetch Binance exchangeInfo:", err.message);
    throw err;
  }

  const usdtSymbols = info.symbols.filter(
    (s: any) => s.quoteAsset === "USDT" &&
                !s.symbol.includes("UP") &&
                !s.symbol.includes("DOWN") &&
                !s.symbol.includes("BULL") &&
                !s.symbol.includes("BEAR")
  );

  console.log(`Fetched ${usdtSymbols.length} symbols from Binance`);

  // Deactivate symbols completely missing from the returned Binance list
  const fetchedBaseAssets = new Set<string>(usdtSymbols.map((s: any) => s.baseAsset));
  const missingDeactivated = await prisma.cryptoAsset.updateMany({
    where: {
      symbol: { notIn: Array.from(fetchedBaseAssets) },
      isActive: true
    },
    data: {
      isActive: false
    }
  });
  if (missingDeactivated.count > 0) {
    console.log(`Deactivated ${missingDeactivated.count} crypto assets missing from Binance registry.`);
  }
  
  // Optimize using bulk operations
  const existingAssets = await prisma.cryptoAsset.findMany();
  const existingMap = new Map(existingAssets.map(a => [a.symbol, a]));

  const newAssetsData: any[] = [];
  const updatedAssetIdsToTrading: string[] = [];
  const updatedAssetIdsToNotTrading: string[] = [];

  for (const s of usdtSymbols) {
    const base = s.baseAsset;
    const isTrading = s.status === "TRADING";
    const existing = existingMap.get(base);
    
    if (!existing) {
      newAssetsData.push({
        symbol: base,
        isActive: isTrading,
        firstSeen: new Date(),
        lastSeen: new Date()
      });
    } else {
      if (isTrading) {
        updatedAssetIdsToTrading.push(existing.id);
      } else {
        updatedAssetIdsToNotTrading.push(existing.id);
      }
    }
  }

  if (newAssetsData.length > 0) {
    await prisma.cryptoAsset.createMany({
      data: newAssetsData,
      skipDuplicates: true
    });
  }

  if (updatedAssetIdsToTrading.length > 0) {
    await prisma.cryptoAsset.updateMany({
      where: { id: { in: updatedAssetIdsToTrading } },
      data: { isActive: true, lastSeen: new Date() }
    });
  }
  if (updatedAssetIdsToNotTrading.length > 0) {
    await prisma.cryptoAsset.updateMany({
      where: { id: { in: updatedAssetIdsToNotTrading } },
      data: { isActive: false, lastSeen: new Date() }
    });
  }

  const allAssets = await prisma.cryptoAsset.findMany();
  const assetMap = new Map(allAssets.map(a => [a.symbol, a.id]));

  const existingMarkets = await prisma.cryptoMarket.findMany();
  const existingMarketsMap = new Map(existingMarkets.map(m => [m.symbol, m]));

  const newMarketsData: any[] = [];
  const updatedMarketsToTrading: string[] = [];
  const updatedMarketsToNotTrading: string[] = [];

  for (const s of usdtSymbols) {
    const assetId = assetMap.get(s.baseAsset);
    if (!assetId) continue;

    const existingMarket = existingMarketsMap.get(s.symbol);
    if (!existingMarket) {
      newMarketsData.push({
        assetId,
        symbol: s.symbol,
        baseAsset: s.baseAsset,
        quoteAsset: s.quoteAsset,
        exchange: "binance",
        status: s.status
      });
    } else {
      if (existingMarket.status !== s.status) {
        if (s.status === "TRADING") {
          updatedMarketsToTrading.push(existingMarket.id);
        } else {
          updatedMarketsToNotTrading.push(existingMarket.id);
        }
      }
    }
  }

  if (newMarketsData.length > 0) {
    await prisma.cryptoMarket.createMany({
      data: newMarketsData,
      skipDuplicates: true
    });
  }

  if (updatedMarketsToTrading.length > 0) {
    await prisma.cryptoMarket.updateMany({
      where: { id: { in: updatedMarketsToTrading } },
      data: { status: "TRADING", updatedAt: new Date() }
    });
  }
  if (updatedMarketsToNotTrading.length > 0) {
    await prisma.cryptoMarket.updateMany({
      where: { id: { in: updatedMarketsToNotTrading } },
      data: { status: "BREAK", updatedAt: new Date() }
    });
  }

  const newAssets = newAssetsData.length;
  const updatedAssets = updatedAssetIdsToTrading.length + updatedAssetIdsToNotTrading.length;

  await prisma.systemConfig.upsert({
    where: { key: "crypto_sync_progress" },
    update: { value: JSON.stringify({ current: usdtSymbols.length, total: usdtSymbols.length, newAssets, updatedAssets, status: "idle", message: "Completed" }) },
    create: { key: "crypto_sync_progress", value: JSON.stringify({ current: usdtSymbols.length, total: usdtSymbols.length, newAssets, updatedAssets, status: "idle", message: "Completed" }) }
  });

  console.log(`Inserted ${newAssets} new assets`);
  console.log(`Updated ${updatedAssets} existing assets`);
  console.log("Universe sync completed");

  return { newAssets, updatedAssets };
}

export async function syncStockUniverse() {
  console.log("Stock universe sync started");

  // Set initial status to PostgreSQL
  await prisma.systemConfig.upsert({
    where: { key: "stock_sync_progress" },
    update: { value: JSON.stringify({ current: 0, total: 100, newStocksCount: 0, updatedStocksCount: 0, status: "running", message: "Fetching registry data..." }) },
    create: { key: "stock_sync_progress", value: JSON.stringify({ current: 0, total: 100, newStocksCount: 0, updatedStocksCount: 0, status: "running", message: "Fetching registry data..." }) }
  });

  let stocksList: Array<{ symbol: string; description: string }> = [];

  try {
    stocksList = await retryOperation(async () => {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 8000);
      const res = await fetch(`https://finnhub.io/api/v1/stock/symbol?exchange=US&token=${finnhubToken}`, { signal: controller.signal });
      clearTimeout(timeout);
      if (!res.ok) throw new Error(`Finnhub API US symbol list HTTP ${res.status}`);
      return await res.json();
    }, "Fetch Finnhub stock universe");
  } catch (err: any) {
    await prisma.systemConfig.upsert({
      where: { key: "stock_sync_progress" },
      update: { value: JSON.stringify({ current: 0, total: 0, newStocksCount: 0, updatedStocksCount: 0, status: "failed", message: err.message }) },
      create: { key: "stock_sync_progress", value: JSON.stringify({ current: 0, total: 0, newStocksCount: 0, updatedStocksCount: 0, status: "failed", message: err.message }) }
    });
    console.error("[stock-sync] Fatal: Failed to fetch Finnhub stocks list:", err.message);
    throw err;
  }

  if (!Array.isArray(stocksList) || stocksList.length === 0) {
    throw new Error("Invalid Finnhub stock list structure");
  }

  const coreSymbolsSet = new Set(CORE_STOCKS.map(s => s.symbol));
  const filteredStocks = stocksList.filter(s => coreSymbolsSet.has(s.symbol) || (s.symbol.length <= 5 && /^[A-Z]+$/.test(s.symbol)));

  console.log(`Fetched ${filteredStocks.length} filtered stocks from Finnhub`);

  // Deactivate stocks completely missing from filtered stocks list
  const filteredSymbolsSet = new Set<string>(filteredStocks.map((s: any) => s.symbol));
  const missingDeactivated = await prisma.stockAsset.updateMany({
    where: {
      symbol: { notIn: Array.from(filteredSymbolsSet) },
      isActive: true
    },
    data: {
      isActive: false
    }
  });
  if (missingDeactivated.count > 0) {
    console.log(`Deactivated ${missingDeactivated.count} stock assets missing from active list.`);
  }

  const existingStocks = await prisma.stockAsset.findMany();
  const existingSet = new Set(existingStocks.map(s => s.symbol));

  const newStocksData: any[] = [];
  const seenSymbols: string[] = [];

  for (const s of filteredStocks) {
    seenSymbols.push(s.symbol);
    if (!existingSet.has(s.symbol)) {
      const isCore = coreSymbolsSet.has(s.symbol);
      newStocksData.push({
        symbol: s.symbol,
        name: s.description || s.symbol,
        isActive: isCore,
        firstSeen: new Date(),
        lastSeen: new Date()
      });
    }
  }

  if (newStocksData.length > 0) {
    // Batch inserts to prevent payload constraints on postgres
    const batchSize = 1000;
    for (let i = 0; i < newStocksData.length; i += batchSize) {
      const batch = newStocksData.slice(i, i + batchSize);
      await prisma.stockAsset.createMany({
        data: batch,
        skipDuplicates: true
      });
    }
  }

  if (seenSymbols.length > 0) {
    const batchSize = 1000;
    for (let i = 0; i < seenSymbols.length; i += batchSize) {
      const batch = seenSymbols.slice(i, i + batchSize);
      await prisma.stockAsset.updateMany({
        where: { symbol: { in: batch } },
        data: { lastSeen: new Date() }
      });
    }
  }

  const newStocksCount = newStocksData.length;
  const updatedStocksCount = filteredStocks.length - newStocksCount;

  await prisma.systemConfig.upsert({
    where: { key: "stock_sync_progress" },
    update: { value: JSON.stringify({ current: filteredStocks.length, total: filteredStocks.length, newStocksCount, updatedStocksCount, status: "idle", message: "Completed" }) },
    create: { key: "stock_sync_progress", value: JSON.stringify({ current: filteredStocks.length, total: filteredStocks.length, newStocksCount, updatedStocksCount, status: "idle", message: "Completed" }) }
  });

  console.log(`Inserted ${newStocksCount} new stocks`);
  console.log("Completed stock universe sync");

  return { newStocksCount, updatedStocksCount };
}

const CORE_STOCKS = [
  // Crypto Majors
  { symbol: "BTC", name: "Bitcoin" },
  { symbol: "ETH", name: "Ethereum" },
  { symbol: "SOL", name: "Solana" },
  { symbol: "BNB", name: "Binance Coin" },
  { symbol: "ADA", name: "Cardano" },
  { symbol: "XRP", name: "Ripple" },
  { symbol: "DOT", name: "Polkadot" },
  { symbol: "DOGE", name: "Dogecoin" },

  // Commodities
  { symbol: "GC=F", name: "Gold Futures" },
  { symbol: "SI=F", name: "Silver Futures" },
  { symbol: "CL=F", name: "Crude Oil Futures" },
  { symbol: "NG=F", name: "Natural Gas Futures" },

  // Forex
  { symbol: "EURUSD=X", name: "EUR/USD" },
  { symbol: "GBPUSD=X", name: "GBP/USD" },
  { symbol: "USDJPY=X", name: "USD/JPY" },
  { symbol: "AUDUSD=X", name: "AUD/USD" },
  { symbol: "USDCAD=X", name: "USD/CAD" },
  { symbol: "USDCHF=X", name: "USD/CHF" },

  // Stocks (Famous Stocks)
  { symbol: "AAPL", name: "Apple Inc" },
  { symbol: "MSFT", name: "Microsoft Corp" },
  { symbol: "NVDA", name: "NVIDIA Corp" },
  { symbol: "AMZN", name: "Amazon.com Inc" },
  { symbol: "GOOGL", name: "Alphabet Inc" },
  { symbol: "META", name: "Meta Platforms Inc" },
  { symbol: "TSLA", name: "Tesla Inc" },
  { symbol: "NFLX", name: "Netflix Inc" },
  { symbol: "LLY", name: "Eli Lilly & Co" },
  { symbol: "V", name: "Visa Inc" },
  { symbol: "JPM", name: "JPMorgan Chase & Co" },
  { symbol: "UNH", name: "UnitedHealth Group Inc" },
  { symbol: "AVGO", name: "Broadcom Inc" },
  { symbol: "XOM", name: "Exxon Mobil Corp" },
  { symbol: "WMT", name: "Walmart Inc" },
  { symbol: "PG", name: "Procter & Gamble Co" },
  { symbol: "JNJ", name: "Johnson & Johnson" },
  { symbol: "MA", name: "Mastercard Inc" },
  { symbol: "HD", name: "Home Depot Inc" },
  { symbol: "MRK", name: "Merck & Co Inc" },
  { symbol: "COST", name: "Costco Wholesale Corp" },
  { symbol: "ABBV", name: "AbbVie Inc" },
  { symbol: "AMD", name: "Advanced Micro Devices Inc" },
  { symbol: "CRM", name: "Salesforce Inc" },
  { symbol: "ADBE", name: "Adobe Inc" },
  { symbol: "CVX", name: "Chevron Corp" },
  { symbol: "BAC", name: "Bank of America Corp" },
  { symbol: "PEP", name: "PepsiCo Inc" },
  { symbol: "KO", name: "Coca-Cola Co" },
  { symbol: "TMO", name: "Thermo Fisher Scientific Inc" },
  { symbol: "WFC", name: "Wells Fargo & Co" },
  { symbol: "CSCO", name: "Cisco Systems Inc" },
  { symbol: "QCOM", name: "Qualcomm Inc" },
  { symbol: "MCD", name: "McDonald's Corp" },
  { symbol: "GE", name: "General Electric Co" },
  { symbol: "INTC", name: "Intel Corp" },
  { symbol: "CAT", name: "Caterpillar Inc" },
  { symbol: "DIS", name: "Walt Disney Co" },
  { symbol: "DHR", name: "Danaher Corp" },
  { symbol: "VZ", name: "Verizon Communications Inc" },

  // Stock Market Indices
  { symbol: "SPX", name: "S&P 500 Index" },
  { symbol: "IXIC", name: "Nasdaq Composite Index" },
  { symbol: "DJI", name: "Dow Jones Industrial Average" },
  { symbol: "RUT", name: "Russell 2000 Index" },
  { symbol: "^GSPC", name: "S&P 500 Index (^GSPC)" },
  { symbol: "^IXIC", name: "Nasdaq Composite Index (^IXIC)" },
  { symbol: "^DJI", name: "Dow Jones Industrial Average (^DJI)" },
  { symbol: "^RUT", name: "Russell 2000 Index (^RUT)" }
];

async function main() {
  console.log("╔══════════════════════════════════════════════════════════╗");
  console.log("║           JDdS ENGINE — Market Universe Sync             ║");
  console.log("╚══════════════════════════════════════════════════════════╝\n");

  const runCrypto = process.argv.includes("--crypto") || !process.argv.includes("--stocks");
  const runStocks = process.argv.includes("--stocks") || !process.argv.includes("--crypto");

  try {
    if (runCrypto) {
      await syncCryptoUniverse();
    }
    if (runStocks) {
      await syncStockUniverse();
    }
    console.log("\n[universe-sync] Universe synchronization completed successfully.");
    process.exit(0);
  } catch (err) {
    console.error("\n[universe-sync] Synchronization failed:", err);
    process.exit(1);
  }
}

if (process.argv[1] && (process.argv[1].endsWith("sync-universe.ts") || process.argv[1].endsWith("sync-universe.js") || process.argv[1].includes("sync-universe"))) {
  main();
}
