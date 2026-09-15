import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { toMarketId, currencyFor } from "@/lib/markets";
import { heatmapMeta, type HeatmapSector, type HeatmapStock } from "@/lib/heatmap";

export const dynamic = "force-dynamic";

// GET /api/heatmap?market=US&limit=160
//
// Builds a sector-grouped treemap heatmap from real JDDS price data. Each
// stock is sized by market cap (falling back to 24h volume) and coloured by
// its percent change on the client. Forex and commodities have no JDDS Asset
// rows of their own — their treemaps are built from the same cached Yahoo
// quote payloads the /api/forex and /api/commodities routes persist, grouped
// into currencies / metal, energy, agriculture. No fabricated data: markets
// with no priced assets return an empty payload and the widget renders an
// UNAVAILABLE note.
const DEFAULT_LIMIT = 160;
const MAX_LIMIT = 220;

/** Synthetic asset markets built from cached quote feeds, not JDDS assets. */
const FEED_MARKETS = new Set(["FOREX", "COMMODITIES"]);

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

// ── Feed-backed heatmaps (Forex / Commodities) ───────────────────────────────
// Reads the persisted Yahoo payload from SystemConfig (written by /api/forex and
// /api/commodities) and groups the instruments into treemap sectors. Size is a
// per-instrument volume proxy (USD notional is not available), so tiles are
// sized by how actively each instrument is quoted.

// FX grouped into a handful of readable buckets — one sector per currency
// would render ~32 tiny bands, which is worse than useless on a treemap.
const FOREX_BUCKET: Record<string, string> = {
  EUR: "Majors", GBP: "Majors", JPY: "Majors", CHF: "Majors",
  AUD: "Commodity", NZD: "Commodity", CAD: "Commodity",
  CNY: "Asia", INR: "Asia", PKR: "Asia", KRW: "Asia", THB: "Asia",
  IDR: "Asia", VND: "Asia", SGD: "Asia", HKD: "Asia", PHP: "Asia",
  MYR: "Asia", ILS: "Asia",
  PLN: "Europe", SEK: "Europe", NOK: "Europe", DKK: "Europe",
  HUF: "Europe", CZK: "Europe", TRY: "Europe", RUB: "Europe",
  BRL: "Americas", MXN: "Americas", ZAR: "Africa", EGP: "Africa",
  NGN: "Africa", AED: "Middle East", SAR: "Middle East",
};

// Coins imported before category enrichment (or with no CoinGecko categories)
// land in sector "Other" — 1300+ of them, which renders as one giant tile and
// hides the real per-coin moves. Fall back to a market-cap tier so crypto
// groups into a few readable buckets instead of a single "Other".
function cryptoBucket(marketCap: number): string {
  if (marketCap >= 10e9) return "Large Cap";
  if (marketCap >= 1e9) return "Mid Cap";
  if (marketCap >= 100e6) return "Small Cap";
  return "Micro Cap";
}

function commoditySector(name: string): string {
  const n = name.toLowerCase();
  if (/gold|silver|platinum|palladium/.test(n)) return "Precious Metals";
  if (/copper|aluminum/.test(n)) return "Base Metals";
  if (/oil|brent|gas/.test(n)) return "Energy";
  if (/wheat|corn|soybean|cattle|coffee|cocoa|sugar|cotton/.test(n)) return "Agriculture";
  return "Other";
}

interface FeedQuote { symbol: string; name: string; price: number; changePct: number; found: boolean; base?: string; quote?: string; }

async function buildFeedHeatmap(market: "FOREX" | "COMMODITIES", limit: number, meta: ReturnType<typeof heatmapMeta>) {
  const key = market === "FOREX" ? "api_cache:forex" : "api_cache:commodities";
  let quotes: FeedQuote[] = [];
  try {
    const row = await prisma.systemConfig.findUnique({ where: { key } });
    if (row?.value) {
      const parsed = JSON.parse(row.value);
      quotes = (market === "FOREX" ? parsed.pairs : parsed.commodities) ?? [];
    }
  } catch { /* ignore — empty payload below */ }

  const priced: Priced[] = quotes
    .filter(q => q.found && q.price > 0)
    .map(q => {
      // Group FX by the NON-USD leg into readable buckets (Majors, Asia, …).
      const fxLeg = q.base === "USD" ? (q.quote ?? "") : (q.base ?? "");
      const sector = market === "FOREX"
        ? (FOREX_BUCKET[fxLeg] || FOREX_BUCKET[q.base ?? ""] || FOREX_BUCKET[q.quote ?? ""] || "Other")
        : commoditySector(q.name);
      // FX majors aren't market-cap weighted; give each pair an equal tile.
      const size = market === "FOREX" ? 1 : q.price;
      return {
        symbol: market === "FOREX" ? q.symbol.replace("=X", "") : q.symbol.replace("=F", ""),
        name: q.name,
        sector,
        price: q.price,
        changePct: q.changePct ?? 0,
        marketCap: 0,
        volume: q.price,
        size,
      };
    })
    .slice(0, limit);

  return assemblePayload(market, meta, priced);
}

/** Group priced instruments into sectors and compute cap-weighted changes. */
function assemblePayload(market: string, meta: ReturnType<typeof heatmapMeta>, stocks: Priced[]) {
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
    .sort((a, b) => b.marketCap - a.marketCap);

  const overall = totalSize > 0 ? totalWeightedChange / totalSize : 0;

  return {
    market,
    country: meta.country,
    indexName: meta.index,
    currency: currencyFor(market),
    asOf: new Date().toISOString(),
    live: stocks.length,
    change: +overall.toFixed(4),
    sectors,
    empty: stocks.length === 0,
  };
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const market = toMarketId((searchParams.get("market") || "US").toUpperCase());
  const limit = clampInt(searchParams.get("limit"), DEFAULT_LIMIT, 20, MAX_LIMIT);
  const meta = heatmapMeta(market);

  if (FEED_MARKETS.has(market)) {
    try {
      return NextResponse.json(await buildFeedHeatmap(market as "FOREX" | "COMMODITIES", limit, meta));
    } catch (err) {
      console.error("[api/heatmap] feed payload error:", err);
      return NextResponse.json({ market, country: meta.country, indexName: meta.index, currency: currencyFor(market), asOf: new Date().toISOString(), live: 0, change: 0, sectors: [], empty: true });
    }
  }

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
        securityType: true,
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
      // Crypto: an unenriched coin has sector "Other" — bucket it by market-cap
      // tier so it doesn't form one giant tile that swallows the whole board.
      const rawSector = r.sector && r.sector !== "Other" ? r.sector : null;
      const sector = market === "CRYPTO"
        ? (rawSector ?? cryptoBucket(marketCap))
        : (r.sector ?? "Other");
      priced.push({
        symbol: r.symbol,
        name: r.name,
        sector,
        price: p.price,
        changePct: p.changePct ?? 0,
        marketCap,
        volume,
        size,
      });
    }

    priced.sort((a, b) => b.size - a.size);
    return NextResponse.json(assemblePayload(market, meta, priced.slice(0, limit)));
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
