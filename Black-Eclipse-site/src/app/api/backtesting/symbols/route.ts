import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const query = searchParams.get("query") || "";
    const assetClass = searchParams.get("assetClass") || "";
    const market = searchParams.get("market") || "";
    const country = searchParams.get("country") || "";
    const exchange = searchParams.get("exchange") || "";
    const page = parseInt(searchParams.get("page") || "1", 10);
    const limit = parseInt(searchParams.get("limit") || "50", 10);
    const skip = (page - 1) * limit;

    // Ensure major symbols exist in the universe
    const count = await prisma.assetSymbol.count();
    if (count < 10) {
      const majorSymbols = [
        { symbol: "BTC", displayName: "Bitcoin", assetClass: "crypto", market: "Crypto", exchange: "Binance", country: "Global" },
        { symbol: "ETH", displayName: "Ethereum", assetClass: "crypto", market: "Crypto", exchange: "Binance", country: "Global" },
        { symbol: "SOL", displayName: "Solana", assetClass: "crypto", market: "Crypto", exchange: "Binance", country: "Global" },
        { symbol: "XRP", displayName: "Ripple", assetClass: "crypto", market: "Crypto", exchange: "Binance", country: "Global" },
        { symbol: "AAPL", displayName: "Apple Inc.", assetClass: "stock", market: "US Stocks", exchange: "NASDAQ", country: "US" },
        { symbol: "MSFT", displayName: "Microsoft Corp.", assetClass: "stock", market: "US Stocks", exchange: "NASDAQ", country: "US" },
        { symbol: "NVDA", displayName: "NVIDIA Corp.", assetClass: "stock", market: "US Stocks", exchange: "NASDAQ", country: "US" },
        { symbol: "TSLA", displayName: "Tesla Inc.", assetClass: "stock", market: "US Stocks", exchange: "NASDAQ", country: "US" },
        { symbol: "SPY", displayName: "SPDR S&P 500 ETF Trust", assetClass: "stock", market: "US Stocks", exchange: "NYSE", country: "US" },
        { symbol: "EURUSD=X", displayName: "EUR/USD Forex", assetClass: "forex", market: "Forex", exchange: "Yahoo", country: "Global" },
        { symbol: "GBPUSD=X", displayName: "GBP/USD Forex", assetClass: "forex", market: "Forex", exchange: "Yahoo", country: "Global" },
        { symbol: "GC=F", displayName: "Gold Futures", assetClass: "commodities", market: "Commodities", exchange: "COMEX", country: "US" },
        { symbol: "CL=F", displayName: "Crude Oil Futures", assetClass: "commodities", market: "Commodities", exchange: "NYMEX", country: "US" }
      ];
      for (const ms of majorSymbols) {
        await prisma.assetSymbol.upsert({
          where: {
            symbol_exchange_assetClass: {
              symbol: ms.symbol,
              exchange: ms.exchange,
              assetClass: ms.assetClass
            }
          },
          update: { displayName: ms.displayName },
          create: {
            symbol: ms.symbol,
            displayName: ms.displayName,
            assetClass: ms.assetClass,
            market: ms.market,
            exchange: ms.exchange,
            country: ms.country,
            availableTimeframes: ["1m", "5m", "15m", "1h", "1d", "1w", "1M"],
            isBacktestEnabled: true,
            dataStatus: "needs_download"
          }
        });
      }
    }

    const where: any = { isActive: true };

    if (query) {
      where.OR = [
        { symbol: { contains: query, mode: "insensitive" } },
        { displayName: { contains: query, mode: "insensitive" } },
      ];
    }
    if (assetClass) where.assetClass = assetClass;
    if (market) where.market = market;
    if (country) where.country = country;
    if (exchange) where.exchange = exchange;

    const [total, symbols] = await Promise.all([
      prisma.assetSymbol.count({ where }),
      prisma.assetSymbol.findMany({
        where,
        orderBy: { symbol: "asc" },
        skip,
        take: limit,
      }),
    ]);

    return NextResponse.json({
      symbols,
      pagination: {
        page,
        limit,
        total,
        totalPages: Math.ceil(total / limit),
      },
    });
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || "Failed to fetch symbols." },
      { status: 500 }
    );
  }
}
