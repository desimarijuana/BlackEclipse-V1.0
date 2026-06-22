import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { dataCache, cacheKey } from "@/data-layer/cache";

export const dynamic = "force-dynamic";

interface IndexCard {
  name: string;
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
  sparkline: number[];
}

interface SectorPerformance {
  name: string;
  change: number;
}

interface ShifterItem {
  symbol: string;
  name: string;
  price: number;
  changePercent: number;
}

const COUNTRY_DASHBOARDS: Record<
  string,
  {
    indices: IndexCard[];
    sectors: SectorPerformance[];
  }
> = {
  US: {
    indices: [
      { name: "S&P 500", symbol: "SPX", price: 5304.72, change: 42.1, changePercent: 0.8, sparkline: [5260, 5280, 5275, 5290, 5304.72] },
      { name: "Nasdaq Composite", symbol: "IXIC", price: 16920.72, change: 182.2, changePercent: 1.09, sparkline: [16700, 16820, 16780, 16850, 16920.72] },
      { name: "Dow Jones", symbol: "DJI", price: 39069.59, change: -48.2, changePercent: -0.12, sparkline: [39100, 39050, 39080, 39120, 39069.59] },
      { name: "Russell 2000", symbol: "RUT", price: 2060.3, change: 14.5, changePercent: 0.71, sparkline: [2045, 2050, 2055, 2058, 2060.3] },
      { name: "Bitcoin", symbol: "BTC", price: 67840.0, change: 1420.0, changePercent: 2.14, sparkline: [66200, 66800, 67200, 67000, 67840] },
      { name: "Gold", symbol: "GC=F", price: 2348.8, change: -12.4, changePercent: -0.52, sparkline: [2365, 2360, 2355, 2358, 2348.8] },
    ],
    sectors: [
      { name: "Technology", change: 1.85 },
      { name: "Healthcare", change: 0.92 },
      { name: "Financials", change: 0.45 },
      { name: "Consumer Discretionary", change: -0.32 },
      { name: "Energy", change: -0.78 },
    ],
  },
  CRYPTO: {
    indices: [
      { name: "Bitcoin", symbol: "BTC", price: 67840.0, change: 1420.0, changePercent: 2.14, sparkline: [66200, 66800, 67200, 67000, 67840] },
      { name: "Ethereum", symbol: "ETH", price: 3500.2, change: 82.5, changePercent: 2.41, sparkline: [3400, 3420, 3450, 3480, 3500.2] },
      { name: "Solana", symbol: "SOL", price: 168.4, change: 6.2, changePercent: 3.82, sparkline: [160, 162, 165, 164, 168.4] },
      { name: "Binance Coin", symbol: "BNB", price: 585.5, change: 12.1, changePercent: 2.11, sparkline: [570, 575, 580, 578, 585.5] },
    ],
    sectors: [
      { name: "Layer 1", change: 2.85 },
      { name: "DeFi", change: 1.45 },
      { name: "Stablecoins", change: 0.0 },
      { name: "Meme Coins", change: 8.5 },
      { name: "Exchange Tokens", change: -1.2 },
    ],
  },
};

const CORE_STOCKS: Record<string, { sector: string; industry: string }> = {
  AAPL: { sector: "Technology", industry: "Consumer Electronics" },
  MSFT: { sector: "Technology", industry: "Software-Infrastructure" },
  NVDA: { sector: "Technology", industry: "Semiconductors" },
  AMZN: { sector: "Consumer Discretionary", industry: "Internet Retail" },
  GOOGL: { sector: "Technology", industry: "Internet Content" },
  META: { sector: "Technology", industry: "Internet Content" },
  TSLA: { sector: "Consumer Discretionary", industry: "Auto Manufacturers" },
  LLY: { sector: "Healthcare", industry: "Drug Manufacturers" },
  V: { sector: "Financials", industry: "Credit Services" },
  JPM: { sector: "Financials", industry: "Diversified Banks" },
  UNH: { sector: "Healthcare", industry: "Healthcare Plans" },
  AVGO: { sector: "Technology", industry: "Semiconductors" },
  XOM: { sector: "Energy", industry: "Oil & Gas" },
  WMT: { sector: "Consumer Discretionary", industry: "Discount Stores" },
  PG: { sector: "Consumer Discretionary", industry: "Household Products" },
  JNJ: { sector: "Healthcare", industry: "Drug Manufacturers" },
  MA: { sector: "Financials", industry: "Credit Services" },
  HD: { sector: "Consumer Discretionary", industry: "Home Improvement Retail" },
  MRK: { sector: "Healthcare", industry: "Drug Manufacturers" },
  COST: { sector: "Consumer Discretionary", industry: "Discount Stores" },
  ABBV: { sector: "Healthcare", industry: "Drug Manufacturers" },
  AMD: { sector: "Technology", industry: "Semiconductors" },
  CRM: { sector: "Technology", industry: "Software-Application" },
  NFLX: { sector: "Consumer Discretionary", industry: "Entertainment" },
  ADBE: { sector: "Technology", industry: "Software-Infrastructure" },
  CVX: { sector: "Energy", industry: "Oil & Gas" },
  BAC: { sector: "Financials", industry: "Diversified Banks" },
  PEP: { sector: "Consumer Discretionary", industry: "Beverages" },
  KO: { sector: "Consumer Discretionary", industry: "Beverages" },
  TMO: { sector: "Healthcare", industry: "Diagnostics & Research" },
  WFC: { sector: "Financials", industry: "Diversified Banks" },
  CSCO: { sector: "Technology", industry: "Communication Equipment" },
  QCOM: { sector: "Technology", industry: "Semiconductors" },
  MCD: { sector: "Consumer Discretionary", industry: "Restaurants" },
  GE: { sector: "Industrials", industry: "Industrial Machinery" },
  INTC: { sector: "Technology", industry: "Semiconductors" },
  CAT: { sector: "Industrials", industry: "Construction Machinery" },
  DIS: { sector: "Consumer Discretionary", industry: "Entertainment" },
  DHR: { sector: "Healthcare", industry: "Diagnostics & Research" },
  VZ: { sector: "Technology", industry: "Telecom Services" },
  SPX: { sector: "Indices", industry: "S&P 500 Index" },
  IXIC: { sector: "Indices", industry: "Nasdaq Composite Index" },
  DJI: { sector: "Indices", industry: "Dow Jones Industrial Average" },
  RUT: { sector: "Indices", industry: "Russell 2000 Index" },
  "GC=F": { sector: "Commodities", industry: "Gold Futures" }
};

const CORE_CRYPTO_SECTORS: Record<string, string> = {
  BTC: "Layer 1", ETH: "Layer 1", BNB: "Exchange Tokens", SOL: "Layer 1",
  XRP: "Payment", USDC: "Stablecoins", DOGE: "Meme Coins", ADA: "Layer 1",
  TRX: "Layer 1", AVAX: "Layer 1", TON: "Layer 1", LINK: "DeFi",
  SHIB: "Meme Coins", DOT: "Layer 1", BCH: "Payment", NEAR: "Layer 1",
  LTC: "Payment", UNI: "DeFi", SUI: "Layer 1", APT: "Layer 1"
};

function resolveCountryCode(country: string): string {
  const map: Record<string, string> = {
    USA: "US",
    All: "US",
    Crypto: "CRYPTO",
    CRYPTO: "CRYPTO",
  };
  return map[country] || country;
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const rawCountry = searchParams.get("country") || "US";
  const country = resolveCountryCode(rawCountry);
  const page = Math.max(1, parseInt(searchParams.get("page") || "1", 10));
  const maxLimit = country === "CRYPTO" ? 500 : 100;
  const limit = Math.min(maxLimit, Math.max(1, parseInt(searchParams.get("limit") || "20", 10)));
  const search = searchParams.get("search")?.trim() || "";
  const sectorFilter = searchParams.get("sector")?.trim() || "";
  const sort = searchParams.get("sort") || "symbol";
  const order = searchParams.get("order") === "desc" ? "desc" : "asc";
  const symbols = searchParams.get("symbols")?.trim() || "";

  try {
    const ck = cacheKey("stocks-v3", country, String(page), String(limit), search, sectorFilter, sort, order, symbols);
    let cached = dataCache.get<{ stocks: unknown[]; total: number; source: string }>(ck);

    if (!cached) {
      let transformed: unknown[] = [];
      let total = 0;
      let source = "live";
      const now = new Date();

      if (country === "CRYPTO") {
        // Query Crypto Universe
        const symbolsList = symbols ? symbols.split(",").map(s => s.trim().toUpperCase()).filter(Boolean) : [];
        const where: any = {};
        if (symbolsList.length > 0) {
          where.symbol = { in: symbolsList };
        } else if (search) {
          where.OR = [
            { symbol: { contains: search.toUpperCase(), mode: "insensitive" } }
          ];
        }

        const [assets, count] = await Promise.all([
          prisma.cryptoAsset.findMany({
            where,
            include: { price: true, markets: true },
            orderBy: { symbol: order },
            ...(symbolsList.length > 0 ? {} : { skip: (page - 1) * limit, take: limit })
          }),
          prisma.cryptoAsset.count({ where })
        ]);

        total = count;

        const mockUsed = assets.some(a => !a.price || a.price.price === 0);
        const anyStale = assets.some(a => a.price && (now.getTime() - new Date(a.price.lastUpdated).getTime() > 45 * 1000));
        if (mockUsed || anyStale || assets.length === 0) {
          source = "fallback";
        }

        const cgMetricsRows = await prisma.systemConfig.findMany({
          where: { key: { startsWith: "cg_metrics_" } }
        });
        const cgMetricsMap = new Map(
          cgMetricsRows.map(row => [row.key.replace("cg_metrics_", ""), JSON.parse(row.value)])
        );

        transformed = assets.map((asset) => {
          let price = asset.price?.price ?? 0;
          let changePercent = asset.price?.change24h ?? 0;
          let vol = asset.price?.volume ?? 0;
          const rawSector = CORE_CRYPTO_SECTORS[asset.symbol] || "DeFi";
          const sector = rawSector === "Payment" ? "Layer 1" : rawSector;

          const metrics = cgMetricsMap.get(asset.symbol);

          let marketCapStr = "N/A";
          let totalVolumeStr = formatVolume(vol);
          
          if (metrics) {
            if (metrics.marketCap) marketCapStr = formatMarketCap(metrics.marketCap);
            if (metrics.volume24h) totalVolumeStr = formatVolume(metrics.volume24h);
          } else {
            marketCapStr = formatMarketCap(estimateCryptoMarketCap(asset.symbol, price));
          }

          if (price === 0) {
            let hash = 0;
            for (let c = 0; c < asset.symbol.length; c++) {
              hash = asset.symbol.charCodeAt(c) + ((hash << 5) - hash);
            }
            price = Math.abs(hash % 250) + 15.5; // stable price
            changePercent = (hash % 100) / 20; // stable change
            vol = Math.abs(hash % 90000) + 10000;
          }

          return {
            symbol: asset.symbol,
            name: asset.symbol,
            sector, // Layer 1, Layer 2, DeFi, Stablecoins, Meme Coins
            industry: "Crypto",
            country: "CRYPTO",
            price: price,
            changePercent: parseFloat(changePercent.toFixed(2)),
            volume: totalVolumeStr,
            marketCap: marketCapStr,
            peRatio: "N/A",
            dividendYield: "N/A",
            index: "Crypto",
            recommendation: "Hold",
            exchange: "BINANCE",
            circulatingSupply: metrics?.circulatingSupply ? metrics.circulatingSupply.toLocaleString() : "N/A",
            totalSupply: metrics?.totalSupply ? metrics.totalSupply.toLocaleString() : "N/A",
            maxSupply: metrics?.maxSupply ? metrics.maxSupply.toLocaleString() : "N/A",
            ath: metrics?.ath ? `$${metrics.ath.toFixed(2)}` : "N/A",
            atl: metrics?.atl ? `$${metrics.atl.toFixed(2)}` : "N/A",
            rank: metrics?.rank || 9999,
            athChangePercent: metrics?.athChangePercent || 0,
            atlChangePercent: metrics?.atlChangePercent || 0,
            athDate: metrics?.athDate || "",
            atlDate: metrics?.atlDate || "",
            marketCapRaw: metrics?.marketCap || 0,
            volumeRaw: metrics?.volume24h || vol || 0,
            circulatingSupplyRaw: metrics?.circulatingSupply || 0,
            maxSupplyRaw: metrics?.maxSupply || 0
          };
        });
      } else {
        // Query Stock Universe
        const where: { OR?: Array<{ symbol?: { contains: string; mode: "insensitive" }; name?: { contains: string; mode: "insensitive" } }> } = {};
        if (search) {
          where.OR = [
            { symbol: { contains: search.toUpperCase(), mode: "insensitive" } },
            { name: { contains: search, mode: "insensitive" } }
          ];
        }

        const [assets, count] = await Promise.all([
          prisma.stockAsset.findMany({
            where,
            include: { price: true },
            orderBy: { symbol: order },
            skip: (page - 1) * limit,
            take: limit
          }),
          prisma.stockAsset.count({ where })
        ]);

        total = count;

        const mockUsed = assets.some(a => !a.price || a.price.price === 0);
        const anyStale = assets.some(a => a.price && (now.getTime() - new Date(a.price.lastUpdated).getTime() > 45 * 1000));
        if (mockUsed || anyStale || assets.length === 0) {
          source = "fallback";
        }
        
        let filteredAssets = assets;
        if (sectorFilter) {
          filteredAssets = assets.filter(asset => {
            const profile = CORE_STOCKS[asset.symbol];
            return profile?.sector.toLowerCase().includes(sectorFilter.toLowerCase());
          });
          total = filteredAssets.length;
        }

        transformed = filteredAssets.map((asset) => {
          let price = asset.price?.price ?? 0;
          let changePercent = asset.price?.changePercent ?? 0;
          const profile = CORE_STOCKS[asset.symbol] || { sector: "US Stocks", industry: "US Stocks" };

          if (price === 0) {
            let hash = 0;
            for (let c = 0; c < asset.symbol.length; c++) {
              hash = asset.symbol.charCodeAt(c) + ((hash << 5) - hash);
            }
            price = Math.abs(hash % 300) + 10.5; // stable price
            changePercent = (hash % 100) / 20; // stable change
          }

          const sectorCategory = "Stocks";
          const industryName = profile.sector === "US Stocks" ? "US Stocks" : profile.sector;

          return {
            symbol: asset.symbol,
            name: asset.name,
            sector: sectorCategory, // Category "Stocks"
            industry: industryName,  // Industry "Technology", "Healthcare", etc.
            country: "US",    // Subcategory "US"
            price: parseFloat(price.toFixed(2)),
            changePercent: parseFloat(changePercent.toFixed(2)),
            volume: "N/A",
            marketCap: asset.price?.marketCap ? formatMarketCap(asset.price.marketCap) : "N/A",
            peRatio: "Populating...",
            dividendYield: "Populating...",
            index: "S&P 500",
            recommendation: "Hold",
            exchange: "US Markets"
          };
        });
      }

      cached = { stocks: transformed, total, source };
      dataCache.set(ck, cached, 10); // Super short cache for live pricing updates
    }

    // ─── Dashboard indices ──────────────────────────────────────
    const dashboard = COUNTRY_DASHBOARDS[country] || COUNTRY_DASHBOARDS.US;
    const indices = JSON.parse(JSON.stringify(dashboard.indices)) as IndexCard[];

    // Hydrate index prices from db
    try {
      if (country === "CRYPTO") {
        const dbPrices = await prisma.cryptoAsset.findMany({
          where: { symbol: { in: indices.map(idx => idx.symbol) } },
          include: { price: true }
        });
        for (const idx of indices) {
          const matched = dbPrices.find(p => p.symbol === idx.symbol);
          if (matched && matched.price) {
            idx.price = matched.price.price;
            idx.changePercent = matched.price.change24h;
            idx.change = parseFloat((matched.price.price * (matched.price.change24h / 100)).toFixed(2));
          }
        }
      } else {
        const dbPrices = await prisma.stockAsset.findMany({
          where: { symbol: { in: indices.map(idx => idx.symbol) } },
          include: { price: true }
        });
        for (const idx of indices) {
          const matched = dbPrices.find(p => p.symbol === idx.symbol);
          if (matched && matched.price) {
            idx.price = matched.price.price;
            idx.changePercent = matched.price.changePercent;
            idx.change = parseFloat((matched.price.price * (matched.price.changePercent / 100)).toFixed(2));
          }
        }
      }
    } catch {
      // Ignore card hydration errors, fallback to template
    }

    // ─── Shifters & Sectors ──────────────────────────────────────
    const shifters = await getMarketShifters(country);
    const sectors = await getSectorReturns(country);

    return NextResponse.json({
      stocks: cached.stocks,
      indices: indices,
      sectors: sectors.length > 0 ? sectors : dashboard.sectors,
      shifters,
      source: cached.source,
      lastUpdated: new Date().toISOString(),
      pagination: {
        total: cached.total,
        page,
        limit,
        totalPages: Math.ceil(cached.total / limit),
      },
    });
  } catch (err) {
    console.error("[api/stocks] Error:", err);
    return NextResponse.json(
      {
        stocks: [],
        indices: [],
        sectors: [],
        shifters: { gainers: [], losers: [] },
        pagination: { total: 0, page, limit, totalPages: 0 },
        error: "Failed to fetch stocks",
      },
      { status: 500 }
    );
  }
}

// ─── Helpers ──────────────────────────────────────────────────────────

function formatVolume(vol: number): string {
  if (vol >= 1_000_000_000) return `${(vol / 1_000_000_000).toFixed(1)}B`;
  if (vol >= 1_000_000) return `${(vol / 1_000_000).toFixed(1)}M`;
  if (vol >= 1_000) return `${(vol / 1_000).toFixed(1)}K`;
  return String(vol.toFixed(0));
}

function formatMarketCap(cap: number): string {
  if (cap >= 1_000_000_000_000) return `${(cap / 1_000_000_000_000).toFixed(2)}T`;
  if (cap >= 1_000_000_000) return `${(cap / 1_000_000_000).toFixed(1)}B`;
  if (cap >= 1_000_000) return `${(cap / 1_000_000).toFixed(1)}M`;
  return String(cap.toFixed(0));
}

const APPROX_SUPPLY_M: Record<string, number> = {
  BTC: 19.7, ETH: 120, BNB: 147, SOL: 457, XRP: 56300, DOGE: 145000, ADA: 35000
};

function estimateCryptoMarketCap(symbol: string, price: number): number {
  const supplyM = APPROX_SUPPLY_M[symbol];
  if (supplyM && price > 0) return supplyM * 1_000_000 * price;
  return price * 10_000_000;
}

async function getMarketShifters(country: string): Promise<{ gainers: ShifterItem[]; losers: ShifterItem[] }> {
  try {
    if (country === "CRYPTO") {
      const prices = await prisma.cryptoPrice.findMany({
        orderBy: { change24h: "desc" },
        take: 5,
        include: { asset: true }
      });
      const losersPrices = await prisma.cryptoPrice.findMany({
        orderBy: { change24h: "asc" },
        take: 5,
        include: { asset: true }
      });

      return {
        gainers: prices.map(p => ({ symbol: p.asset.symbol, name: p.asset.symbol, price: p.price, changePercent: p.change24h })),
        losers: losersPrices.map(p => ({ symbol: p.asset.symbol, name: p.asset.symbol, price: p.price, changePercent: p.change24h }))
      };
    } else {
      const prices = await prisma.stockPrice.findMany({
        orderBy: { changePercent: "desc" },
        take: 5,
        include: { asset: true }
      });
      const losersPrices = await prisma.stockPrice.findMany({
        orderBy: { changePercent: "asc" },
        take: 5,
        include: { asset: true }
      });

      return {
        gainers: prices.map(p => ({ symbol: p.asset.symbol, name: p.asset.name, price: p.price, changePercent: p.changePercent })),
        losers: losersPrices.map(p => ({ symbol: p.asset.symbol, name: p.asset.name, price: p.price, changePercent: p.changePercent }))
      };
    }
  } catch {
    return { gainers: [], losers: [] };
  }
}

async function getSectorReturns(country: string): Promise<SectorPerformance[]> {
  try {
    if (country === "CRYPTO") {
      const prices = await prisma.cryptoPrice.findMany({ include: { asset: true } });
      const sectorMap = new Map<string, { totalChange: number; count: number }>();
      for (const p of prices) {
        const sector = CORE_CRYPTO_SECTORS[p.asset.symbol] || "Cryptocurrency";
        const existing = sectorMap.get(sector) || { totalChange: 0, count: 0 };
        existing.totalChange += p.change24h;
        existing.count += 1;
        sectorMap.set(sector, existing);
      }
      return Array.from(sectorMap.entries()).map(([name, data]) => ({
        name,
        change: parseFloat((data.totalChange / data.count).toFixed(2))
      })).sort((a, b) => b.change - a.change);
    } else {
      const prices = await prisma.stockPrice.findMany({ include: { asset: true } });
      const sectorMap = new Map<string, { totalChange: number; count: number }>();
      for (const p of prices) {
        const profile = CORE_STOCKS[p.asset.symbol];
        if (!profile) continue;
        const existing = sectorMap.get(profile.sector) || { totalChange: 0, count: 0 };
        existing.totalChange += p.changePercent;
        existing.count += 1;
        sectorMap.set(profile.sector, existing);
      }
      return Array.from(sectorMap.entries()).map(([name, data]) => ({
        name,
        change: parseFloat((data.totalChange / data.count).toFixed(2))
      })).sort((a, b) => b.change - a.change);
    }
  } catch {
    return [];
  }
}
