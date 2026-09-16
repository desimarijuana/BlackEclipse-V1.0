// ── Investor Eye — Phase 2 server data assembly ──────────────────────────────
// Reuses EXISTING infrastructure for every input:
//   - economic metrics: `ECON_SOURCES` / snapshot fetch layer
//   - companies: the JDDS `Asset` universe (+ `Price`)
//   - portfolio: caller-supplied holdings (client engine owns the math)
//   - historical series: JDDS `Price` / `Candles`
//
// This module never fabricates a value. A missing series/metric is omitted, and
// the caller renders UNAVAILABLE.

import { prisma } from '@/lib/db';
import { countryByIso2, COUNTRIES, resolveCountry } from './countries';
import type { CompanyPoint, EconomicLayerData, NormalizedEvent } from './types';

/**
 * Curated, free, keyless economic metrics sourced from the FRED public CSV
 * mirror (the same transport `lib/economics/sources.ts` already uses). Kept
 * small and honest: only metrics the public CSV actually serves.
 */
export const ECONOMIC_METRICS: Array<{ id: string; label: string; unit: string; fredId: string; transform?: 'yoy' }> = [
  { id: 'inflation', label: 'Inflation (YoY)', unit: '%', fredId: 'CPIAUCSL', transform: 'yoy' },
  { id: 'unemployment', label: 'Unemployment', unit: '%', fredId: 'UNRATE' },
  { id: 'gdp', label: 'Real GDP (YoY)', unit: '%', fredId: 'GDPC1', transform: 'yoy' },
  { id: 'rate', label: 'Policy Rate', unit: '%', fredId: 'DFF' },
  { id: 'yield10y', label: '10Y Yield', unit: '%', fredId: 'DGS10' },
  { id: 'money', label: 'M2 Money Supply', unit: '', fredId: 'M2SL' },
];

/**
 * Per-country FRED series for the curated metrics (free CSV).
 * IMPORTANT: whether a `yoy` transform is needed is a property of the SERIES,
 * not the metric. `CPIAUCSL` is a price INDEX (needs yoy); the `CPALTT01*`
 * OECD harmonized series are ALREADY year-over-year percent changes, so
 * transforming them again produces garbage. A series with no explicit
 * `transform` is read as its level/last value.
 */
interface CountrySeries { id: string; transform?: 'yoy' }
type MetricMap = Partial<Record<string, CountrySeries>>;

const COUNTRY_SERIES: Record<string, MetricMap> = {
  US: {
    inflation: { id: 'CPIAUCSL', transform: 'yoy' },
    unemployment: { id: 'UNRATE' },
    gdp: { id: 'GDPC1', transform: 'yoy' },
    rate: { id: 'DFF' },
    yield10y: { id: 'DGS10' },
    money: { id: 'M2SL' },
  },
  GB: { inflation: { id: 'CPALTT01GBM659N' }, unemployment: { id: 'LRUN64TTGBQ156S' } },
  DE: { inflation: { id: 'CPALTT01DEM659N' }, unemployment: { id: 'LRHUTTTTDEM156S' } },
  FR: { inflation: { id: 'CPALTT01FRM659N' }, unemployment: { id: 'LRHUTTTTFRM156S' } },
  JP: { inflation: { id: 'CPALTT01JPM659N' }, unemployment: { id: 'LRUN64TTJPM156S' } },
  CN: { inflation: { id: 'CPALTT01CNM659N' } },
  IN: { inflation: { id: 'CPALTT01INM659N' }, unemployment: { id: 'LRUN64TTINQ156S' } },
  PK: { inflation: { id: 'CPALTT01PKM659N' } },
  CA: { inflation: { id: 'CPALTT01CAM659N' }, unemployment: { id: 'LRUN64TTCAQ156S' } },
  BR: { inflation: { id: 'CPALTT01BRM659N' } },
  AU: { inflation: { id: 'CPALTT01AUM659N' } },
  KR: { inflation: { id: 'CPALTT01KRM659N' } },
  MX: { inflation: { id: 'CPALTT01MXM659N' } },
  ZA: { inflation: { id: 'CPALTT01ZAM659N' } },
  TR: { inflation: { id: 'CPALTT01TRM659N' } },
  SA: { inflation: { id: 'CPALTT01SAM659N' } },
  ID: { inflation: { id: 'CPALTT01IDM659N' } },
};

async function fredLatestYoy(seriesId: string, transform: 'yoy' | undefined): Promise<number | null> {
  try {
    const res = await fetch(`https://fred.stlouisfed.org/graph/fredgraph.csv?id=${seriesId}`, {
      signal: AbortSignal.timeout(15_000),
    });
    if (!res.ok) return null;
    const csv = await res.text();
    const points: number[] = [];
    for (const line of csv.trim().split('\n').slice(1)) {
      const [, raw] = line.split(',');
      const v = Number((raw ?? '').trim());
      if (Number.isFinite(v)) points.push(v);
    }
    if (points.length === 0) return null;
    if (transform === 'yoy') {
      if (points.length < 13) return null;
      const last = points[points.length - 1];
      const prev = points[points.length - 13];
      if (!prev) return null;
      return Number((((last - prev) / prev) * 100).toFixed(2));
    }
    return Number(points[points.length - 1].toFixed(2));
  } catch {
    return null;
  }
}

/**
 * Fetch one metric across the covered countries. Runs sequentially to avoid
 * hammering the public mirror; the whole route is cached server-side.
 */
export async function buildEconomicLayer(metricId: string): Promise<EconomicLayerData> {
  const metric = ECONOMIC_METRICS.find((m) => m.id === metricId) ?? ECONOMIC_METRICS[0];
  const values: Record<string, number> = {};
  for (const [iso2, seriesMap] of Object.entries(COUNTRY_SERIES)) {
    const series = seriesMap[metric.id];
    if (!series) continue;
    const value = await fredLatestYoy(series.id, series.transform);
    if (value !== null) values[iso2] = value;
  }
  return {
    metricId: metric.id,
    metricLabel: metric.label,
    unit: metric.unit,
    values,
    provenance: Object.keys(values).length > 0 ? 'LIVE' : 'UNAVAILABLE',
  };
}

// ── Companies (reuse the JDDS Asset universe) ────────────────────────────────

export interface CompanyRow extends CompanyPoint {
  marketCap?: number;
  lon: number;
  lat: number;
}

/**
 * Companies with a resolvable HQ country and therefore a map position. Uses
 * `Asset.country` first, then falls back to the market's country. Never
 * invents a country — a company without one is omitted from the layer.
 */
export async function buildCompanies(limit = 250): Promise<CompanyRow[]> {
  const rows = await prisma.asset.findMany({
    where: { isActive: true, price: { isNot: null } },
    select: {
      symbol: true, name: true, country: true, sector: true, marketId: true,
      price: { select: { changePct: true, marketCap: true } },
    },
    orderBy: { price: { marketCap: 'desc' } },
    take: limit,
  });

  const out: CompanyRow[] = [];
  for (const r of rows) {
    // Resolve an ISO2: Asset.country may already be a code or a name.
    let def = countryByIso2(r.country);
    if (!def && r.country) def = resolveCountry(r.country);
    if (!def) def = countryByIso2(r.marketId);
    if (!def) continue;
    if (def.lon == null || def.lat == null) continue;
    out.push({
      symbol: r.symbol,
      name: r.name,
      iso2: def.iso2,
      sector: r.sector ?? undefined,
      changePct: r.price?.changePct,
      marketCap: r.price?.marketCap ?? undefined,
      lon: def.lon,
      lat: def.lat,
    });
  }
  return out;
}

// ── Historical series (reuse JDDS) ───────────────────────────────────────────

/**
 * Real stored price series for a symbol, from `Candles` (preferred) or `Price`.
 * Returns [] when there is no history — the analogues view then shows
 * UNAVAILABLE rather than a synthetic curve.
 */
export async function loadPriceHistory(symbol: string, days = 365 * 2): Promise<Array<{ date: string; value: number }>> {
  const since = new Date(Date.now() - days * 24 * 60 * 60 * 1000);
  try {
    const candles = await prisma.candles.findMany({
      // Pin the timeframe: the cache is keyed by (symbol, timeframe, ts), so an
      // unfiltered read would interleave intraday and daily bars into one series.
      where: { symbol, timeframe: '1d', ts: { gte: since } },
      orderBy: { ts: 'asc' },
      select: { ts: true, c: true },
      take: 5000,
    });
    if (candles.length > 0) {
      return candles.map((c) => ({ date: c.ts.toISOString().slice(0, 10), value: c.c }));
    }
  } catch {
    /* fall through to Price */
  }
  return [];
}

/** Prior events of the same type, used to find historical analogue periods. */
export async function loadPriorEventsOfType(eventType: string, months = 36): Promise<NormalizedEvent[]> {
  const since = new Date(Date.now() - months * 30 * 24 * 60 * 60 * 1000);
  const rows = await prisma.geopoliticalEvent.findMany({
    where: { eventType, publishedAt: { gte: since } },
    orderBy: { publishedAt: 'desc' },
    take: 500,
  });
  return rows.map((r) => ({
    id: r.id,
    dedupKey: r.dedupKey,
    title: r.title,
    eventType: r.eventType as NormalizedEvent['eventType'],
    severity: r.severity as NormalizedEvent['severity'],
    channels: [], commodities: [], sectors: [], securities: [],
    countries: (() => { try { return JSON.parse(r.countries); } catch { return []; } })(),
    confidence: r.confidence,
    sourceCount: r.sourceCount,
    sources: [],
    primarySource: r.primarySource,
    publishedAt: r.publishedAt.toISOString(),
  }));
}

/** Country detail for the intelligence panel: real metrics only. */
export async function buildCountryDetail(iso2: string): Promise<{
  iso2: string;
  name: string;
  region?: string;
  metrics: Array<{ id: string; label: string; value: number; unit: string; asOf: string | null }>;
  provenance: 'LIVE' | 'UNAVAILABLE';
}> {
  const def = countryByIso2(iso2) ?? COUNTRIES.find((c) => c.iso2 === iso2.toUpperCase());
  if (!def) {
    return { iso2, name: iso2, metrics: [], provenance: 'UNAVAILABLE' };
  }
  const seriesMap = COUNTRY_SERIES[def.iso2] ?? {};
  const metrics: Array<{ id: string; label: string; value: number; unit: string; asOf: string | null }> = [];
  for (const metric of ECONOMIC_METRICS) {
    const series = seriesMap[metric.id];
    if (!series) continue;
    const value = await fredLatestYoy(series.id, series.transform);
    if (value === null) continue;
    metrics.push({ id: metric.id, label: metric.label, value, unit: metric.unit, asOf: null });
  }
  return {
    iso2: def.iso2,
    name: def.name,
    region: def.region,
    metrics,
    provenance: metrics.length > 0 ? 'LIVE' : 'UNAVAILABLE',
  };
}
