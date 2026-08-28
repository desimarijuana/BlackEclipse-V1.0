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
      { name: "S&P 500", symbol: "^GSPC", price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
      { name: "Nasdaq Composite", symbol: "^IXIC", price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
      { name: "Dow Jones", symbol: "^DJI", price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
      { name: "Russell 2000", symbol: "^RUT", price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
      { name: "Bitcoin", symbol: "BTC-USD", price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
      { name: "Gold", symbol: "GC=F", price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
    ],
    sectors: [
      { name: "Information Technology", change: 0 },
      { name: "Communication Services", change: 0 },
      { name: "Health Care", change: 0 },
      { name: "Financials", change: 0 },
      { name: "Materials", change: 0 },
      { name: "Energy", change: 0 },
      { name: "Industrials", change: 0 },
      { name: "Consumer Staples", change: 0 },
      { name: "Real Estate", change: 0 },
      { name: "Utilities", change: 0 },
      { name: "Consumer Discretionary", change: 0 },
    ],
    shifters: {
      gainers: [
        { symbol: "NVDA", name: "NVIDIA Corp.", price: 0, changePercent: 0 },
        { symbol: "LLY", name: "Eli Lilly & Co.", price: 0, changePercent: 0 },
        { symbol: "NFLX", name: "Netflix Inc.", price: 0, changePercent: 0 },
      ],
      losers: [
        { symbol: "TSLA", name: "Tesla Inc.", price: 0, changePercent: 0 },
        { symbol: "META", name: "Meta Platforms", price: 0, changePercent: 0 },
        { symbol: "UNH", name: "UnitedHealth Group", price: 0, changePercent: 0 },
      ],
    },
  },
  CRYPTO: {
    indices: [
      { name: "Bitcoin", symbol: "BTC-USD", price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
      { name: "Ethereum", symbol: "ETH-USD", price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
      { name: "Solana", symbol: "SOL-USD", price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
      { name: "Binance Coin", symbol: "BNB-USD", price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
      { name: "Ripple", symbol: "XRP-USD", price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
      { name: "Dogecoin", symbol: "DOGE-USD", price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
    ],
    sectors: [
      { name: "Layer 1", change: 0 },
      { name: "DeFi", change: 0 },
      { name: "Stablecoins", change: 0 },
      { name: "Meme Coins", change: 0 },
      { name: "Exchange Tokens", change: 0 },
      { name: "Layer 2", change: 0 },
    ],
    shifters: {
      gainers: [
        { symbol: "DOGE", name: "Dogecoin", price: 0, changePercent: 0 },
        { symbol: "SOL", name: "Solana", price: 0, changePercent: 0 },
        { symbol: "ETH", name: "Ethereum", price: 0, changePercent: 0 },
      ],
      losers: [
        { symbol: "BNB", name: "Binance Coin", price: 0, changePercent: 0 },
        { symbol: "XRP", name: "Ripple", price: 0, changePercent: 0 },
        { symbol: "BTC", name: "Bitcoin", price: 0, changePercent: 0 },
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

  // Cold start: if the IndexQuote table already has quotes for this market
  // (persisted by a previous build), serve them INSTANTLY and refresh from
  // Yahoo in the background. Never make the browser wait 15-40s on the
  // Python bridge — that's what caused the "Failed to fetch" aborts.
  try {
    const persisted = await prisma.indexQuote.findMany({
      where: { marketId: market },
      select: { symbol: true, name: true, price: true, change: true, changePct: true },
    });
    const usable = persisted.filter((q) => q.price > 0);
    if (usable.length > 0) {
      const data = buildPayloadFromCache(market, usable);
      indicesCache.set(market, { t: Date.now(), data });
      if (!indicesRebuilding.has(market)) {
        indicesRebuilding.add(market);
        buildIndicesPayload(market)
          .then((fresh) => indicesCache.set(market, { t: Date.now(), data: fresh }))
          .catch((err) => console.error("[api/indices] background rebuild error:", err))
          .finally(() => indicesRebuilding.delete(market));
      }
      return NextResponse.json(data);
    }
  } catch { /* DB miss — fall through to a live build */ }

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

// Assemble the same payload shape from persisted IndexQuote rows only (no
// network). Used for the instant cold-start serve above.
function buildPayloadFromCache(
  market: string,
  rows: Array<{ symbol: string; name: string; price: number; change: number; changePct: number }>
) {
  const marketCurrency = MARKET_CURRENCY[market] || "$";
  const indices = rows
    .filter((r) => r.price > 0)
    .map((r) => ({
      name: r.name,
      symbol: r.symbol,
      price: r.price,
      change: r.change,
      changePercent: r.changePct,
      sparkline: sparkline(r.price),
      currency: marketCurrency,
    }));
  return {
    market,
    indices,
    sectors: [] as { name: string; change: number }[],
    shifters: { gainers: [], losers: [] },
    live: indices.length,
    total: rows.length,
    source: "cache",
  };
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
