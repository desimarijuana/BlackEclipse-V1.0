import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { getSimulatedDashboard, type StockItem } from "@/lib/screener/data";
import { MARKET_SEEDS } from "@/lib/scraper";
import { toMarketId, countryToMarketId, MARKET_FULL_NAME } from "@/lib/markets";
import {
  UNCLASSIFIED, normalizeSector, normalizeIndustry,
  rawSectorVariants, rawIndustryVariants,
} from "@/lib/screener/taxonomy";

export const dynamic = "force-dynamic";

// Per-market (+type scope) filter dropdown options (sectors/industries/types/countries).
const filterOptionsCache = new Map<string, { t: number; data: { sectors: string[]; industries: string[]; types: string[]; countries: string[] } }>();

// Build the securityType predicate for a comma-separated type filter, or null
// when it must be skipped. Small markets (HK/IN/JP/CN/TW/UK/DE/TR...) were
// imported without securityType metadata, so enforcing a type filter there
// would empty the whole screener.
async function typePredicate(marketId: string, typeFilter: string): Promise<Record<string, unknown> | null> {
  if (!typeFilter || typeFilter === "all") return null;
  const hasTypeMetadata = await prisma.asset.findFirst({
    where: { marketId, isActive: true, securityType: { not: null } },
    select: { id: true },
  });
  if (!hasTypeMetadata) return null;
  const types = typeFilter.split(",").map((t) => t.trim()).filter(Boolean);
  if (types.length === 0) return null;
  if (types.length === 1) return { securityType: { contains: types[0] } };
  return { OR: types.map((t) => ({ securityType: { contains: t } })) };
}

// Build the DB predicate for a (canonical) sector/industry selection. Because
// the same real sector is stored under multiple synonym labels, the filter must
// match EVERY raw variant. UNCLASSIFIED matches nulls (plus a literal stored
// "Unclassified") so the option the user sees always yields rows.
function taxonomyFilter(field: "sector" | "industry", value: string): Record<string, unknown> {
  if (value === UNCLASSIFIED) {
    return { OR: [{ [field]: null }, { [field]: UNCLASSIFIED }] };
  }
  const variants = field === "sector" ? rawSectorVariants(value) : rawIndustryVariants(value);
  if (variants.length === 1) return { [field]: variants[0] };
  return { OR: variants.map((v) => ({ [field]: v })) };
}

// Map JDDS Asset+Price records into the StockItem shape the screener expects.
function toStockItem(
  asset: { symbol: string; name: string; sector: string | null; industry: string | null; country: string | null; securityType: string | null; assetClass: string | null },
  price: {
    price: number; changePct: number; marketCap: number | null; volume: number | null; peRatio: number | null;
    dividendYield: number | null; rank?: number | null; circulatingSupply?: number | null; totalSupply?: number | null;
    maxSupply?: number | null; ath?: number | null; atl?: number | null; athChangePct?: number | null; atlChangePct?: number | null;
    source?: string | null; updatedAt?: Date | string | null;
    eps?: number | null; fiftyTwoWeekHigh?: number | null; fiftyTwoWeekLow?: number | null;
    forwardPE?: number | null; beta?: number | null; dayHigh?: number | null; dayLow?: number | null;
    open?: number | null; previousClose?: number | null; dividendRate?: number | null; fdv?: number | null;
  } | null,
  country: string
): StockItem {
  const marketCap = price?.marketCap ?? 0;
  const volume = price?.volume ?? 0;
  const isCrypto = country === "CRYPTO";
  // `country` here is the JDDS market id (e.g. "US"). The stored Asset.country
  // value is inconsistent — both "US" and "United States" appear, plus foreign
  // domiciles ("Canada", "Israel", ...). Normalize it to a canonical market code
  // for the table so the Country column and the country filter stay consistent.
  const displayCountry = countryToMarketId(asset.country || country);
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
    // Normalize synonyms so the table and filter agree, and render nulls as
    // "Unclassified" (not "Other", which is a real stored crypto sector).
    sector: normalizeSector(asset.sector),
    industry: normalizeIndustry(asset.industry),
    // Markets imported without securityType metadata (HK/IN/JP/CN/TW/UK/DE/TR)
    // are equities by definition; default to "Stock" so the type filter and
    // the Stocks tab work client-side.
    securityType: asset.securityType || (isCrypto ? "Crypto" : "Stock"),
    assetClass: asset.assetClass || (isCrypto ? "Crypto" : "Equity"),
    country: displayCountry,
    price: price?.price ?? 0,
    changePercent: price?.changePct ?? 0,
    priceMissing: !price,
    priceSource: price?.source || null,
    updatedAt: price?.updatedAt ? new Date(price.updatedAt).toISOString() : null,
    volume: volume > 0 ? formatVol(volume) : "N/A",
    marketCap: marketCap > 0 ? formatCap(marketCap) : "N/A",
    peRatio: price?.peRatio != null ? price.peRatio.toFixed(2) : "N/A",
    dividendYield: price?.dividendYield != null && price.dividendYield > 0 ? `${price.dividendYield.toFixed(2)}%` : "None",
    index: "JDDS",
    recommendation: "N/A",
    exchange: isCrypto ? "GLOBAL" : country,
    forwardPE: price?.forwardPE != null ? price.forwardPE.toFixed(2) : "N/A",
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
    atlChangePercent: price?.atlChangePct ?? 0,
    totalSupply: supplyFmt(price?.totalSupply),
    eps: price?.eps != null ? price.eps.toFixed(2) : "N/A",
    fiftyTwoWeekHigh: price?.fiftyTwoWeekHigh ?? null,
    fiftyTwoWeekLow: price?.fiftyTwoWeekLow ?? null,
    // Day session data (open / high / low / prev close) for the detail view.
    dayHigh: price?.dayHigh ?? null,
    dayLow: price?.dayLow ?? null,
    dayOpen: price?.open ?? null,
    previousClose: price?.previousClose ?? null,
    beta: price?.beta != null ? price.beta.toFixed(2) : "N/A",
    dividendRate: price?.dividendRate != null ? price.dividendRate.toFixed(2) : "N/A",
    fdv: price?.fdv != null ? formatCap(price.fdv) : "N/A",
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
function capFilterRange(f: string): { min: number | null; minExclusive?: boolean; max: number | null } | null {
  switch (f) {
    // Small uses an EXCLUSIVE lower bound: a missing/zero market cap is not a
    // "small cap", and the client predicate requires capMil > 0 (a `gte: 0`
    // server bound let zero-cap rows through and overcounted the footer total).
    case "Small": return { min: 0, minExclusive: true, max: 2e9 };
    case "Mega": return { min: 100e9, max: null };
    case "Large": return { min: 10e9, max: 100e9 };
    case "Mid": return { min: 2e9, max: 10e9 };
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

// NOTE: range predicates are built as `gt`/`gte`/`lt` below. We keep the
// boundary explicit so "Positive" excludes exactly 0 (a flat stock is not a
// gainer) and "Negative" excludes 0 (a flat stock is not a loser).
function changeFilterRange(f: string): { min: number | null; minExclusive?: boolean; max: number | null; maxExclusive?: boolean } | null {
  switch (f) {
    case "Positive": return { min: 0, minExclusive: true, max: null };
    case "Negative": return { min: null, max: 0, maxExclusive: true };
    case "Over2": return { min: 2, max: null };
    case "UnderMinus2": return { min: null, max: -2 };
    default: return null;
  }
}

// Dividend yield filter. `None` = no/zero yield; `Positive` = any dividend;
// `Over2`/`Over5` = at least that percent.
function dividendFilter(f: string): Record<string, unknown> | null {
  switch (f) {
    case "None":
      // No yield = the field is NULL or explicitly 0 (the UI maps both to
      // "None"), so match both rather than NULL only.
      return { OR: [{ dividendYield: null }, { dividendYield: { lte: 0 } }] };
    case "Positive": return { dividendYield: { gt: 0 } };
    case "Over2": return { dividendYield: { gte: 2 } };
    case "Over5": return { dividendYield: { gte: 5 } };
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
  const dividendFilterParam = (searchParams.get("dividend") || "").trim();
  const sortParam = (searchParams.get("sort") || "").trim();

  // Pagination — default 20/page, allow 20/50/100.
  const page = clampInt(searchParams.get("page"), 1, 1, 100000);
  const limit = clampInt(searchParams.get("limit"), 20, 1, 100);

  try {
    // Map UI country codes to JDDS market ids.
    const marketId = toMarketId(rawCountry);

    // Build the DB-level filter so we never pull the whole universe into memory.
    const where: Record<string, unknown> = {
      market: { id: marketId, enabled: true },
      isActive: true,
    };
    // OR-clauses from independent filters (type, search) are collected and
    // ANDed together. Writing them straight to `where.OR` made the last one win
    // — selecting types "Stock,ETF" then typing a search discarded the type
    // match entirely.
    const orGroups: Record<string, unknown>[] = [];
    const typeWhere = await typePredicate(marketId, typeFilter);
    if (typeWhere) orGroups.push(typeWhere);
    if (sector && sector !== "All") {
      orGroups.push(taxonomyFilter("sector", sector));
    }
    if (industry && industry !== "All") {
      orGroups.push(taxonomyFilter("industry", industry));
    }
    if (countryFilter && countryFilter !== "All") {
      // The stored Asset.country is inconsistent ("US" vs "United States"), and
      // the dropdown offers display names. Match every raw form that normalizes
      // to the same market id so filtering by "United States" also finds rows
      // stored as "US" (and vice versa).
      const target = countryToMarketId(countryFilter);
      const rawVariants = Object.entries(MARKET_FULL_NAME)
        .filter(([, name]) => countryToMarketId(name) === target)
        .map(([id, name]) => [id, name]);
      const variants = new Set<string>([countryFilter, target]);
      for (const [id, name] of rawVariants) {
        variants.add(id);
        variants.add(name);
      }
      where.country = { in: [...variants] };
    }
    if (search) {
      orGroups.push({
        OR: [
          { symbol: { contains: search } },
          { name: { contains: search } },
        ],
      });
    }
    if (orGroups.length > 0) {
      where.AND = orGroups;
    }

    // Numeric filters applied on the Price relation (server-side, full universe).
    const priceWhere: Record<string, unknown> = {};
    if (marketCapFilter && marketCapFilter !== "All") {
      const cap = capFilterRange(marketCapFilter);
      if (cap) {
        const capRange: Record<string, number> = {};
        if (cap.max != null) capRange.lt = cap.max;
        if (cap.min != null) capRange[cap.minExclusive ? "gt" : "gte"] = cap.min;
        priceWhere.marketCap = capRange;
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
        const range: Record<string, number> = {};
        if (ch.min != null) range[ch.minExclusive ? "gt" : "gte"] = ch.min;
        if (ch.max != null) range[ch.maxExclusive ? "lt" : "lte"] = ch.max;
        priceWhere.changePct = range;
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
    if (dividendFilterParam && dividendFilterParam !== "All") {
      const div = dividendFilter(dividendFilterParam);
      if (div) Object.assign(priceWhere, div);
    }
    if (Object.keys(priceWhere).length > 0) {
      where.price = priceWhere;
    }

    // Server-side ordering. The UI sorts headers over the full universe, so a
    // page is only meaningful when the DB orders by the same key before
    // slicing. `sort` is a StockItem field name; `dir` is asc|desc. Only
    // DB-backed columns are honoured (symbol/name/securityType/sector/industry/
    // country live on Asset, price/change/marketCap/pe/volume/rank on Price);
    // anything else falls back to the market default.
    const sortDir: "asc" | "desc" = (searchParams.get("dir") || "asc").toLowerCase() === "desc" ? "desc" : "asc";
    const priceSortFields: Record<string, string> = {
      price: "price",
      changePercent: "changePct",
      marketCap: "marketCap",
      peRatio: "peRatio",
      volume: "volume",
      rank: "rank",
    };
    const assetSortFields: Record<string, string> = {
      symbol: "symbol",
      name: "name",
      securityType: "securityType",
      industry: "industry",
      sector: "sector",
      country: "country",
    };
    // `price` and `changePct` are non-nullable Price columns; the generated
    // client rejects `nulls` for them (it only accepts { sort, nulls } on
    // nullable fields). Nullable columns keep nulls-last so missing data sinks.
    const nullablePriceFields = new Set(["marketCap", "peRatio", "volume", "rank"]);
    let orderBy: Record<string, unknown> | Record<string, unknown>[] = { symbol: "asc" };
    if (sortParam && priceSortFields[sortParam]) {
      const column = priceSortFields[sortParam];
      orderBy = [{
        price: {
          [column]: nullablePriceFields.has(column)
            ? { sort: sortDir, nulls: "last" }
            : sortDir,
        },
      }];
    } else if (sortParam && assetSortFields[sortParam]) {
      // Scalar Asset columns take a plain SortOrder (nulls handling is only
      // accepted on the price relation).
      orderBy = [{ [assetSortFields[sortParam]]: sortDir }];
    } else if (marketId === "CRYPTO") {
      orderBy = [{ price: { rank: { sort: "asc", nulls: "last" } } }];
    }

    const [total, assets] = await Promise.all([
      prisma.asset.count({ where }),
      prisma.asset.findMany({
        where,
        include: { price: true },
        orderBy,
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

    // Distinct filter options for dynamic dropdowns. Two rules matter here:
    //   1. Sector/industry options are scoped to the ACTIVE type filter. On the
    //      Stocks tab (type=Stock) the raw market also contains 4,155 ETFs whose
    //      `industry` is really an ETF category ("General", "Bond", "Dividend")
    //      and whose `sector` is the asset class "Equity" — offering those made
    //      ~13 dropdown entries that silently returned zero rows.
    //   2. A null sector/industry is rendered as "Unclassified" in the table, so
    //      the option must exist AND map back to nulls (see taxonomyFilter).
    // Types/countries stay unscoped so the user can always change type.
    let filterOptions: { sectors: string[]; industries: string[]; types: string[]; countries: string[] } | null = null;
    {
      const FILTER_OPTS_TTL_MS = 5 * 60 * 1000;
      const cacheKey = `${marketId}|${typeFilter || "all"}`;
      const cachedOpts = filterOptionsCache.get(cacheKey);
      if (cachedOpts && Date.now() - cachedOpts.t < FILTER_OPTS_TTL_MS) {
        filterOptions = cachedOpts.data;
      } else {
        // Scope for sector/industry options follows the active type filter.
        const optionScope: Record<string, unknown> = { marketId, isActive: true };
        if (typeWhere) optionScope.AND = [typeWhere];
        const [sectorRows, industryRows, typeRows, countryRows, nullSector, nullIndustry] = await Promise.all([
          prisma.asset.findMany({ where: optionScope, select: { sector: true }, distinct: ["sector"] }),
          prisma.asset.findMany({ where: optionScope, select: { industry: true }, distinct: ["industry"] }),
          prisma.asset.findMany({ where: { marketId, isActive: true }, select: { securityType: true }, distinct: ["securityType"] }),
          prisma.asset.findMany({ where: { marketId, isActive: true, country: { not: null } }, select: { country: true }, distinct: ["country"] }),
          prisma.asset.count({ where: { ...optionScope, sector: null } }),
          prisma.asset.count({ where: { ...optionScope, industry: null } }),
        ]);
        // Normalize then dedupe: synonyms collapse to one canonical option so a
        // sector never appears twice under two labels. `normalize` only applied
        // to present values — nulls are surfaced separately via the sentinel.
        const clean = (vals: (string | null)[], normalize: (v: string) => string): string[] =>
          [...new Set(vals.filter((s): s is string => !!s).map(normalize))].sort((a, b) => a.localeCompare(b));
        const sectors = new Set(clean(sectorRows.map((r) => r.sector), normalizeSector));
        const industries = new Set(clean(industryRows.map((r) => r.industry), normalizeIndustry));
        // Sentinel sorts last so the real taxonomy leads.
        if (nullSector > 0) sectors.add(UNCLASSIFIED);
        if (nullIndustry > 0) industries.add(UNCLASSIFIED);
        filterOptions = {
          sectors: [...sectors],
          industries: [...industries],
          types: clean(typeRows.map((r) => r.securityType), (v) => v),
          // Normalize the inconsistent stored values ("US" / "United States")
          // into a single canonical market CODE per market, matching what the
          // Country column renders (and what keeps `priceWithCurrency` correct),
          // so the dropdown has no duplicates and its values compare cleanly.
          countries: [...new Set(
            countryRows
              .map((r) => r.country)
              .filter((s): s is string => !!s)
              .map((s) => countryToMarketId(s))
          )].sort((a, b) => a.localeCompare(b)),
        };
        filterOptionsCache.set(cacheKey, { t: Date.now(), data: filterOptions });
      }
    }

    return NextResponse.json({
      stocks,
      indices: dash.indices,
      sectors: dash.sectors,
      shifters: dash.shifters,
      filterOptions,
      source: total > 0 ? "jdds" : "seed",
      // Seed/demo payloads are simulated — clients must label them as such.
      simulated: total === 0,
      pagination: { total, page, limit, totalPages },
    });
  } catch (err) {
    console.error("[api/stocks] Error:", err);
    // Real 5xx — clients treat any failure (or an empty payload) as a signal
    // to fall back to demo data, so this no longer masquerades as success.
    const dash = getSimulatedDashboard(country === "CRYPTO" ? "CRYPTO" : "US");
    return NextResponse.json(
      {
        stocks: [],
        indices: dash.indices,
        sectors: dash.sectors,
        shifters: dash.shifters,
        source: "error",
        simulated: true,
        pagination: { total: 0, page: 1, limit: 0, totalPages: 0 },
      },
      { status: 500 }
    );
  }
}
