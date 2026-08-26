import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { fetchYahooBatchQuote } from "@/lib/scraper/fetchers/yfinance";
import { toMarketId, MARKET_CURRENCY as marketCurrencyMap } from "@/lib/markets";

export const dynamic = "force-dynamic";

// Index universe per market (Yahoo tickers). Fall back to simulated data when
// a fetch fails so the dashboard is never empty.
const INDEX_UNIVERSE: Record<string, Array<{ symbol: string; name: string }>> = {
  US: [
    { symbol: "^GSPC", name: "S&P 500" },
    { symbol: "^IXIC", name: "Nasdaq Composite" },
    { symbol: "^DJI", name: "Dow Jones" },
    { symbol: "^RUT", name: "Russell 2000" },
    { symbol: "BTC-USD", name: "Bitcoin" },
    { symbol: "GC=F", name: "Gold" },
  ],
  CRYPTO: [
    { symbol: "BTC-USD", name: "Bitcoin" },
    { symbol: "ETH-USD", name: "Ethereum" },
    { symbol: "SOL-USD", name: "Solana" },
    { symbol: "BNB-USD", name: "Binance Coin" },
    { symbol: "XRP-USD", name: "Ripple" },
    { symbol: "DOGE-USD", name: "Dogecoin" },
  ],
  // Yahoo no longer carries PSX data (^KSE100 / .PSX all return delisted).
  // Empty universe → the TOP STOCKS fallback below serves KSE cards instead.
  PK: [],
  IN: [
    { symbol: "^NSEI", name: "Nifty 50" },
    { symbol: "^BSESN", name: "Sensex" },
    { symbol: "^NSEBANK", name: "Bank Nifty" },
  ],
  CN: [
    { symbol: "000001.SS", name: "Shanghai Composite" },
    { symbol: "399001.SZ", name: "Shenzhen Component" },
    { symbol: "399006.SZ", name: "ChiNext" },
  ],
  TW: [{ symbol: "^TWII", name: "TAIEX Weighted" }],
  HK: [
    { symbol: "^HSI", name: "Hang Seng" },
    { symbol: "^HSCE", name: "Hang Seng China Ent." },
  ],
  JP: [{ symbol: "^N225", name: "Nikkei 225" }],
  KR: [
    { symbol: "^KS11", name: "KOSPI" },
    { symbol: "^KOSDAQ", name: "KOSDAQ" },
  ],
  SG: [{ symbol: "^STI", name: "Straits Times" }],
  MY: [{ symbol: "^KLSE", name: "FTSE Bursa KLCI" }],
  AU: [
    { symbol: "^AXJO", name: "S&P/ASX 200" },
    { symbol: "^AORD", name: "All Ordinaries" },
  ],
  UK: [
    { symbol: "^FTSE", name: "FTSE 100" },
    { symbol: "^FTMC", name: "FTSE Mid 250" },
  ],
  DE: [{ symbol: "^GDAXI", name: "DAX" }],
  FR: [{ symbol: "^FCHI", name: "CAC 40" }],
  NL: [{ symbol: "^AEX", name: "AEX Index" }],
  CA: [{ symbol: "^GSPTSE", name: "S&P/TSX Composite" }],
  BR: [{ symbol: "^BVSP", name: "Ibovespa" }],
  MX: [{ symbol: "^MXX", name: "IPC Mexico" }],
  SA: [{ symbol: "^TASI.SR", name: "Tadawul All Share" }],
  AE: [{ symbol: "^DFMGI", name: "DFM General" }],
  ZA: [{ symbol: "^JALSH", name: "JSE All Share" }],
  EG: [{ symbol: "^EGX30", name: "EGX 30" }],
  NG: [{ symbol: "^NGXALLSH", name: "NGX All Share" }],
  RU: [{ symbol: "^IMOEX.ME", name: "MOEX Russia" }],
  TR: [{ symbol: "^XU100", name: "BIST 100" }],
  ID: [{ symbol: "^JKSE", name: "Jakarta Composite" }],
  TH: [{ symbol: "^SET.BK", name: "SET Index" }],
  VN: [{ symbol: "^VNINDEX", name: "VN Index" }],
};

// Currency that belongs to each market's instruments (shared with /api/quote).
const MARKET_CURRENCY = marketCurrencyMap;

const SIMULATED: Record<string, { indices: { name: string; symbol: string; price: number; change: number; changePercent: number; sparkline: number[] }[]; sectors: { name: string; change: number }[]; shifters: { gainers: { symbol: string; name: string; price: number; changePercent: number }[]; losers: { symbol: string; name: string; price: number; changePercent: number }[] } }> = {
  US: {
    indices: [
      { name: "S&P 500", symbol: "^GSPC", price: 5304.72, change: 42.1, changePercent: 0.8, sparkline: [5260, 5280, 5275, 5290, 5304.72] },
      { name: "Nasdaq Composite", symbol: "^IXIC", price: 16920.72, change: 182.2, changePercent: 1.09, sparkline: [16700, 16820, 16780, 16850, 16920.72] },
      { name: "Dow Jones", symbol: "^DJI", price: 39069.59, change: -88.1, changePercent: -0.22, sparkline: [39200, 39150, 39180, 39020, 39069.59] },
      { name: "Russell 2000", symbol: "^RUT", price: 2068.32, change: 11.45, changePercent: 0.56, sparkline: [2050, 2062, 2055, 2060, 2068.32] },
      { name: "Bitcoin", symbol: "BTC-USD", price: 67840, change: 1420, changePercent: 2.14, sparkline: [66200, 66800, 67200, 67000, 67840] },
      { name: "Gold", symbol: "GC=F", price: 2348.8, change: -12.4, changePercent: -0.52, sparkline: [2365, 2360, 2355, 2358, 2348.8] },
    ],
    sectors: [
      { name: "Information Technology", change: 1.84 },
      { name: "Communication Services", change: 1.25 },
      { name: "Health Care", change: 0.88 },
      { name: "Financials", change: 0.42 },
      { name: "Materials", change: 0.15 },
      { name: "Energy", change: -0.12 },
      { name: "Industrials", change: -0.34 },
      { name: "Consumer Staples", change: -0.45 },
      { name: "Real Estate", change: -0.72 },
      { name: "Utilities", change: -0.85 },
      { name: "Consumer Discretionary", change: -1.12 },
    ],
    shifters: {
      gainers: [
        { symbol: "NVDA", name: "NVIDIA Corp.", price: 1096.5, changePercent: 4.6 },
        { symbol: "LLY", name: "Eli Lilly & Co.", price: 818.5, changePercent: 2.1 },
        { symbol: "NFLX", name: "Netflix Inc.", price: 645.2, changePercent: 1.96 },
      ],
      losers: [
        { symbol: "TSLA", name: "Tesla Inc.", price: 178.5, changePercent: -2.35 },
        { symbol: "META", name: "Meta Platforms", price: 475.4, changePercent: -1.7 },
        { symbol: "UNH", name: "UnitedHealth Group", price: 494.6, changePercent: -1.3 },
      ],
    },
  },
  CRYPTO: {
    indices: [
      { name: "Bitcoin", symbol: "BTC-USD", price: 67840, change: 1420, changePercent: 2.14, sparkline: [66200, 66800, 67200, 67000, 67840] },
      { name: "Ethereum", symbol: "ETH-USD", price: 3500.2, change: 82.5, changePercent: 2.41, sparkline: [3400, 3420, 3450, 3480, 3500.2] },
      { name: "Solana", symbol: "SOL-USD", price: 168.4, change: 6.2, changePercent: 3.82, sparkline: [160, 162, 165, 164, 168.4] },
      { name: "Binance Coin", symbol: "BNB-USD", price: 585.5, change: 12.1, changePercent: 2.11, sparkline: [570, 575, 580, 578, 585.5] },
      { name: "Ripple", symbol: "XRP-USD", price: 0.52, change: 0.015, changePercent: 2.97, sparkline: [0.5, 0.51, 0.5, 0.51, 0.52] },
      { name: "Dogecoin", symbol: "DOGE-USD", price: 0.154, change: 0.008, changePercent: 5.48, sparkline: [0.142, 0.145, 0.148, 0.15, 0.154] },
    ],
    sectors: [
      { name: "Layer 1", change: 2.85 },
      { name: "DeFi", change: 1.45 },
      { name: "Stablecoins", change: 0 },
      { name: "Meme Coins", change: 8.5 },
      { name: "Exchange Tokens", change: -1.2 },
      { name: "Layer 2", change: 1.8 },
    ],
    shifters: {
      gainers: [
        { symbol: "DOGE", name: "Dogecoin", price: 0.154, changePercent: 5.48 },
        { symbol: "SOL", name: "Solana", price: 168.4, changePercent: 3.82 },
        { symbol: "ETH", name: "Ethereum", price: 3500.2, changePercent: 2.41 },
      ],
      losers: [
        { symbol: "BNB", name: "Binance Coin", price: 585.5, changePercent: -1.2 },
        { symbol: "XRP", name: "Ripple", price: 0.52, changePercent: -0.45 },
        { symbol: "BTC", name: "Bitcoin", price: 67840, changePercent: -0.15 },
      ],
    },
  },
};

function simulatedFor(market: string) {
  if (market === "CRYPTO") return SIMULATED.CRYPTO;
  return SIMULATED.US;
}

function sparkline(price: number): number[] {
  if (!price || price <= 0) return [0, 0, 0, 0, 0];
  const start = price * 0.995;
  const pts: number[] = [];
  for (let i = 1; i <= 5; i++) {
    pts.push(+(start + ((price - start) * i) / 5).toFixed(2));
  }
  return pts;
}

// GET /api/indices?market=US — live index quotes + sector performance + market
// shifters for the given market. Quotes come from Yahoo Finance and are cached
// in the IndexQuote table (JDDS) so repeated page loads never hit the network.
//
// SWR memory cache: a live fetch spawns Python + hits Yahoo (7-30s), which on
// every tab/market switch made the UI feel frozen. Serve cached payloads
// instantly; rebuild in the background when older than 2 minutes.
const INDICES_CACHE_TTL_MS = 2 * 60 * 1000;
const indicesCache = new Map<string, { t: number; data: unknown }>();
const indicesRebuilding = new Set<string>();

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const market = toMarketId((searchParams.get("market") || "US").toUpperCase());

  const cachedEntry = indicesCache.get(market);
  if (cachedEntry) {
    if (Date.now() - cachedEntry.t < INDICES_CACHE_TTL_MS) {
      return NextResponse.json(cachedEntry.data);
    }
    if (!indicesRebuilding.has(market)) {
      indicesRebuilding.add(market);
      buildIndicesPayload(market)
        .then((data) => indicesCache.set(market, { t: Date.now(), data }))
        .catch((err) => console.error("[api/indices] background rebuild error:", err))
        .finally(() => indicesRebuilding.delete(market));
    }
    return NextResponse.json(cachedEntry.data);
  }

  try {
    const data = await buildIndicesPayload(market);
    indicesCache.set(market, { t: Date.now(), data });
    return NextResponse.json(data);
  } catch (err) {
    console.error("[api/indices] GET error:", err);
    const fallback = simulatedFor(market);
    return NextResponse.json({
      market,
      indices: fallback.indices,
      sectors: fallback.sectors,
      shifters: fallback.shifters,
      live: 0,
      total: (INDEX_UNIVERSE[market] || INDEX_UNIVERSE.US).length,
      source: "fallback",
      simulated: true,
    });
  }
}

async function buildIndicesPayload(market: string) {
  const universe = INDEX_UNIVERSE[market] || INDEX_UNIVERSE.US;

  try {
    // 1) Live quotes from the yfinance bridge (one batched call over one
    //    shared session), cached in IndexQuote.
    const cached = await prisma.indexQuote.findMany({
      where: { marketId: market },
      select: { symbol: true, name: true, price: true, change: true, changePct: true },
    });
    const cachedBySymbol = new Map(cached.map((c) => [c.symbol, c]));

    const results = await fetchYahooBatchQuote(
      universe.map((item) => item.symbol),
      "US"
    );
    for (let i = 0; i < results.length; i++) {
      const result = results[i];
      const item = universe[i];
      if (result.status !== "ok" || !result.quote || !item) continue;

      const prevClose = result.quote.changePct !== 0
        ? result.quote.price / (1 + result.quote.changePct / 100)
        : result.quote.price;
      const change = +(result.quote.price - prevClose).toFixed(2);
      await prisma.indexQuote.upsert({
        where: { marketId_symbol: { marketId: market, symbol: item.symbol } },
        update: { price: result.quote.price, change, changePct: result.quote.changePct },
        create: { marketId: market, symbol: item.symbol, name: item.name, price: result.quote.price, change, changePct: result.quote.changePct },
      });
      cachedBySymbol.set(item.symbol, { symbol: item.symbol, name: item.name, price: result.quote.price, change, changePct: result.quote.changePct });
    }

    let live = 0;
    const marketCurrency = MARKET_CURRENCY[market] || "$";
    const indices = universe
      .map((item) => {
        const c = cachedBySymbol.get(item.symbol);
        if (c) live++;
        return {
          name: c?.name || item.name,
          symbol: c?.symbol || item.symbol,
          price: c?.price ?? 0,
          change: c?.change ?? 0,
          changePercent: c?.changePct ?? 0,
          sparkline: sparkline(c?.price ?? 0),
          currency: marketCurrency,
        };
      })
      // Drop indices with no live/cached quote so a country never shows
      // broken zero-price cards — the grid simply renders fewer cards.
      .filter((idx) => idx.price > 0);

    // Some markets have no index coverage on Yahoo (e.g. PSX). When nothing
    // resolves, fall back to the country's TOP STOCKS from JDDS as the ticker
    // cards so every country always shows its own leading instruments.
    if (indices.length === 0 && market !== "US") {
      const topAssets = await prisma.asset.findMany({
        where: { marketId: market, isActive: true, price: { isNot: null } },
        select: { symbol: true, name: true, price: { select: { price: true, changePct: true } } },
        orderBy: [{ price: { marketCap: "desc" } }, { price: { volume: "desc" } }],
        take: 6,
      });
      for (const a of topAssets) {
        if (!a.price || a.price.price <= 0) continue;
        indices.push({
          name: a.name,
          symbol: a.symbol,
          price: a.price.price,
          change: +(a.price.price - a.price.price / (1 + a.price.changePct / 100)).toFixed(2),
          changePercent: a.price.changePct,
          sparkline: sparkline(a.price.price),
          currency: marketCurrency,
        });
      }
    }

    // 2) Sector performance from JDDS (average % change per sector).
    let sectors: { name: string; change: number }[] = [];
    if (market !== "CRYPTO") {
      const rows = await prisma.asset.findMany({
        where: { marketId: market, isActive: true, sector: { not: null } },
        select: { sector: true, price: { select: { changePct: true } } },
        take: 2000,
      });
      const bySector = new Map<string, { sum: number; count: number }>();
      for (const r of rows) {
        if (!r.sector || !r.price) continue;
        const cur = bySector.get(r.sector) || { sum: 0, count: 0 };
        cur.sum += r.price.changePct;
        cur.count += 1;
        bySector.set(r.sector, cur);
      }
      sectors = [...bySector.entries()]
        .filter(([, v]) => v.count >= 5)
        .map(([name, v]) => ({ name, change: +(v.sum / v.count).toFixed(2) }))
        .sort((a, b) => b.change - a.change)
        .slice(0, 11);
    } else {
      const rows = await prisma.asset.findMany({
        where: { marketId: "CRYPTO", isActive: true, sector: { not: null } },
        select: { sector: true, price: { select: { changePct: true } } },
        take: 2000,
      });
      const bySector = new Map<string, { sum: number; count: number }>();
      for (const r of rows) {
        if (!r.sector || !r.price) continue;
        const cur = bySector.get(r.sector) || { sum: 0, count: 0 };
        cur.sum += r.price.changePct;
        cur.count += 1;
        bySector.set(r.sector, cur);
      }
      sectors = [...bySector.entries()]
        .filter(([, v]) => v.count >= 3)
        .map(([name, v]) => ({ name, change: +(v.sum / v.count).toFixed(2) }))
        .sort((a, b) => b.change - a.change)
        .slice(0, 6);
    }
    if (sectors.length === 0) sectors = simulatedFor(market).sectors;

    // 3) Shifters: top gainers/losers from the priced universe.
    const priced = await prisma.asset.findMany({
      where: { marketId: market, isActive: true, price: { isNot: null } },
      select: { symbol: true, name: true, price: { select: { price: true, changePct: true } } },
      orderBy: { price: { changePct: "desc" } },
      take: 6,
    });
    const losers = await prisma.asset.findMany({
      where: { marketId: market, isActive: true, price: { isNot: null } },
      select: { symbol: true, name: true, price: { select: { price: true, changePct: true } } },
      orderBy: { price: { changePct: "asc" } },
      take: 6,
    });
    const toShifter = (a: (typeof priced)[number]) => ({
      symbol: a.symbol,
      name: a.name,
      price: a.price?.price ?? 0,
      changePercent: a.price?.changePct ?? 0,
    });
    const shifters = {
      gainers: priced.map(toShifter).filter((s) => s.changePercent > 0).slice(0, 3),
      losers: losers.map(toShifter).filter((s) => s.changePercent < 0).slice(0, 3),
    };
    if (shifters.gainers.length === 0 || shifters.losers.length === 0) {
      const fallback = simulatedFor(market).shifters;
      shifters.gainers = shifters.gainers.length ? shifters.gainers : fallback.gainers;
      shifters.losers = shifters.losers.length ? shifters.losers : fallback.losers;
    }

    return {
      market,
      indices,
      sectors,
      shifters,
      live,
      total: universe.length,
      source: live > 0 ? "yfinance" : "cache",
    };
  } catch (err) {
    console.error("[api/indices] Error:", err);
    const fallback = simulatedFor(market);
    return {
      market,
      indices: fallback.indices,
      sectors: fallback.sectors,
      shifters: fallback.shifters,
      live: 0,
      total: universe.length,
      source: "fallback",
      simulated: true,
    };
  }
}
