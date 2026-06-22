/**
 * /api/stocks/[symbol] — Stock/Crypto detail endpoint
 * 
 * Returns full details for a specific asset including:
 * - Details/Profile
 * - Current price + mock price history for charts
 * - Default fundamental metrics for stocks
 */

import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { dataCache, cacheKey } from "@/data-layer/cache";

export const dynamic = "force-dynamic";

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
  VZ: { sector: "Technology", industry: "Telecom Services" }
};

const CORE_CRYPTO_SECTORS: Record<string, string> = {
  BTC: "Layer 1", ETH: "Layer 1", BNB: "Exchange Tokens", SOL: "Layer 1",
  XRP: "Payment", USDC: "Stablecoins", DOGE: "Meme Coins", ADA: "Layer 1",
  TRX: "Layer 1", AVAX: "Layer 1", TON: "Layer 1", LINK: "DeFi",
  SHIB: "Meme Coins", DOT: "Layer 1", BCH: "Payment", NEAR: "Layer 1",
  LTC: "Payment", UNI: "DeFi", SUI: "Layer 1", APT: "Layer 1"
};

const APPROX_SUPPLY_M: Record<string, number> = {
  BTC: 19.7, ETH: 120, BNB: 147, SOL: 457, XRP: 56300, DOGE: 145000, ADA: 35000
};

function estimateCryptoMarketCap(symbol: string, price: number): number {
  const supplyM = APPROX_SUPPLY_M[symbol];
  if (supplyM && price > 0) return supplyM * 1_000_000 * price;
  return price * 10_000_000;
}

interface ChartBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

function generateMockChart(currentPrice: number, days: number): ChartBar[] {
  const chart: ChartBar[] = [];
  let price = currentPrice || 100;
  const now = new Date();
  for (let i = 0; i < days; i++) {
    const date = new Date(now);
    date.setDate(now.getDate() - i);
    const change = (Math.random() - 0.495) * 0.025; // slight upward drift
    const open = price * (1 - change);
    const close = price;
    const high = Math.max(open, close) * (1 + Math.random() * 0.008);
    const low = Math.min(open, close) * (1 - Math.random() * 0.008);
    const volume = Math.round(100000 + Math.random() * 900000);

    chart.unshift({
      date: date.toISOString().split("T")[0],
      open: parseFloat(open.toFixed(4)),
      high: parseFloat(high.toFixed(4)),
      low: parseFloat(low.toFixed(4)),
      close: parseFloat(close.toFixed(4)),
      volume,
    });
    price = open;
  }
  return chart;
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ symbol: string }> }
) {
  const { symbol } = await params;
  const { searchParams } = new URL(request.url);
  const days = Math.min(3650, Math.max(1, parseInt(searchParams.get("days") || "30", 10)));

  if (!symbol) {
    return NextResponse.json({ error: "Symbol is required" }, { status: 400 });
  }

  const ck = cacheKey("asset-detail", symbol.toUpperCase(), String(days));
  const cached = dataCache.get(ck);
  if (cached) {
    return NextResponse.json(cached);
  }

  try {
    const upperSymbol = symbol.toUpperCase();

    // 1. Try Crypto Asset first
    const cryptoAsset = await prisma.cryptoAsset.findUnique({
      where: { symbol: upperSymbol },
      include: { price: true }
    });

    if (cryptoAsset) {
      if (!cryptoAsset.isActive) {
        try {
          await prisma.cryptoAsset.update({
            where: { id: cryptoAsset.id },
            data: { isActive: true }
          });
          cryptoAsset.isActive = true;
          
          // Also fetch Binance price on the fly
          const res = await fetch(`https://api.binance.com/api/v3/ticker/24hr?symbol=${cryptoAsset.symbol}USDT`);
          if (res.ok) {
            const ticker = await res.json();
            if (ticker?.lastPrice) {
              const price = parseFloat(ticker.lastPrice) || 0;
              const volume = parseFloat(ticker.quoteVolume) || 0;
              const change24h = parseFloat(ticker.priceChangePercent) || 0;
              const priceRow = await prisma.cryptoPrice.upsert({
                where: { assetId: cryptoAsset.id },
                update: { price, volume, change24h, lastUpdated: new Date() },
                create: { assetId: cryptoAsset.id, price, volume, change24h, lastUpdated: new Date() }
              });
              cryptoAsset.price = priceRow;
            }
          }
        } catch (e) {
          console.warn(`[crypto-api] On-the-fly activation failed for ${upperSymbol}:`, e);
        }
      }

      const priceVal = cryptoAsset.price?.price ?? 0;
      const change24h = cryptoAsset.price?.change24h ?? 0;
      const volumeVal = cryptoAsset.price?.volume ?? 0;
      const prevPriceVal = priceVal / (1 + change24h / 100);
      const priceChangeVal = priceVal - prevPriceVal;

      const chart = generateMockChart(priceVal, days);
      const high52w = Math.max(...chart.map(c => c.high));
      const low52w = Math.min(...chart.map(c => c.low));

      const result = {
        symbol: cryptoAsset.symbol,
        name: cryptoAsset.symbol,
        sector: CORE_CRYPTO_SECTORS[cryptoAsset.symbol] || "Cryptocurrency",
        industry: "Cryptocurrency",
        country: "CRYPTO",
        exchange: "BINANCE",
        isActive: cryptoAsset.isActive,
        price: priceVal,
        previousClose: prevPriceVal,
        change: priceChangeVal,
        changePercent: change24h,
        high52w,
        low52w,
        avgVolume: volumeVal,
        marketCap: estimateCryptoMarketCap(cryptoAsset.symbol, priceVal),
        fundamentals: null,
        fundamentalsHistory: [],
        chart,
        aliases: []
      };

      dataCache.set(ck, result, 60);
      return NextResponse.json(result);
    }

    // 2. Try Stock Asset
    const stockAsset = await prisma.stockAsset.findUnique({
      where: { symbol: upperSymbol },
      include: { price: true }
    });

    if (stockAsset) {
      if (!stockAsset.isActive) {
        try {
          await prisma.stockAsset.update({
            where: { id: stockAsset.id },
            data: { isActive: true }
          });
          stockAsset.isActive = true;

          const finnhubToken = process.env.FINNHUB_TOKEN || process.env.FINNHUB_API_KEY || "d8gau59r01qlgcuietn0d8gau59r01qlgcuietng";
          const res = await fetch(`https://finnhub.io/api/v1/quote?symbol=${stockAsset.symbol}&token=${finnhubToken}`);
          if (res.ok) {
            const quote = await res.json();
            if (quote?.c) {
              const price = quote.c || 0;
              const changePercent = quote.dp || 0;
              
              // Upsert price row
              const priceRow = await prisma.stockPrice.upsert({
                where: { assetId: stockAsset.id },
                update: { price, changePercent, lastUpdated: new Date() },
                create: { assetId: stockAsset.id, price, changePercent, lastUpdated: new Date() }
              });
              stockAsset.price = priceRow;
            }
          }
        } catch (e) {
          console.warn(`[stocks-api] On-the-fly activation failed for ${upperSymbol}:`, e);
        }
      }
      const priceVal = stockAsset.price?.price ?? 0;
      const changePercent = stockAsset.price?.changePercent ?? 0;
      const prevPriceVal = priceVal / (1 + changePercent / 100);
      const priceChangeVal = priceVal - prevPriceVal;
      const marketCapVal = stockAsset.price?.marketCap ?? 0;

      const chart = generateMockChart(priceVal, days);
      const high52w = Math.max(...chart.map(c => c.high));
      const low52w = Math.min(...chart.map(c => c.low));
      const profile = CORE_STOCKS[stockAsset.symbol] || { sector: "Technology", industry: "Equities" };

      const result = {
        symbol: stockAsset.symbol,
        name: stockAsset.name,
        sector: profile.sector,
        industry: profile.industry,
        country: "US",
        exchange: "US Markets",
        isActive: stockAsset.isActive,
        price: priceVal,
        previousClose: prevPriceVal,
        change: priceChangeVal,
        changePercent,
        high52w,
        low52w,
        avgVolume: 50000000,
        marketCap: marketCapVal,
        fundamentals: {
          period: "Q1 2026",
          date: "2026-03-31",
          revenue: 90753000000,
          netIncome: 23636000000,
          eps: 1.53,
          peRatio: 27.5,
          pbRatio: 35.2,
          debtToEquity: 1.4,
          roe: 154.2,
          freeCashFlow: 20720000000,
          dividendYield: 0.55,
          marketCap: marketCapVal
        },
        fundamentalsHistory: [],
        chart,
        aliases: []
      };

      dataCache.set(ck, result, 60);
      return NextResponse.json(result);
    }

    return NextResponse.json(
      { error: `Asset ${symbol} not found` },
      { status: 404 }
    );
  } catch (err) {
    console.error(`[api/stocks/${symbol}] Error:`, err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
