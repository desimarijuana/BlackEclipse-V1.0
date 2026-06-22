import "dotenv/config";
import { prisma } from "../src/lib/prisma";
import { syncCryptoUniverse, syncStockUniverse } from "./sync-universe";
import { getBestProvider } from "../src/lib/providers/provider-registry";


// ─── NEW CONFIG SCHEMA (NO HARDCODED INTERVALS) ─────────────────────────────

const DEFAULT_CONFIG = {
  crypto: {
    universeEnabled: true,
    universeSyncInterval: 3600, // seconds (default: 1 hour)
    priceEnabled: true,
    priceUpdateInterval: 120, // seconds (default: 2 min)
  },
  stocks: {
    universeEnabled: true,
    universeSyncInterval: 3600,
    priceEnabled: true,
    priceUpdateInterval: 120,
  },
  api: {
    binanceEnabled: true,
    finnhubEnabled: true,
    timeout: 4000,
    retryCount: 3
  },
  system: {
    globalPause: false,
    mode: "hybrid" // hybrid | universe_only | price_only | suspended
  }
};

let currentConfig = JSON.parse(JSON.stringify(DEFAULT_CONFIG));

// ─── CONFIG MIGRATION (old format → new format) ─────────────────────────────

function migrateConfig(raw: any): any {
  const config = { ...raw };
  if (config.crypto) {
    // Migrate old universeSyncSchedule → universeSyncInterval
    if (config.crypto.universeSyncSchedule && config.crypto.universeSyncInterval === undefined) {
      const map: Record<string, number> = { daily: 86400, weekly: 604800, monthly: 2592000 };
      config.crypto.universeSyncInterval = map[config.crypto.universeSyncSchedule] || 3600;
      delete config.crypto.universeSyncSchedule;
    }
    // Migrate old single `enabled` → split universeEnabled + priceEnabled
    if (config.crypto.enabled !== undefined && config.crypto.universeEnabled === undefined) {
      config.crypto.universeEnabled = config.crypto.enabled;
      config.crypto.priceEnabled = config.crypto.enabled;
      delete config.crypto.enabled;
    }
  }
  if (config.stocks) {
    if (config.stocks.universeSyncSchedule && config.stocks.universeSyncInterval === undefined) {
      const map: Record<string, number> = { daily: 86400, weekly: 604800, monthly: 2592000 };
      config.stocks.universeSyncInterval = map[config.stocks.universeSyncSchedule] || 3600;
      delete config.stocks.universeSyncSchedule;
    }
    if (config.stocks.enabled !== undefined && config.stocks.universeEnabled === undefined) {
      config.stocks.universeEnabled = config.stocks.enabled;
      config.stocks.priceEnabled = config.stocks.enabled;
      delete config.stocks.enabled;
    }
  }
  return config;
}

// ─── DYNAMIC CONFIG RELOADER ─────────────────────────────────────────────────

async function refreshConfig() {
  try {
    const configRow = await prisma.systemConfig.findUnique({
      where: { key: "system_config" }
    });
    const activeModeRow = await prisma.systemConfig.findUnique({
      where: { key: "active_mode" }
    });
    
    let config = JSON.parse(JSON.stringify(DEFAULT_CONFIG));
    if (configRow) {
      try {
        const raw = JSON.parse(configRow.value);
        const migrated = migrateConfig(raw);
        config = {
          crypto: { ...config.crypto, ...migrated.crypto },
          stocks: { ...config.stocks, ...migrated.stocks },
          api: { ...config.api, ...migrated.api },
          system: { ...config.system, ...migrated.system },
        };
      } catch (e) {
        // use default
      }
    }
    
    if (activeModeRow) {
      config.system.mode = activeModeRow.value;
    }
    
    currentConfig = config;
  } catch (err) {
    console.error("[daemon] Error reloading config from DB:", err);
  }
  // Reload every 3 seconds for responsive config changes
  setTimeout(refreshConfig, 3000);
}

// ─── RUN NOW SIGNAL DETECTION ───────────────────────────────────────────────

async function checkRunNowSignals(): Promise<{ universe: boolean; prices: boolean; news: boolean }> {
  const result = { universe: false, prices: false, news: false };
  
  try {
    const [universeSignal, pricesSignal, newsSignal] = await Promise.all([
      prisma.systemConfig.findUnique({ where: { key: "run_now_universe" } }),
      prisma.systemConfig.findUnique({ where: { key: "run_now_prices" } }),
      prisma.systemConfig.findUnique({ where: { key: "run_now_news" } }),
    ]);
    
    if (universeSignal?.value === "pending") {
      result.universe = true;
      // Immediately acknowledge — set to "running"
      await prisma.systemConfig.upsert({
        where: { key: "run_now_universe" },
        update: { value: "running" },
        create: { key: "run_now_universe", value: "running" }
      });
    }
    
    if (pricesSignal?.value === "pending") {
      result.prices = true;
      await prisma.systemConfig.upsert({
        where: { key: "run_now_prices" },
        update: { value: "running" },
        create: { key: "run_now_prices", value: "running" }
      });
    }

    if (newsSignal?.value === "pending") {
      result.news = true;
      await prisma.systemConfig.upsert({
        where: { key: "run_now_news" },
        update: { value: "running" },
        create: { key: "run_now_news", value: "running" }
      });
    }
  } catch (err) {
    console.error("[daemon] Error checking Run Now signals:", err);
  }
  
  return result;
}

async function clearRunNowSignal(key: string) {
  try {
    await prisma.systemConfig.upsert({
      where: { key },
      update: { value: "idle" },
      create: { key, value: "idle" }
    });
  } catch (err) {
    console.error(`[daemon] Error clearing ${key}:`, err);
  }
}

// ─── CRYPTO PRICE UPDATER (BINANCE REST BATCH) ────────────────────────────────

export async function updateCryptoPrices() {
  const ts = new Date().toISOString();
  
  try {
    if (!currentConfig.api.binanceEnabled) {
      console.log(`[crypto-prices] ${ts} — Skipped (Binance API disabled).`);
      return;
    }

    console.log(`[crypto-prices] ${ts} — Loading active crypto assets from DB...`);
    const assets = await prisma.cryptoAsset.findMany({
      where: { isActive: true },
      include: { markets: true }
    });

    if (assets.length === 0) {
      console.log(`[crypto-prices] ${ts} — No active crypto assets in DB. Skipping.`);
      return;
    }

    console.log(`[crypto-prices] ${ts} — Fetching live Binance tickers in batch...`);
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), currentConfig.api.timeout);
    
    const res = await fetch("https://api.binance.com/api/v3/ticker/24hr", {
      signal: controller.signal
    });
    clearTimeout(timeoutId);

    if (!res.ok) throw new Error(`Binance ticker endpoint returned HTTP ${res.status}`);
    const tickers: Array<{
      symbol: string;
      lastPrice: string;
      quoteVolume: string;
      priceChangePercent: string;
    }> = await res.json();

    if (!Array.isArray(tickers)) throw new Error("Invalid Binance ticker response structure");

    let updatedCount = 0;

    for (const asset of assets) {
      const market = asset.markets.find(m => m.quoteAsset === "USDT") || asset.markets[0];
      if (!market) continue;

      const ticker = tickers.find(t => t.symbol === market.symbol);
      if (!ticker) continue;

      const price = parseFloat(ticker.lastPrice) || 0;
      const volume = parseFloat(ticker.quoteVolume) || 0;
      const change24h = parseFloat(ticker.priceChangePercent) || 0;

      await prisma.cryptoPrice.upsert({
        where: { assetId: asset.id },
        update: {
          price,
          volume,
          change24h,
          lastUpdated: new Date()
        },
        create: {
          assetId: asset.id,
          price,
          volume,
          change24h,
          lastUpdated: new Date()
        }
      });

      updatedCount++;
    }

    console.log(`[crypto-prices] ${ts} — Successfully updated ${updatedCount}/${assets.length} crypto prices.`);
    
    // Write heartbeat to DB
    await prisma.systemConfig.upsert({
      where: { key: "worker_crypto_price_heartbeat" },
      update: { value: String(Date.now()) },
      create: { key: "worker_crypto_price_heartbeat", value: String(Date.now()) }
    });
    await prisma.systemConfig.upsert({
      where: { key: "last_price_run" },
      update: { value: String(Date.now()) },
      create: { key: "last_price_run", value: String(Date.now()) }
    });
    await prisma.systemConfig.upsert({
      where: { key: "last_cycle_crypto_updated" },
      update: { value: String(updatedCount) },
      create: { key: "last_cycle_crypto_updated", value: String(updatedCount) }
    });
  } catch (err) {
    console.error(`[crypto-prices] ${ts} — Error:`, err instanceof Error ? err.message : err);
  }
}

// ─── STOCK PRICE UPDATER (FINNHUB QUOTES) ─────────────────────────────────────

export async function updateStockPrices() {
  const ts = new Date().toISOString();
  const finnhubToken = process.env.FINNHUB_TOKEN || process.env.FINNHUB_API_KEY || "d8gau59r01qlgcuietn0d8gau59r01qlgcuietng";

  try {
    if (!currentConfig.api.finnhubEnabled) {
      console.log(`[stock-prices] ${ts} — Skipped (Finnhub API disabled).`);
      return;
    }

    console.log(`[stock-prices] ${ts} — Loading active stock assets from DB...`);
    const assets = await prisma.stockAsset.findMany({
      where: { isActive: true }
    });

    if (assets.length === 0) {
      console.log(`[stock-prices] ${ts} — No active stocks in DB. Skipping.`);
      return;
    }

    console.log(`[stock-prices] ${ts} — Polling quotes for ${assets.length} stocks from Finnhub in concurrent batches...`);
    let updatedCount = 0;
    const batchSize = 30;

    for (let i = 0; i < assets.length; i += batchSize) {
      // Re-verify global pause didn't change mid-run
      if (currentConfig.system.globalPause) {
        console.log(`[stock-prices] ${ts} — Ingestion aborted mid-run (paused: ${currentConfig.system.globalPause}).`);
        break;
      }

      const batch = assets.slice(i, i + batchSize);
      await Promise.all(batch.map(async (asset) => {
        try {
          const finnhubSym = asset.symbol === "SPX" ? "^GSPC" :
                             asset.symbol === "IXIC" ? "^IXIC" :
                             asset.symbol === "DJI" ? "^DJI" :
                             asset.symbol === "RUT" ? "^RUT" :
                             asset.symbol;

          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), currentConfig.api.timeout);

          const res = await fetch(`https://finnhub.io/api/v1/quote?symbol=${finnhubSym}&token=${finnhubToken}`, {
            signal: controller.signal
          });
          clearTimeout(timeoutId);

          if (!res.ok) {
            if (res.status === 429) {
              return; // Rate limit, skip for now
            }
            throw new Error(`HTTP ${res.status}`);
          }
          const quote = await res.json();

          if (quote?.c == null || quote.c === 0) return;

          const price = quote.c || 0;
          const changePercent = quote.dp || 0;

          let marketCap = 0;
          try {
            const metricController = new AbortController();
            const metricTimeoutId = setTimeout(() => metricController.abort(), currentConfig.api.timeout);
            
            const metricRes = await fetch(`https://finnhub.io/api/v1/stock/metric?symbol=${finnhubSym}&metric=all&token=${finnhubToken}`, {
              signal: metricController.signal
            });
            clearTimeout(metricTimeoutId);

            if (metricRes.ok) {
              const metrics = await metricRes.json();
              marketCap = (metrics?.metric?.marketCapitalization || 0) * 1_000_000;
            }
          } catch (mErr) {
            // Ignore metric fetch failure
          }

          await prisma.stockPrice.upsert({
            where: { assetId: asset.id },
            update: {
              price,
              changePercent,
              marketCap: marketCap > 0 ? marketCap : undefined,
              lastUpdated: new Date()
            },
            create: {
              assetId: asset.id,
              price,
              changePercent,
              marketCap: marketCap > 0 ? marketCap : 0,
              lastUpdated: new Date()
            }
          });

          updatedCount++;
        } catch (err) {
          // Ignore individual fetch failure
        }
      }));

      // Small delay between batches to respect rate limits
      await new Promise(r => setTimeout(r, 1000));
    }

    console.log(`[stock-prices] ${ts} — Finished stock prices poll. Successfully updated: ${updatedCount}/${assets.length}`);
    
    // Write heartbeat to DB
    await prisma.systemConfig.upsert({
      where: { key: "worker_stock_price_heartbeat" },
      update: { value: String(Date.now()) },
      create: { key: "worker_stock_price_heartbeat", value: String(Date.now()) }
    });
    await prisma.systemConfig.upsert({
      where: { key: "last_price_run" },
      update: { value: String(Date.now()) },
      create: { key: "last_price_run", value: String(Date.now()) }
    });
    await prisma.systemConfig.upsert({
      where: { key: "last_cycle_stock_updated" },
      update: { value: String(updatedCount) },
      create: { key: "last_cycle_stock_updated", value: String(updatedCount) }
    });
  } catch (err) {
    console.error(`[stock-prices] ${ts} — Fatal error:`, err instanceof Error ? err.message : err);
  }
}

// ─── UNIVERSE SYNC EXECUTOR ─────────────────────────────────────────────────

async function executeUniverseSync() {
  const ts = new Date().toISOString();
  console.log(`[daemon] ${ts} — Executing universe sync...`);
  
  // Set heartbeats
  const now = Date.now();
  await Promise.all([
    prisma.systemConfig.upsert({
      where: { key: "worker_crypto_universe_heartbeat" },
      update: { value: String(now) },
      create: { key: "worker_crypto_universe_heartbeat", value: String(now) }
    }),
    prisma.systemConfig.upsert({
      where: { key: "worker_stock_universe_heartbeat" },
      update: { value: String(now) },
      create: { key: "worker_stock_universe_heartbeat", value: String(now) }
    }),
  ]);

  try {
    await syncCryptoUniverse();
    await syncStockUniverse();
    
    // Record last run time
    await prisma.systemConfig.upsert({
      where: { key: "last_universe_run" },
      update: { value: String(Date.now()) },
      create: { key: "last_universe_run", value: String(Date.now()) }
    });
    
    console.log(`[daemon] Universe sync completed successfully.`);
  } catch (err) {
    console.error("[daemon] Universe sync error:", err);
  }
}

async function executePricePolling() {
  const ts = new Date().toISOString();
  console.log(`[daemon] ${ts} — Executing price polling...`);
  
  try {
    if (currentConfig.crypto.priceEnabled) {
      await updateCryptoPrices();
    }
    if (currentConfig.stocks.priceEnabled) {
      await updateStockPrices();
    }
    console.log(`[daemon] Price polling completed.`);
  } catch (err) {
    console.error("[daemon] Price polling error:", err);
  }
}

async function executeGeckoSync() {
  const apiKey = process.env.COINGECKO_API_KEY;
  if (!apiKey) {
    console.log("[CoinGecko-Sync] No COINGECKO_API_KEY configured in environment. Skipping.");
    return;
  }

  try {
    console.log("[CoinGecko-Sync] Ingesting fundamental metrics from CoinGecko...");
    const url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=250&page=1";
    
    const res = await fetch(url, {
      headers: {
        "accept": "application/json",
        "x-cg-demo-api-key": apiKey
      }
    });

    if (!res.ok) throw new Error(`CoinGecko API returned HTTP ${res.status}`);
    
    const coins = await res.json();
    if (!Array.isArray(coins)) throw new Error("Invalid CoinGecko response structure");

    console.log(`[CoinGecko-Sync] Fetched ${coins.length} coins. Upserting to db...`);
    
    const upserts = coins.map(coin => {
      const symbol = coin.symbol.toUpperCase();
      const payload = {
        marketCap: coin.market_cap,
        volume24h: coin.total_volume,
        circulatingSupply: coin.circulating_supply,
        totalSupply: coin.total_supply,
        maxSupply: coin.max_supply,
        ath: coin.ath,
        atl: coin.atl,
        rank: coin.market_cap_rank,
        athChangePercent: coin.ath_change_percentage,
        atlChangePercent: coin.atl_change_percentage,
        athDate: coin.ath_date,
        atlDate: coin.atl_date
      };

      return prisma.systemConfig.upsert({
        where: { key: `cg_metrics_${symbol}` },
        update: { value: JSON.stringify(payload) },
        create: { key: `cg_metrics_${symbol}`, value: JSON.stringify(payload) }
      });
    });

    await Promise.all(upserts);
    console.log("[CoinGecko-Sync] CoinGecko metrics upsert complete.");
  } catch (err: any) {
    console.error("[CoinGecko-Sync] Error during CoinGecko sync:", err.message || err);
  }
}

function analyzeSimpleSentiment(title: string, summary: string): { sentiment: string, impact: number } {
  const text = (title + " " + summary).toLowerCase();
  
  const bullishWords = [
    "grow", "surge", "rise", "gain", "beat", "upward", "bull", "breakout", 
    "record high", "positive", "buy", "upgrade", "soar", "high", "jump", 
    "expansion", "boost", "revenue surge", "outperform", "profit increase"
  ];
  
  const bearishWords = [
    "fall", "slide", "drop", "loss", "miss", "downward", "bear", "probe", 
    "lawsuit", "plunge", "negative", "sell", "downgrade", "slump", "low", 
    "decline", "investigation", "antitrust", "penalty", "deficit", "risk"
  ];

  let bullCount = 0;
  let bearCount = 0;

  bullishWords.forEach(w => {
    const regex = new RegExp("\\b" + w, "g");
    bullCount += (text.match(regex) || []).length;
  });

  bearishWords.forEach(w => {
    const regex = new RegExp("\\b" + w, "g");
    bearCount += (text.match(regex) || []).length;
  });

  if (bullCount > bearCount) {
    return { sentiment: 'bullish', impact: 1.0 + Math.round(bullCount * 8) / 10 };
  } else if (bearCount > bullCount) {
    return { sentiment: 'bearish', impact: -1.0 - Math.round(bearCount * 8) / 10 };
  }
  return { sentiment: 'neutral', impact: 0 };
}

async function executeNewsPolling() {
  console.log("[News-Sync] Executing market news synchronization...");
  try {
    const keys = await prisma.systemConfig.findMany({
      where: {
        key: { in: ["marketaux_api_key", "cryptopanic_api_key", "finnhub_api_key"] }
      }
    });

    const keyMap = keys.reduce((acc, k) => {
      acc[k.key] = k.value;
      return acc;
    }, {} as Record<string, string>);

    const marketauxToken = keyMap.marketaux_api_key || "lgw4jOLpqAJbbCIotGst7q79s7XFWFINOPe6EoCY";
    const cryptopanicToken = keyMap.cryptopanic_api_key || "";
    const finnhubToken = keyMap.finnhub_api_key || "d8gau59r01qlgcuietn0d8gau59r01qlgcuietng";

    const articlesToInsert: Array<{
      source: string;
      ticker?: string;
      headline: string;
      summary: string;
      sentiment: string;
      impactPercent: number;
      url?: string;
      publishedAt: Date;
    }> = [];

    // 1. Fetch MarketAux news
    if (marketauxToken) {
      try {
        const symbolsQuery = "AAPL,TSLA,NVDA,MSFT";
        const url = `https://api.marketaux.com/v1/news/all?api_token=${marketauxToken}&symbols=${symbolsQuery}&filter_entities=true&language=en&limit=10`;
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          if (data && Array.isArray(data.data)) {
            data.data.forEach((item: any) => {
              let sentimentScore = 0;
              let tickerSymbol: string | undefined = undefined;

              if (Array.isArray(item.entities) && item.entities.length > 0) {
                const primaryEntity = item.entities.find((e: any) => e.symbol && e.sentiment_score !== undefined) || item.entities[0];
                tickerSymbol = primaryEntity.symbol || undefined;
                sentimentScore = primaryEntity.sentiment_score || 0;
              }

              let sentiment = 'neutral';
              if (sentimentScore > 0.15) sentiment = 'bullish';
              else if (sentimentScore < -0.15) sentiment = 'bearish';

              const impact = Math.round(sentimentScore * 100) / 10;

              articlesToInsert.push({
                source: item.source || "MarketAux",
                ticker: tickerSymbol,
                headline: item.title,
                summary: item.description || item.snippet || "No summary available.",
                sentiment,
                impactPercent: impact !== 0 ? impact : (sentiment === 'bullish' ? 1.5 : sentiment === 'bearish' ? -1.5 : 0),
                url: item.url || undefined,
                publishedAt: new Date(item.published_at || Date.now())
              });
            });
          }
        }
      } catch (e) {
        console.error("[News-Sync] MarketAux fetch failed:", e);
      }
    }

    // 2. Fetch CryptoPanic
    if (cryptopanicToken) {
      try {
        const url = `https://cryptopanic.com/api/v1/posts/?auth_token=${cryptopanicToken}&public=true&limit=30`;
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          if (data && Array.isArray(data.results)) {
            data.results.forEach((item: any) => {
              let cryptoTicker: string | undefined = undefined;
              if (Array.isArray(item.currencies) && item.currencies.length > 0) {
                cryptoTicker = item.currencies[0].code;
              }

              let sentiment = 'neutral';
              let impact = 0;
              if (item.votes) {
                const bullishVotes = Number(item.votes.bullish || 0);
                const bearishVotes = Number(item.votes.bearish || 0);
                const totalVotes = bullishVotes + bearishVotes;
                if (totalVotes > 0) {
                  const ratio = (bullishVotes - bearishVotes) / totalVotes;
                  if (ratio > 0.2) sentiment = 'bullish';
                  else if (ratio < -0.2) sentiment = 'bearish';
                  impact = Math.round(ratio * 50) / 10;
                }
              }

              articlesToInsert.push({
                source: item.domain || "CryptoPanic",
                ticker: cryptoTicker,
                headline: item.title,
                summary: item.title,
                sentiment,
                impactPercent: impact !== 0 ? impact : (sentiment === 'bullish' ? 2.0 : sentiment === 'bearish' ? -2.0 : 0),
                url: item.url || undefined,
                publishedAt: new Date(item.published_at || Date.now())
              });
            });
          }
        }
      } catch (e) {
        console.error("[News-Sync] CryptoPanic fetch failed:", e);
      }
    }

    // 3. Fetch Finnhub General News
    if (finnhubToken) {
      try {
        const url = `https://finnhub.io/api/v1/news?category=general&token=${finnhubToken}`;
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          if (data && Array.isArray(data)) {
            data.slice(0, 100).forEach((item: any) => {
              const { sentiment, impact } = analyzeSimpleSentiment(item.headline || "", item.summary || "");
              articlesToInsert.push({
                source: item.source || "Finnhub",
                ticker: item.related || undefined,
                headline: item.headline,
                summary: item.summary || "No summary details available.",
                sentiment,
                impactPercent: impact,
                url: item.url || undefined,
                publishedAt: new Date(item.datetime * 1000)
              });
            });
          }
        }
      } catch (e) {
        console.error("[News-Sync] Finnhub fetch failed:", e);
      }

      // 4. Fetch Finnhub Crypto News
      try {
        const url = `https://finnhub.io/api/v1/news?category=crypto&token=${finnhubToken}`;
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          if (data && Array.isArray(data)) {
            data.slice(0, 100).forEach((item: any) => {
              const { sentiment, impact } = analyzeSimpleSentiment(item.headline || "", item.summary || "");
              articlesToInsert.push({
                source: item.source || "Finnhub (Crypto)",
                ticker: item.related || undefined,
                headline: item.headline,
                summary: item.summary || "No summary details available.",
                sentiment,
                impactPercent: impact,
                url: item.url || undefined,
                publishedAt: new Date(item.datetime * 1000)
              });
            });
          }
        }
      } catch (e) {
        console.error("[News-Sync] Finnhub crypto news fetch failed:", e);
      }
    }

    // Upsert into database safely
    console.log(`[News-Sync] Processing ${articlesToInsert.length} articles into PostgreSQL...`);
    let insertedCount = 0;
    for (const art of articlesToInsert) {
      if (!art.headline || art.headline.trim() === "") continue;
      try {
        await prisma.newsArticle.upsert({
          where: { headline: art.headline },
          update: {
            ticker: art.ticker,
            summary: art.summary,
            sentiment: art.sentiment,
            impactPercent: art.impactPercent,
            url: art.url,
            publishedAt: art.publishedAt
          },
          create: {
            source: art.source,
            ticker: art.ticker,
            headline: art.headline,
            summary: art.summary,
            sentiment: art.sentiment,
            impactPercent: art.impactPercent,
            url: art.url,
            publishedAt: art.publishedAt
          }
        });
        insertedCount++;
      } catch (err: any) {
        // Skip duplicates
      }
    }
    console.log(`[News-Sync] News synchronization complete. Ingested/updated ${insertedCount} articles.`);
    try {
      await prisma.systemConfig.upsert({
        where: { key: "last_news_run" },
        update: { value: String(Date.now()) },
        create: { key: "last_news_run", value: String(Date.now()) }
      });
    } catch (e) {}
  } catch (err: any) {
    console.error("[News-Sync] General poller failed:", err.message || err);
  }
}

// ─── HISTORICAL DOWNLOAD QUEUE WORKER ────────────────────────────────────────

async function executeHistoricalDownloadJobs() {
  try {
    const job = await prisma.jDDSJob.findFirst({
      where: { status: { in: ["pending", "running"] } },
      orderBy: [
        { priority: "asc" },
        { createdAt: "asc" }
      ]
    });

    if (!job) return;

    console.log(`[jdds-worker] Processing job ${job.id} of type ${job.type} for symbol ID ${job.symbolId}`);

    if (job.status === "pending") {
      await prisma.jDDSJob.update({
        where: { id: job.id },
        data: { status: "running", progress: 10 }
      });
    }

    if (!job.symbolId) {
      throw new Error("Job missing symbolId");
    }

    const symbol = await prisma.assetSymbol.findUnique({
      where: { id: job.symbolId }
    });

    if (!symbol) {
      throw new Error(`Symbol with ID ${job.symbolId} not found`);
    }

    await prisma.assetSymbol.update({
      where: { id: symbol.id },
      data: { dataStatus: "downloading" }
    });

    const timeframe = job.timeframe || "1d";
    const startDate = job.startDate || new Date(Date.now() - 365 * 24 * 60 * 60 * 1000);
    const endDate = job.endDate || new Date();

    const provider = getBestProvider(symbol.assetClass, symbol.symbol, timeframe);
    console.log(`[jdds-worker] Selected provider ${provider.name} for ${symbol.symbol} (${symbol.assetClass})`);

    await prisma.jDDSJob.update({
      where: { id: job.id },
      data: { provider: provider.name, progress: 30 }
    });

    const candles = await provider.fetchCandles(
      symbol.symbol,
      symbol.assetClass,
      timeframe,
      startDate,
      endDate
    );

    if (candles.length === 0) {
      const existingCandlesCount = await prisma.historicalCandle.count({
        where: { symbolId: symbol.id, timeframe }
      });
      if (existingCandlesCount > 0) {
        console.log(`[jdds-worker] Found ${existingCandlesCount} existing cached candles for ${symbol.symbol}.`);
        await prisma.jDDSJob.update({
          where: { id: job.id },
          data: { status: "completed", progress: 100 }
        });
        await prisma.assetSymbol.update({
          where: { id: symbol.id },
          data: { dataStatus: "ready", lastSyncedAt: new Date(), isBacktestEnabled: true }
        });
        return;
      }
      throw new Error(`No candles returned from provider ${provider.name}`);
    }

    console.log(`[jdds-worker] Fetched ${candles.length} candles. Bulk saving...`);
    await prisma.jDDSJob.update({
      where: { id: job.id },
      data: { progress: 60 }
    });

    const batch = candles.map(c => ({
      symbolId: symbol.id,
      timeframe: timeframe,
      timestamp: c.timestamp,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
      volume: c.volume ?? 0,
      source: c.source || provider.name,
      quality: "clean"
    }));

    const chunkSize = 1000;
    for (let i = 0; i < batch.length; i += chunkSize) {
      const chunk = batch.slice(i, i + chunkSize);
      await prisma.historicalCandle.createMany({
        data: chunk,
        skipDuplicates: true
      });
    }

    await prisma.jDDSJob.update({
      where: { id: job.id },
      data: { status: "completed", progress: 100, error: null }
    });

    await prisma.assetSymbol.update({
      where: { id: symbol.id },
      data: {
        dataStatus: "ready",
        lastSyncedAt: new Date(),
        isBacktestEnabled: true
      }
    });

    console.log(`[jdds-worker] Job ${job.id} completed successfully.`);
  } catch (err: any) {
    console.error(`[jdds-worker] Job failed:`, err.message || err);
    try {
      const activeJob = await prisma.jDDSJob.findFirst({
        where: { status: "running" }
      });
      if (activeJob) {
        await prisma.jDDSJob.update({
          where: { id: activeJob.id },
          data: { status: "failed", error: err.message || "Unknown error", progress: 0 }
        });
        if (activeJob.symbolId) {
          await prisma.assetSymbol.update({
            where: { id: activeJob.symbolId },
            data: { dataStatus: "failed" }
          });
        }
      }
    } catch (e) {}
  }
}

// ─── MAIN ENGINE RUNNER ───────────────────────────────────────────────────────


async function main() {
  console.log("╔══════════════════════════════════════════════════════════╗");
  console.log("║   JDdS — Joint Data Delivery Service  (v2 — DYNAMIC)    ║");
  console.log("╠══════════════════════════════════════════════════════════╣");
  console.log("║  All scheduling is user-controlled via DB config.        ║");
  console.log("║  No hardcoded intervals. Run Now supported.              ║");
  console.log("╚══════════════════════════════════════════════════════════╝\n");

  // Load config once synchronously at start
  try {
    const configRow = await prisma.systemConfig.findUnique({
      where: { key: "system_config" }
    });
    const activeModeRow = await prisma.systemConfig.findUnique({
      where: { key: "active_mode" }
    });
    if (configRow) {
      const raw = JSON.parse(configRow.value);
      const migrated = migrateConfig(raw);
      currentConfig = {
        crypto: { ...DEFAULT_CONFIG.crypto, ...migrated.crypto },
        stocks: { ...DEFAULT_CONFIG.stocks, ...migrated.stocks },
        api: { ...DEFAULT_CONFIG.api, ...migrated.api },
        system: { ...DEFAULT_CONFIG.system, ...migrated.system },
      };
    }
    if (activeModeRow) {
      currentConfig.system.mode = activeModeRow.value;
    }
  } catch (err) {
    console.error("[daemon] Initial config load failed. Using defaults.", err);
  }

  console.log(`[daemon] Loaded config — Mode: "${currentConfig.system.mode}", Crypto Universe Interval: ${currentConfig.crypto.universeSyncInterval}s, Price Interval: ${currentConfig.crypto.priceUpdateInterval}s`);

  // Start config reloader (every 3 seconds)
  setTimeout(refreshConfig, 3000);

  // Initialize run tracking
  let lastUniverseRun = 0;
  let lastPriceRun = 0;
  let lastGeckoRun = 0;
  let lastNewsRun = 0;
  let lastMode = "";
  let universeRunning = false;
  let priceRunning = false;
  let geckoRunning = false;
  let newsRunning = false;

  const runEngineCycle = async () => {
    try {
      const mode = currentConfig.system.mode;
      const isPaused = currentConfig.system.globalPause || mode === "suspended";

      // Detect mode change → reset schedules
      if (mode !== lastMode) {
        console.log(`[daemon] Mode changed: "${lastMode}" → "${mode}". Resetting schedules.`);
        lastMode = mode;
        lastUniverseRun = 0;
        lastPriceRun = 0;
        lastNewsRun = 0;
      }

      // ─── RUN NOW SIGNALS (always checked, even when paused/suspended) ─────
      const runNow = await checkRunNowSignals();
      
      if (runNow.universe && !universeRunning) {
        console.log("[daemon] ▶ RUN NOW — Universe sync triggered by user!");
        universeRunning = true;
        lastUniverseRun = Date.now(); // Reset timer so scheduled run doesn't double up
        executeUniverseSync().finally(() => {
          universeRunning = false;
          clearRunNowSignal("run_now_universe");
        });
      }

      if (runNow.prices && !priceRunning) {
        console.log("[daemon] ▶ RUN NOW — Price polling triggered by user!");
        priceRunning = true;
        lastPriceRun = Date.now();
        executePricePolling().finally(() => {
          priceRunning = false;
          clearRunNowSignal("run_now_prices");
        });
      }

      if (runNow.news && !newsRunning) {
        console.log("[daemon] ▶ RUN NOW — News polling triggered by user!");
        newsRunning = true;
        lastNewsRun = Date.now();
        executeNewsPolling().finally(() => {
          newsRunning = false;
          clearRunNowSignal("run_now_news");
        });
      }

      // ─── SCHEDULED OPERATIONS (only when not paused) ─────────────────────
      if (!isPaused) {
        const now = Date.now();

        // Universe Sync (active in: hybrid, universe_only)
        if ((mode === "hybrid" || mode === "universe_only") && !universeRunning) {
          const cryptoUniverseEnabled = currentConfig.crypto.universeEnabled;
          const stocksUniverseEnabled = currentConfig.stocks.universeEnabled;
          
          if (cryptoUniverseEnabled || stocksUniverseEnabled) {
            // Use the smaller of the two intervals
            const intervalSec = Math.min(
              currentConfig.crypto.universeSyncInterval || 3600,
              currentConfig.stocks.universeSyncInterval || 3600
            );
            const intervalMs = intervalSec * 1000;
            
            if (lastUniverseRun === 0 || now - lastUniverseRun >= intervalMs) {
              lastUniverseRun = now;
              universeRunning = true;
              console.log(`[daemon] Scheduled universe sync (interval: ${intervalSec}s, mode: "${mode}")...`);
              executeUniverseSync().finally(() => {
                universeRunning = false;
              });
            }
          }
        }

        // Price Polling (active in: hybrid, price_only)
        if ((mode === "hybrid" || mode === "price_only") && !priceRunning) {
          const cryptoPriceEnabled = currentConfig.crypto.priceEnabled;
          const stocksPriceEnabled = currentConfig.stocks.priceEnabled;
          
          if (cryptoPriceEnabled || stocksPriceEnabled) {
            // Use the smaller of the two intervals
            const intervalSec = Math.min(
              currentConfig.crypto.priceUpdateInterval || 120,
              currentConfig.stocks.priceUpdateInterval || 120
            );
            const intervalMs = intervalSec * 1000;
            
            if (lastPriceRun === 0 || now - lastPriceRun >= intervalMs) {
              lastPriceRun = now;
              priceRunning = true;
              console.log(`[daemon] Scheduled price poll (interval: ${intervalSec}s, mode: "${mode}")...`);
              executePricePolling().finally(() => {
                priceRunning = false;
              });
            }
          }
        }

        // CoinGecko Fundamentals Sync (every 15 minutes)
        if ((mode === "hybrid" || mode === "price_only" || mode === "universe_only") && !geckoRunning) {
          const geckoIntervalMs = 15 * 60 * 1000; // 15 minutes
          if (lastGeckoRun === 0 || now - lastGeckoRun >= geckoIntervalMs) {
            lastGeckoRun = now;
            geckoRunning = true;
            console.log("[daemon] Scheduled CoinGecko fundamental sync...");
            executeGeckoSync().finally(() => {
              geckoRunning = false;
            });
          }
        }

        // Market News Ingestion Poller (every 5 minutes)
        if (!newsRunning) {
          const newsIntervalMs = 5 * 60 * 1000; // 5 minutes
          if (lastNewsRun === 0 || now - lastNewsRun >= newsIntervalMs) {
            lastNewsRun = now;
            newsRunning = true;
            console.log("[daemon] Scheduled market news sync...");
            executeNewsPolling().finally(() => {
              newsRunning = false;
            });
          }
        }
      }

      // ─── HISTORICAL DATA JOBS QUEUE WORKER (JDDS BACKTEST PIPE) ─────────────
      if (mode === "hybrid" || mode === "backtest_only" || mode === "universe_only" || mode === "prices_only") {
        await executeHistoricalDownloadJobs();
      }
    } catch (cycleErr) {
      console.error("[daemon] Engine cycle error:", cycleErr);
    }
    
    // Cycle check every 1 second
    setTimeout(runEngineCycle, 1000);
  };

  // Ingest CoinGecko fundamentals and news immediately on startup to build cache
  executeGeckoSync().catch(err => console.error("[daemon] Startup CoinGecko sync error:", err));
  executeNewsPolling().catch(err => console.error("[daemon] Startup News sync error:", err));

  runEngineCycle();
}

// Run main only if executed directly
if (process.argv[1] && (process.argv[1].endsWith("jdds-daemon.ts") || process.argv[1].endsWith("jdds-daemon.js") || process.argv[1].includes("jdds"))) {
  main();
}
