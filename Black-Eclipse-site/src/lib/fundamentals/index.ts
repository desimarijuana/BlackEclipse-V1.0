// ── Fundamentals service: Provider → Normalization → JDDS → UI ─────────────
// The single entry point the UI talks to. `fundamentals.get(symbol, market)`
// resolves configured providers in authority order, merges complementary data
// (SEC statements + FMP/Yahoo multiples), normalizes into the Eclipse schema,
// derives metrics/insights, and persists the result to JDDS.
//
// Caching: an in-memory map fronts the `FundamentalsCache` table. A fresh cache
// is served directly; a stale cache is served immediately while a background
// refresh runs (stale-while-revalidate), so the page never blocks on providers.

import { prisma } from '@/lib/db';
import { configuredProviders } from './providers';
import { normalizePeriods } from './normalize';
import { assembleSnapshot, buildGrowth, type AssembleInputs } from './compute';
import type {
  CompanyProfile,
  EarningsEntry,
  FundamentalMetric,
  FundamentalProviderId,
  FundamentalsProvider,
  FundamentalsProvenance,
  FundamentalsSnapshot,
  GrowthSeries,
  MetricSource,
  OwnershipSnapshot,
  ProviderFundamentals,
  QuoteSnapshot,
  TimelineEntry,
  ValuationInputs,
} from './types';

export const CACHE_TTL_MS = 24 * 60 * 60 * 1000; // statements change quarterly
export const STALE_SERVE_MS = 7 * 24 * 60 * 60 * 1000; // beyond this, refresh hard

interface CacheRecord {
  payload: string;
  fetchedAt: string;
}

// ── Raw provider fetch (no cache) ────────────────────────────────────────────

async function fetchProviders(
  symbol: string,
  market: string
): Promise<{ results: ProviderFundamentals[]; attempted: FundamentalProviderId[] }> {
  const providers = await configuredProviders(symbol, market);
  const attempted = providers.map((p) => p.id);
  if (providers.length === 0) return { results: [], attempted };

  // Query in parallel — SEC/Yahoo/FMP are independent. Each provider returns
  // null on failure rather than throwing, so one outage never blanks the page.
  const settled = await Promise.all(
    providers.map(async (p) => {
      try {
        return await p.fetch(symbol, market);
      } catch {
        return null;
      }
    })
  );
  // Keep any provider that returned a usable signal. Funds/ETFs legitimately
  // have no financial statements but do have a profile and valuation multiples,
  // and showing that is more honest than a blank UNAVAILABLE.
  const hasSignal = (r: ProviderFundamentals): boolean =>
    r.periods.length > 0 ||
    Boolean(r.company?.name) ||
    Boolean(r.quote?.marketCap) ||
    Boolean(r.valuation && Object.values(r.valuation).some((v) => typeof v === 'number'));
  return {
    results: settled.filter((r): r is ProviderFundamentals => r !== null && hasSignal(r)),
    attempted,
  };
}

// ── Merge complementary provider outputs into one Eclipse snapshot ──────────

const EMPTY_VALUATION: ValuationInputs = {
  trailingPE: null,
  forwardPE: null,
  peg: null,
  priceToSales: null,
  priceToBook: null,
  evToEbitda: null,
  evToRevenue: null,
  fcfYield: null,
  dividendYield: null,
  dividendRate: null,
  payoutRatio: null,
  trailingEps: null,
  forwardEps: null,
};

function mergeCompany(parts: Array<Partial<CompanyProfile>>): CompanyProfile {
  const pick = (key: keyof CompanyProfile): string | null => {
    for (const p of parts) {
      const v = p[key];
      if (typeof v === 'string' && v.trim()) return v;
    }
    return null;
  };
  let employees: number | null = null;
  for (const p of parts) {
    if (typeof p.employees === 'number' && Number.isFinite(p.employees)) {
      employees = p.employees;
      break;
    }
  }
  let leadership: CompanyProfile['leadership'] = [];
  for (const p of parts) {
    if (Array.isArray(p.leadership) && p.leadership.length > 0) {
      leadership = p.leadership;
      break;
    }
  }
  return {
    name: pick('name'),
    sector: pick('sector'),
    industry: pick('industry'),
    country: pick('country'),
    website: pick('website'),
    description: pick('description'),
    employees,
    exchange: pick('exchange'),
    leadership,
  };
}

function mergeQuote(parts: Array<Partial<QuoteSnapshot> | null | undefined>): QuoteSnapshot | null {
  const merged: QuoteSnapshot = {
    price: null,
    previousClose: null,
    marketCap: null,
    enterpriseValue: null,
    sharesOutstanding: null,
    beta: null,
    fiftyTwoWeekHigh: null,
    fiftyTwoWeekLow: null,
    source: 'derived',
    updatedAt: null,
  };
  let any = false;
  for (const p of parts) {
    if (!p) continue;
    for (const key of [
      'price',
      'previousClose',
      'marketCap',
      'enterpriseValue',
      'sharesOutstanding',
      'beta',
      'fiftyTwoWeekHigh',
      'fiftyTwoWeekLow',
    ] as const) {
      if (merged[key] === null && typeof p[key] === 'number' && Number.isFinite(p[key])) {
        (merged[key] as number | null) = p[key] as number;
        any = true;
        if (p.source) merged.source = p.source;
      }
    }
  }
  return any ? merged : null;
}

function mergeValuation(results: ProviderFundamentals[]): {
  valuation: ValuationInputs;
  source: MetricSource;
} {
  const merged: ValuationInputs = { ...EMPTY_VALUATION };
  let source: MetricSource = 'derived';
  for (const result of results) {
    const p = result.valuation;
    if (!p) continue;
    for (const key of Object.keys(EMPTY_VALUATION) as Array<keyof ValuationInputs>) {
      if (merged[key] === null && typeof p[key] === 'number' && Number.isFinite(p[key])) {
        merged[key] = p[key] as number;
        // The valuation provider is carried alongside the inputs so metric
        // source labels stay honest (provider-reported vs derived).
        if (source === 'derived') source = result.provider;
      }
    }
  }
  return { valuation: merged, source };
}

function mergeOwnership(parts: Array<Partial<OwnershipSnapshot> | null | undefined>): OwnershipSnapshot | null {
  const merged: OwnershipSnapshot = {
    institutionalPercent: null,
    insiderPercent: null,
    shortPercentOfFloat: null,
    sharesShort: null,
    floatShares: null,
    source: 'derived',
  };
  let any = false;
  for (const p of parts) {
    if (!p) continue;
    for (const key of [
      'institutionalPercent',
      'insiderPercent',
      'shortPercentOfFloat',
      'sharesShort',
      'floatShares',
    ] as const) {
      if (merged[key] === null && typeof p[key] === 'number' && Number.isFinite(p[key])) {
        merged[key] = p[key] as number;
        any = true;
        if (p.source) merged.source = p.source;
      }
    }
  }
  return any ? merged : null;
}

function mergeEarnings(parts: ProviderFundamentals[]): { history: EarningsEntry[]; estimates: EarningsEntry[] } {
  const historyByDate = new Map<string, EarningsEntry>();
  const estimatesByDate = new Map<string, EarningsEntry>();
  for (const p of parts) {
    if (!p.earnings) continue;
    for (const row of p.earnings.history) {
      if (row.date) historyByDate.set(row.date, row);
    }
    for (const row of p.earnings.estimates) {
      if (row.date) estimatesByDate.set(row.date, row);
    }
  }
  const byDate = (a: EarningsEntry, b: EarningsEntry) => a.date.localeCompare(b.date);
  return {
    history: [...historyByDate.values()].sort(byDate),
    estimates: [...estimatesByDate.values()].sort(byDate),
  };
}

function mergeTimeline(parts: ProviderFundamentals[]): TimelineEntry[] {
  const seen = new Set<string>();
  const out: TimelineEntry[] = [];
  for (const p of parts) {
    for (const entry of p.timeline ?? []) {
      const key = `${entry.date}:${entry.label}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(entry);
    }
  }
  return out.sort((a, b) => b.date.localeCompare(a.date));
}

// ── Public snapshot assembly ────────────────────────────────────────────────

export function buildSnapshot(
  symbol: string,
  market: string,
  results: ProviderFundamentals[],
  provenance: FundamentalsProvenance
): FundamentalsSnapshot | null {
  if (results.length === 0) return null;

  // Statement source = first provider that returned actual periods; fall back
  // to the first provider with any signal (e.g. an ETF with profile only).
  const primary = results.find((r) => r.periods.length > 0) ?? results[0];
  const periods = normalizePeriods(primary);
  const growth: GrowthSeries = buildGrowth(periods);

  const quote = mergeQuote(results.map((r) => r.quote));
  const { valuation, source: valuationSource } = mergeValuation(results);
  const ownership = mergeOwnership(results.map((r) => r.ownership));
  const earnings = mergeEarnings(results);
  const timeline = mergeTimeline(results);
  const company = mergeCompany(results.map((r) => r.company));
  const currency = results.map((r) => r.currency).find((c) => c) ?? null;
  const latestPeriod = periods[periods.length - 1];
  const fiscalYearEnd = latestPeriod?.endDate ?? null;

  const contributors: MetricSource[] = [...new Set(results.map((r) => r.provider as MetricSource))];
  const primarySource: MetricSource = primary.provider;

  const input: AssembleInputs = {
    symbol,
    market,
    currency,
    company,
    periods,
    growth,
    quote,
    valuation,
    valuationSource,
    earnings,
    ownership,
    timeline,
    primary: primarySource,
    contributors,
    provenance,
    retrievedAt: new Date().toISOString(),
    fiscalYearEnd,
  };
  return assembleSnapshot(input);
}

// ── Cache layer ─────────────────────────────────────────────────────────────

const memoryCache = new Map<string, CacheRecord>();
const refreshing = new Set<string>();

function cacheKeyOf(symbol: string, market: string): string {
  return `${market}:${symbol}`.toUpperCase();
}

async function readCache(symbol: string, market: string): Promise<CacheRecord | null> {
  const key = cacheKeyOf(symbol, market);
  const mem = memoryCache.get(key);
  if (mem) return mem;
  try {
    const row = await prisma.fundamentalsCache.findUnique({
      where: { symbol_market: { symbol: symbol.toUpperCase(), market } },
    });
    if (!row) return null;
    const record: CacheRecord = { payload: row.payload, fetchedAt: row.fetchedAt.toISOString() };
    memoryCache.set(key, record);
    return record;
  } catch {
    return null;
  }
}

async function writeCache(symbol: string, market: string, snapshot: FundamentalsSnapshot): Promise<void> {
  const payload = JSON.stringify(snapshot);
  const record: CacheRecord = { payload, fetchedAt: snapshot.retrievedAt };
  memoryCache.set(cacheKeyOf(symbol, market), record);
  try {
    await prisma.fundamentalsCache.upsert({
      where: { symbol_market: { symbol: symbol.toUpperCase(), market } },
      update: {
        primarySource: String(snapshot.primarySource),
        payload,
        fetchedAt: new Date(snapshot.retrievedAt),
      },
      create: {
        symbol: symbol.toUpperCase(),
        market,
        primarySource: String(snapshot.primarySource),
        payload,
        fetchedAt: new Date(snapshot.retrievedAt),
      },
    });
  } catch {
    /* cache write failure must never fail the request */
  }
}

/**
 * Refresh from providers and persist. Concurrent callers for the same symbol
 * share one in-flight fetch. Returns the new snapshot, or the stale cache when
 * every provider fails (never blanks a previously good page).
 */
async function refresh(symbol: string, market: string): Promise<FundamentalsSnapshot | null> {
  const key = cacheKeyOf(symbol, market);
  if (refreshing.has(key)) {
    const cached = await readCache(symbol, market);
    return cached ? (JSON.parse(cached.payload) as FundamentalsSnapshot) : null;
  }
  refreshing.add(key);
  try {
    const { results } = await fetchProviders(symbol, market);
    if (results.length === 0) {
      const cached = await readCache(symbol, market);
      return cached ? withProvenance(cached.payload, 'CACHED') : null;
    }
    const snapshot = buildSnapshot(symbol, market, results, 'LIVE');
    if (!snapshot) {
      const cached = await readCache(symbol, market);
      return cached ? withProvenance(cached.payload, 'CACHED') : null;
    }
    await writeCache(symbol, market, snapshot);
    return snapshot;
  } finally {
    refreshing.delete(key);
  }
}

function withProvenance(payload: string, provenance: FundamentalsProvenance): FundamentalsSnapshot {
  const parsed = JSON.parse(payload) as FundamentalsSnapshot;
  return { ...parsed, provenance };
}

export interface GetOptions {
  /** Force a provider refresh, ignoring a fresh cache. */
  force?: boolean;
}

/**
 * Provider → Normalization → JDDS → UI entry point.
 *
 * - Fresh cache           → CACHED snapshot (no provider calls).
 * - Stale cache           → returns stale now, refreshes in the background.
 * - No cache              → fetches providers; UNAVAILABLE when none can serve.
 */
export async function getFundamentals(
  rawSymbol: string,
  rawMarket = 'US',
  options: GetOptions = {}
): Promise<FundamentalsSnapshot | null> {
  const symbol = rawSymbol.trim().toUpperCase();
  const market = rawMarket.trim().toUpperCase();
  if (!symbol) return null;

  const cached = options.force ? null : await readCache(symbol, market);
  if (cached) {
    const age = Date.now() - Date.parse(cached.fetchedAt);
    if (Number.isFinite(age) && age < CACHE_TTL_MS) {
      return { ...withProvenance(cached.payload, 'CACHED'), retrievedAt: cached.fetchedAt };
    }
    // Stale: serve immediately, revalidate in the background. A very old entry
    // blocks so the user does not see years-old data as if it were current.
    if (Number.isFinite(age) && age < STALE_SERVE_MS) {
      void refresh(symbol, market).catch(() => undefined);
      return { ...withProvenance(cached.payload, 'CACHED'), retrievedAt: cached.fetchedAt };
    }
  }

  return refresh(symbol, market);
}

/** Test/ops seam: drop the in-process cache for one symbol (or all). */
export function __clearFundamentalsMemoryCache(symbol?: string, market?: string): void {
  if (symbol && market) memoryCache.delete(cacheKeyOf(symbol, market));
  else memoryCache.clear();
}

export type { FundamentalsSnapshot, FundamentalMetric };
export type { FundamentalsProvider };
