import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { getSimulatedDashboard, type StockItem } from "@/components/screens/market-data";
import { MARKET_SEEDS } from "@/lib/scraper";

export const dynamic = "force-dynamic";

// Map JDDS Asset+Price records into the StockItem shape the screener expects.
function toStockItem(
  asset: { symbol: string; name: string; sector: string | null; industry: string | null; country: string | null; securityType: string | null; assetClass: string | null },
  price: { price: number; changePct: number; marketCap: number | null; volume: number | null; peRatio: number | null; rank?: number | null; circulatingSupply?: number | null; totalSupply?: number | null; maxSupply?: number | null; ath?: number | null; atl?: number | null; athChangePct?: number | null; source?: string | null } | null,
  country: string
): StockItem {
  const marketCap = price?.marketCap ?? 0;
  const volume = price?.volume ?? 0;
  const isCrypto = country === "CRYPTO";
  const supplyFmt = (v?: number | null): string => {
    if (v == null) return "N/A";
    if (v >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
    if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
    if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
    if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
    return `${Math.floor(v)}`;
  };
  return {
    symbol: asset.symbol,
    name: asset.name,
    sector: asset.sector || "Other",
    industry: asset.industry || "Other",
    securityType: asset.securityType || (isCrypto ? "Crypto" : "N/A"),
    assetClass: asset.assetClass || (isCrypto ? "Crypto" : "N/A"),
    country: asset.country || country,
    price: price?.price ?? 0,
    changePercent: price?.changePct ?? 0,
    priceMissing: !price,
    priceSource: price?.source || null,
    volume: volume > 0 ? formatVol(volume) : "N/A",
    marketCap: marketCap > 0 ? formatCap(marketCap) : "N/A",
    peRatio: price?.peRatio != null ? price.peRatio.toFixed(2) : "N/A",
    dividendYield: "None",
    index: "JDDS",
    recommendation: "N/A",
    exchange: isCrypto ? "GLOBAL" : country,
    forwardPE: "N/A",
    peg: "N/A",
    ps: "N/A",
    pb: "N/A",
    evEbitda: "N/A",
    grossMargin: "N/A",
    operatingMargin: "N/A",
    netProfitMargin: "N/A",
    insiderOwnership: "N/A",
    institutionalOwnership: "N/A",
    shortFloat: "N/A",
    rsi14: "N/A",
    sma20: "N/A",
    sma50: "N/A",
    sma200: "N/A",
    marketCapRaw: marketCap,
    volumeRaw: volume,
    rank: price?.rank ?? undefined,
    circulatingSupplyRaw: price?.circulatingSupply ?? undefined,
    maxSupplyRaw: price?.maxSupply ?? undefined,
    circulatingSupply: supplyFmt(price?.circulatingSupply),
    maxSupply: supplyFmt(price?.maxSupply),
    athChangePercent: price?.athChangePct ?? 0,
    ath: price?.ath != null ? String(price.ath) : "N/A",
    athDate: "N/A",
    atl: price?.atl != null ? String(price.atl) : "N/A",
    atlChangePercent: price?.athChangePct ?? 0,
    totalSupply: supplyFmt(price?.totalSupply),
  };
}

function formatVol(v: number): string {
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return String(v);
}

function formatCap(v: number): string {
  if (v >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  return String(v);
}

function clampInt(raw: string | null, fallback: number, min: number, max: number): number {
  const n = parseInt(raw || "", 10);
  if (isNaN(n)) return fallback;
  return Math.min(max, Math.max(min, n));
}

// Market cap filter → { min, max } in raw dollars.
function capFilterRange(f: string): { min: number | null; max: number | null } | null {
  switch (f) {
    case "Mega": return { min: 100e9, max: null };
    case "Large": return { min: 10e9, max: 100e9 };
    case "Mid": return { min: 2e9, max: 10e9 };
    case "Small": return { min: 0, max: 2e9 };
    default: return null;
  }
}

function peFilterRange(f: string): { min: number | null; max: number | null } | null {
  switch (f) {
    case "Under15": return { min: null, max: 15 };
    case "Under20": return { min: null, max: 20 };
    case "Under30": return { min: null, max: 30 };
    case "Over30": return { min: 30, max: null };
    case "Over50": return { min: 50, max: null };
    default: return null;
  }
}

function priceFilterRange(f: string): { min: number | null; max: number | null } | null {
  switch (f) {
    case "Under10": return { min: null, max: 10 };
    case "Under50": return { min: null, max: 50 };
    case "Under100": return { min: null, max: 100 };
    case "Over100": return { min: 100, max: null };
    case "Over500": return { min: 500, max: null };
    default: return null;
  }
}

function changeFilterRange(f: string): { min: number | null; max: number | null } | null {
  switch (f) {
    case "Positive": return { min: 0, max: null };
    case "Negative": return { min: null, max: 0 };
    case "Over2": return { min: 2, max: null };
    case "UnderMinus2": return { min: null, max: -2 };
    default: return null;
  }
}

function volumeFilterRange(f: string): { min: number | null; max: number | null } | null {
  switch (f) {
    case "Under1": return { min: null, max: 1e6 };
    case "1to10": return { min: 1e6, max: 10e6 };
    case "Over10": return { min: 10e6, max: null };
    case "Over30": return { min: 30e6, max: null };
    default: return null;
  }
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const rawCountry = searchParams.get("country") || "US";
  const country = rawCountry.toUpperCase() === "CRYPTO" ? "CRYPTO" : rawCountry;
  const typeFilter = (searchParams.get("type") || "").trim().toLowerCase();
  const search = (searchParams.get("search") || "").trim().toLowerCase();
  const sector = (searchParams.get("sector") || "").trim();
  const industry = (searchParams.get("industry") || "").trim();
  const countryFilter = (searchParams.get("countryFilter") || "").trim();
  const marketCapFilter = (searchParams.get("marketCap") || "").trim();
  const peFilter = (searchParams.get("pe") || "").trim();
  const priceFilter = (searchParams.get("price") || "").trim();
  const changeFilter = (searchParams.get("change") || "").trim();
  const volumeFilter = (searchParams.get("volume") || "").trim();

  // Pagination — default 20/page, allow 20/50/100.
  const page = clampInt(searchParams.get("page"), 1, 1, 100000);
  const limit = clampInt(searchParams.get("limit"), 20, 1, 100);

  try {
    // Map UI country codes to JDDS market ids.
    const marketIdMap: Record<string, string> = {
      US: "US",
      USA: "US",
      PK: "PK",
      IN: "IN",
      CRYPTO: "CRYPTO",
      China: "CN",
      Taiwan: "TW",
    };
    const marketId = marketIdMap[country] || country;

    // Build the DB-level filter so we never pull the whole universe into memory.
    const where: Record<string, unknown> = {
      market: { id: marketId, enabled: true },
      isActive: true,
    };
    if (typeFilter && typeFilter !== "all") {
      where.securityType = { contains: typeFilter };
    }
    if (sector && sector !== "All") {
      where.sector = sector;
    }
    if (industry && industry !== "All") {
      where.industry = industry;
    }
    if (countryFilter && countryFilter !== "All") {
      where.country = countryFilter;
    }
    if (search) {
      where.OR = [
        { symbol: { contains: search } },
        { name: { contains: search } },
      ];
    }

    // Numeric filters applied on the Price relation (server-side, full universe).
    const priceWhere: Record<string, unknown> = {};
    if (marketCapFilter && marketCapFilter !== "All") {
      const cap = capFilterRange(marketCapFilter);
      if (cap) {
        priceWhere.marketCap = cap.min != null && cap.max != null
          ? { gte: cap.min, lt: cap.max }
          : cap.min != null ? { gte: cap.min } : { lt: cap.max! };
      }
    }
    if (peFilter && peFilter !== "All") {
      const pe = peFilterRange(peFilter);
      if (pe) {
        priceWhere.peRatio = pe.min != null && pe.max != null
          ? { gte: pe.min, lt: pe.max }
          : pe.min != null ? { gte: pe.min } : { lt: pe.max! };
      }
    }
    if (priceFilter && priceFilter !== "All") {
      const pr = priceFilterRange(priceFilter);
      if (pr) {
        priceWhere.price = pr.min != null && pr.max != null
          ? { gte: pr.min, lt: pr.max }
          : pr.min != null ? { gte: pr.min } : { lt: pr.max! };
      }
    }
    if (changeFilter && changeFilter !== "All") {
      const ch = changeFilterRange(changeFilter);
      if (ch) {
        priceWhere.changePct = ch.min != null && ch.max != null
          ? { gte: ch.min, lt: ch.max }
          : ch.min != null ? { gte: ch.min } : { lt: ch.max! };
      }
    }
    if (volumeFilter && volumeFilter !== "All") {
      const vol = volumeFilterRange(volumeFilter);
      if (vol) {
        priceWhere.volume = vol.min != null && vol.max != null
          ? { gte: vol.min, lt: vol.max }
          : vol.min != null ? { gte: vol.min } : { lt: vol.max! };
      }
    }
    if (Object.keys(priceWhere).length > 0) {
      where.price = priceWhere;
    }

    const [total, assets] = await Promise.all([
      prisma.asset.count({ where }),
      prisma.asset.findMany({
        where,
        include: { price: true },
        orderBy: marketId === "CRYPTO"
          ? [{ price: { rank: { sort: "asc", nulls: "last" } } }]
          : { symbol: "asc" },
        skip: (page - 1) * limit,
        take: limit,
      }),
    ]);

    let stocks: StockItem[] = [];
    if (assets.length > 0) {
      stocks = assets.map((a) => toStockItem(a, a.price, marketId));
    } else if (total === 0) {
      // JDDS empty for this market → fall back to demo/seed data.
      const seed = MARKET_SEEDS.find((m) => m.id === marketId);
      stocks = (seed?.symbols || []).map((s) =>
        toStockItem({ symbol: s.symbol, name: s.name, sector: s.sector || null, industry: s.industry || null, country: marketId, securityType: null, assetClass: null }, null, marketId)
      );
    }

    const totalPages = Math.max(1, Math.ceil(total / limit));
    const dash = getSimulatedDashboard(marketId === "CRYPTO" ? "CRYPTO" : "US");

    // Distinct filter options for dynamic dropdowns (only for non-crypto markets).
    let filterOptions: { sectors: string[]; industries: string[]; types: string[]; countries: string[] } | null = null;
    if (marketId !== "CRYPTO") {
      const [sectorRows, industryRows, typeRows, countryRows] = await Promise.all([
        prisma.asset.findMany({ where: { marketId, isActive: true }, select: { sector: true }, distinct: ["sector"] }),
        prisma.asset.findMany({ where: { marketId, isActive: true }, select: { industry: true }, distinct: ["industry"] }),
        prisma.asset.findMany({ where: { marketId, isActive: true }, select: { securityType: true }, distinct: ["securityType"] }),
        prisma.asset.findMany({ where: { marketId, isActive: true, country: { not: null } }, select: { country: true }, distinct: ["country"] }),
      ]);
      filterOptions = {
        sectors: sectorRows.map((r) => r.sector).filter((s): s is string => !!s).sort(),
        industries: industryRows.map((r) => r.industry).filter((s): s is string => !!s).sort(),
        types: typeRows.map((r) => r.securityType).filter((s): s is string => !!s).sort(),
        countries: countryRows.map((r) => r.country).filter((s): s is string => !!s).sort(),
      };
    }

    return NextResponse.json({
      stocks,
      indices: dash.indices,
      sectors: dash.sectors,
      shifters: dash.shifters,
      filterOptions,
      source: total > 0 ? "jdds" : "seed",
      pagination: { total, page, limit, totalPages },
    });
  } catch (err) {
    console.error("[api/stocks] Error:", err);
    const dash = getSimulatedDashboard(country === "CRYPTO" ? "CRYPTO" : "US");
    return NextResponse.json(
      {
        stocks: [],
        indices: dash.indices,
        sectors: dash.sectors,
        shifters: dash.shifters,
        source: "error",
        pagination: { total: 0, page: 1, limit: 0, totalPages: 0 },
      },
      { status: 200 }
    );
  }
}
