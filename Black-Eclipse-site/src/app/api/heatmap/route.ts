import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { toMarketId, currencyFor } from "@/lib/markets";
import { heatmapMeta, type HeatmapSector, type HeatmapStock } from "@/lib/heatmap";

export const dynamic = "force-dynamic";

// GET /api/heatmap?market=US&limit=160
//
// Builds a sector-grouped treemap heatmap from real JDDS price data. Each
// stock is sized by market cap (falling back to 24h volume) and coloured by
// its percent change on the client. No fabricated data: markets with no priced
// assets return an empty payload and the widget renders an UNAVAILABLE note.
const DEFAULT_LIMIT = 160;
const MAX_LIMIT = 220;

function clampInt(raw: string | null, fallback: number, min: number, max: number): number {
  const n = parseInt(raw || "", 10);
  if (isNaN(n)) return fallback;
  return Math.min(max, Math.max(min, n));
}

interface Priced {
  symbol: string;
  name: string;
  sector: string;
  price: number;
  changePct: number;
  marketCap: number;
  volume: number;
  size: number;
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const market = toMarketId((searchParams.get("market") || "US").toUpperCase());
  const limit = clampInt(searchParams.get("limit"), DEFAULT_LIMIT, 20, MAX_LIMIT);
  const meta = heatmapMeta(market);

  try {
    // Restrict to common stock where the market carries security-type metadata
    // (excludes ETFs/funds from an equity heatmap). Markets imported without
    // metadata (securityType null) are kept. Crypto is exempt — its security
    // types are chain standards (ERC-20, SPL, ...), not asset classes.
    const equityFilter =
      market === "CRYPTO"
        ? {}
        : { OR: [{ securityType: null }, { securityType: { contains: "Stock" } }] };

    const rows = await prisma.asset.findMany({
      where: {
        marketId: market,
        isActive: true,
        price: { isNot: null },
        ...equityFilter,
      },
      select: {
        symbol: true,
        name: true,
        sector: true,
        price: { select: { price: true, changePct: true, marketCap: true, volume: true } },
      },
      orderBy: [
        { price: { marketCap: { sort: "desc", nulls: "last" } } },
        { price: { volume: { sort: "desc", nulls: "last" } } },
      ],
      take: limit * 4,
    });

    const priced: Priced[] = [];
    for (const r of rows) {
      const p = r.price;
      if (!p || !(p.price > 0)) continue;
      const marketCap = p.marketCap && p.marketCap > 0 ? p.marketCap : 0;
      const volume = p.volume && p.volume > 0 ? p.volume : 0;
      const size = marketCap || volume;
      if (size <= 0) continue;
      priced.push({
        symbol: r.symbol,
        name: r.name,
        sector: r.sector || (market === "CRYPTO" ? "Crypto" : "Other"),
        price: p.price,
        changePct: p.changePct ?? 0,
        marketCap,
        volume,
        size,
      });
    }

    priced.sort((a, b) => b.size - a.size);
    const stocks = priced.slice(0, limit);

    // Group by sector, cap-weighted sector change.
    const bySector = new Map<string, Priced[]>();
    for (const s of stocks) {
      const list = bySector.get(s.sector) || [];
      list.push(s);
      bySector.set(s.sector, list);
    }

    let totalSize = 0;
    let totalWeightedChange = 0;
    const sectors: HeatmapSector[] = [...bySector.entries()]
      .map(([name, list]) => {
        let cap = 0;
        let weighted = 0;
        const sectorStocks: HeatmapStock[] = list.map(s => {
          cap += s.size;
          weighted += s.size * s.changePct;
          return {
            symbol: s.symbol,
            name: s.name,
            sector: name,
            price: s.price,
            changePct: s.changePct,
            marketCap: s.marketCap,
            volume: s.volume,
          };
        });
        const change = cap > 0 ? weighted / cap : 0;
        totalSize += cap;
        totalWeightedChange += weighted;
        return { name, change: +change.toFixed(4), marketCap: cap, stocks: sectorStocks };
      })
      // Biggest sectors first (matches the finviz layout — Tech top-left).
      .sort((a, b) => b.marketCap - a.marketCap);

    const overall = totalSize > 0 ? totalWeightedChange / totalSize : 0;

    return NextResponse.json({
      market,
      country: meta.country,
      indexName: meta.index,
      currency: currencyFor(market),
      asOf: new Date().toISOString(),
      live: stocks.length,
      change: +overall.toFixed(4),
      sectors,
      empty: stocks.length === 0,
    });
  } catch (err) {
    console.error("[api/heatmap] GET error:", err);
    return NextResponse.json(
      {
        market,
        country: meta.country,
        indexName: meta.index,
        currency: currencyFor(market),
        asOf: new Date().toISOString(),
        live: 0,
        change: 0,
        sectors: [],
        empty: true,
      },
      { status: 200 }
    );
  }
}
