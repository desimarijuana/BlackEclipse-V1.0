// ── Investor Eye — deterministic intelligence (Phase 2) ──────────────────────
// The "God's Eye" analysis layer. Everything here is deterministic and
// explainable: no LLM, no hidden weights. Where a relationship is inferred it
// is labelled as such, so the UI can separate:
//
//   OBSERVED      present in the data (an event named both entities)
//   HISTORICAL    computed from real stored price history
//   INFERRED      derived by an explicit, documented rule
//   AI-INTERPRETED produced by the agent layer (never by this module)
//
// See docs/investor-eye-architecture.md §5 and ADR-011.

import { severityWeight, classifyCommodities } from './classify';
import { extractCountries, countryByIso2 } from './countries';
import type {
  CountrySummary, MarketObservation, NormalizedEvent, Provenance,
} from './types';

export type RelationClass = 'OBSERVED' | 'HISTORICAL' | 'INFERRED' | 'AI-INTERPRETED';

// ── Global state (spec §40) ──────────────────────────────────────────────────

export interface RiskComponent {
  id: string;
  label: string;
  /** 0..1, higher = more stressed. */
  score: number;
  /** The evidence that produced the score (never a bare number). */
  drivers: string[];
  sampleSize: number;
}

export interface GlobalState {
  generatedAt: string;
  windowHours: number;
  regions: RegionState[];
  countries: CountrySummary[];
  activeEvents: NormalizedEvent[];
  marketState: MarketObservation[];
  riskState: RiskComponent[];
  provenance: Provenance;
}

export interface RegionState {
  region: string;
  eventCount: number;
  avgSeverity: number;
  topType: string | null;
}

export function buildRegionState(events: NormalizedEvent[], countries: CountrySummary[]): RegionState[] {
  const regionByIso = new Map(countries.map((c) => [c.iso2, c.region ?? 'Unknown']));
  const byRegion = new Map<string, { count: number; sevSum: number; types: Map<string, number> }>();
  for (const e of events) {
    const regions = new Set(e.countries.map((iso) => regionByIso.get(iso) ?? 'Unknown'));
    for (const region of regions) {
      const cur = byRegion.get(region) ?? { count: 0, sevSum: 0, types: new Map() };
      cur.count++;
      cur.sevSum += severityWeight(e.severity);
      cur.types.set(e.eventType, (cur.types.get(e.eventType) ?? 0) + 1);
      byRegion.set(region, cur);
    }
  }
  return [...byRegion.entries()]
    .map(([region, v]) => ({
      region,
      eventCount: v.count,
      avgSeverity: v.count ? v.sevSum / v.count : 0,
      topType: [...v.types.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null,
    }))
    .sort((a, b) => b.eventCount - a.eventCount);
}

// ── Decomposable risk (spec §39) ─────────────────────────────────────────────
// No arbitrary single "risk score". Each component is independently derived
// from counts of matching events and always carries its drivers + sample size.

interface RiskSpec {
  id: string;
  label: string;
  types: string[];
  channels?: string[];
  commodities?: string[];
}

const RISK_SPECS: RiskSpec[] = [
  { id: 'conflict', label: 'Conflict Risk', types: ['conflict', 'military'] },
  { id: 'trade', label: 'Trade Risk', types: ['trade', 'tariff', 'sanction'] },
  { id: 'energy', label: 'Energy Risk', types: ['energy'], channels: ['Energy'], commodities: ['Crude Oil', 'Natural Gas'] },
  { id: 'political', label: 'Political Instability', types: ['protest', 'election', 'regulatory'] },
  { id: 'shipping', label: 'Shipping Risk', types: ['shipping'], channels: ['Shipping & Logistics'] },
  { id: 'financial', label: 'Financial Stress', types: ['monetary', 'fiscal'], channels: ['Rates & Credit', 'Currency & FX'] },
  { id: 'natural', label: 'Natural Event Risk', types: ['natural_disaster'] },
];

export function buildRiskState(events: NormalizedEvent[]): RiskComponent[] {
  const total = Math.max(1, events.length);
  return RISK_SPECS.map((spec) => {
    const matched = events.filter((e) => {
      if (spec.types.includes(e.eventType)) return true;
      if (spec.channels?.some((c) => e.channels.includes(c))) return true;
      if (spec.commodities?.some((c) => e.commodities.includes(c))) return true;
      return false;
    });
    const weighted = matched.reduce((sum, e) => sum + severityWeight(e.severity), 0);
    // Saturation: 0 events → 0; ramps with weighted count but bounded at 1.
    const raw = 1 - Math.exp(-weighted / 4);
    // Normalize by overall activity so a globally noisy day doesn't max every bar.
    const normalized = Math.min(1, raw * (0.6 + 0.4 * Math.min(1, matched.length / total + 0.2)));
    const drivers: string[] = [];
    if (matched.length === 0) drivers.push('No matching events in window');
    else {
      const byCountry = new Map<string, number>();
      for (const e of matched) for (const iso of e.countries) byCountry.set(iso, (byCountry.get(iso) ?? 0) + 1);
      const top = [...byCountry.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3);
      for (const [iso, n] of top) drivers.push(`${iso}: ${n} event${n === 1 ? '' : 's'}`);
      const crit = matched.filter((e) => e.severity === 'critical' || e.severity === 'high').length;
      if (crit > 0) drivers.push(`${crit} high/critical`);
    }
    return {
      id: spec.id,
      label: spec.label,
      score: Number(normalized.toFixed(3)),
      drivers,
      sampleSize: matched.length,
    };
  });
}

// ── Portfolio exposure (spec §35/§36) ────────────────────────────────────────
// Presented strictly as an EXPOSURE relationship, never a recommendation.
// Consumes the same holding shape the existing portfolio engine uses.

export interface HoldingLike {
  symbol: string;
  /** Fraction of portfolio value, 0..1 (or any consistent weight). */
  weight: number;
  country?: string;
  sector?: string;
}

export interface ExposureSlice {
  key: string;
  label: string;
  weight: number;
}

export interface PortfolioExposure {
  countries: ExposureSlice[];
  sectors: ExposureSlice[];
  total: number;
  unmappedWeight: number;
}

export function computeExposure(holdings: HoldingLike[]): PortfolioExposure {
  const countryMap = new Map<string, number>();
  const sectorMap = new Map<string, number>();
  let total = 0;
  let unmapped = 0;
  for (const h of holdings) {
    const w = Number.isFinite(h.weight) ? h.weight : 0;
    total += w;
    if (h.country) countryMap.set(h.country, (countryMap.get(h.country) ?? 0) + w);
    else unmapped += w;
    if (h.sector) sectorMap.set(h.sector, (sectorMap.get(h.sector) ?? 0) + w);
  }
  const toSlices = (m: Map<string, number>): ExposureSlice[] =>
    [...m.entries()]
      .map(([key, weight]) => ({ key, label: key, weight }))
      .sort((a, b) => b.weight - a.weight);
  return { countries: toSlices(countryMap), sectors: toSlices(sectorMap), total, unmappedWeight: unmapped };
}

/** Events intersecting the portfolio via country / sector exposure. */
export interface PortfolioIntersection {
  event: NormalizedEvent;
  matchedCountries: string[];
  matchedSectors: string[];
  /** Share of portfolio exposed via the matched countries. */
  exposedWeight: number;
  relation: RelationClass;
}

export function portfolioIntersections(
  events: NormalizedEvent[],
  exposure: PortfolioExposure,
): PortfolioIntersection[] {
  const countryWeight = new Map(exposure.countries.map((c) => [c.key, c.weight]));
  const sectorWeight = new Map(exposure.sectors.map((s) => [s.key, s.weight]));
  const out: PortfolioIntersection[] = [];
  for (const e of events) {
    const matchedCountries = e.countries.filter((c) => countryWeight.has(c));
    const matchedSectors = e.sectors.filter((s) => sectorWeight.has(s));
    if (matchedCountries.length === 0 && matchedSectors.length === 0) continue;
    const exposedWeight =
      matchedCountries.reduce((sum, c) => sum + (countryWeight.get(c) ?? 0), 0) +
      matchedSectors.reduce((sum, s) => sum + (sectorWeight.get(s) ?? 0), 0);
    out.push({
      event: e,
      matchedCountries,
      matchedSectors,
      exposedWeight,
      // A holding's country/sector is stored data → OBSERVED intersection.
      relation: 'OBSERVED',
    });
  }
  return out.sort((a, b) => b.exposedWeight - a.exposedWeight || Date.parse(b.event.publishedAt) - Date.parse(a.event.publishedAt));
}

// ── Market transmission (spec §37) ───────────────────────────────────────────
// Event → entity → economic channel → asset → OBSERVED market response.
// The market step is only attached when a real observation exists for the
// asset; otherwise the link stops at the channel and is marked INFERRED.

export interface TransmissionStep {
  kind: 'event' | 'country' | 'channel' | 'asset';
  label: string;
  detail?: string;
  relation: RelationClass;
}

export interface Transmission {
  eventId: string;
  title: string;
  steps: TransmissionStep[];
  relation: RelationClass;
}

/** Map a channel to the market observations that could carry its signal. */
const CHANNEL_ASSET_MAP: Record<string, string[]> = {
  Energy: ['US'],
  'Shipping & Logistics': ['US', 'CN', 'DE', 'SG'],
  'Trade & Tariffs': ['CN', 'US', 'DE', 'JP', 'KR'],
  Semiconductors: ['TW', 'KR', 'US'],
  'Rates & Credit': ['US'],
  'Currency & FX': ['US'],
  'Metals & Mining': ['AU', 'ZA', 'CA'],
  Agriculture: ['BR', 'US'],
  'Financial Markets': ['US'],
  'Technology': ['US', 'TW', 'KR'],
  'Defense & Aerospace': ['US'],
};

export function buildTransmissions(
  events: NormalizedEvent[],
  markets: MarketObservation[],
  limit = 12,
): Transmission[] {
  const byIso = new Map<string, MarketObservation>();
  for (const m of markets) if (m.iso2 && !byIso.has(m.iso2)) byIso.set(m.iso2, m);

  const scored = events
    .map((e) => ({ e, score: severityWeight(e.severity) + e.channels.length * 0.1 }))
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);

  return scored.map(({ e }) => {
    const steps: TransmissionStep[] = [];
    steps.push({ kind: 'event', label: e.title, relation: 'OBSERVED' });
    const country = e.countries[0];
    if (country) steps.push({ kind: 'country', label: country, detail: 'primary country', relation: 'OBSERVED' });

    // Channels are word-derived relevance, not causation → INFERRED.
    for (const ch of e.channels.slice(0, 2)) {
      steps.push({ kind: 'channel', label: ch, relation: 'INFERRED' });
      const candidateIsos = CHANNEL_ASSET_MAP[ch] ?? [];
      for (const iso of candidateIsos) {
        const obs = byIso.get(iso);
        if (!obs) continue;
        steps.push({
          kind: 'asset',
          label: `${obs.symbol} (${obs.name})`,
          detail: `${obs.changePct >= 0 ? '+' : ''}${obs.changePct.toFixed(2)}%`,
          // The market print is real (OBSERVED); the CHANNEL→asset link is INFERRED.
          relation: 'OBSERVED',
        });
        break; // one representative asset per channel keeps the graph readable
      }
    }
    const hasInferred = steps.some((s) => s.relation === 'INFERRED');
    return { eventId: e.id ?? e.dedupKey, title: e.title, steps, relation: hasInferred ? 'INFERRED' : 'OBSERVED' };
  });
}

// ── Historical analogues (spec §38) ──────────────────────────────────────────
// Honest: this returns the analogue *candidates* and the actual stored close
// series for the asset class, with sample size + date range. It never converts
// a past move into a prediction.

export interface HistoricalAnalogues {
  eventId: string;
  eventType: string;
  /** Prior years in which events of the same type clustered. */
  analoguePeriods: Array<{ label: string; eventCount: number }>;
  /** Real stored market series supplied by the caller (never synthesized). */
  series?: Array<{ date: string; value: number }>;
  seriesLabel?: string;
  sampleSize: number;
  dateRange: { from: string; to: string } | null;
  availability: Provenance;
  disclaimer: string;
}

const DISCLAIMER =
  'Historical relationships are descriptive, not predictive. Sample sizes and data availability are shown; missing data is marked unavailable.';

export function buildAnalogues(
  target: NormalizedEvent,
  priorEventsOfType: NormalizedEvent[],
  series?: Array<{ date: string; value: number }>,
  seriesLabel?: string,
): HistoricalAnalogues {
  const byYear = new Map<string, number>();
  for (const e of priorEventsOfType) {
    const year = e.publishedAt.slice(0, 4);
    byYear.set(year, (byYear.get(year) ?? 0) + 1);
  }
  const analoguePeriods = [...byYear.entries()]
    .map(([label, eventCount]) => ({ label, eventCount }))
    .sort((a, b) => a.label.localeCompare(b.label));

  const dates = (series ?? []).map((p) => p.date).filter(Boolean).sort();
  const dateRange = dates.length > 0 ? { from: dates[0], to: dates[dates.length - 1] } : null;
  return {
    eventId: target.id ?? target.dedupKey,
    eventType: target.eventType,
    analoguePeriods,
    series,
    seriesLabel,
    sampleSize: priorEventsOfType.length,
    dateRange,
    availability: series && series.length > 0 ? 'HISTORICAL' : 'UNAVAILABLE',
    disclaimer: DISCLAIMER,
  };
}

// ── Global state assembly ────────────────────────────────────────────────────

export function buildGlobalState(
  events: NormalizedEvent[],
  countries: CountrySummary[],
  markets: MarketObservation[],
  provenance: Provenance,
  windowHours: number,
): GlobalState {
  return {
    generatedAt: new Date().toISOString(),
    windowHours,
    regions: buildRegionState(events, countries),
    countries,
    activeEvents: events,
    marketState: markets,
    riskState: buildRiskState(events),
    provenance,
  };
}

/** Deterministic natural-language intent → layer/filter plan (spec §43). */
export interface QueryPlan {
  query: string;
  activateLayers: string[];
  eventTypes: string[];
  commodities: string[];
  countries: string[];
  explanation: string;
}

const LAYER_KEYWORDS: Array<{ layer: string; words: string[] }> = [
  { layer: 'energy', words: ['oil', 'gas', 'energy', 'opec', 'crude', 'lng', 'pipeline'] },
  { layer: 'trade', words: ['trade', 'tariff', 'tariffs', 'export', 'import', 'shipping', 'freight'] },
  { layer: 'conflict', words: ['conflict', 'war', 'military', 'sanction', 'attack', 'defense'] },
  { layer: 'economy', words: ['economy', 'inflation', 'gdp', 'rates', 'macro', 'recession'] },
  { layer: 'weather', words: ['earthquake', 'weather', 'storm', 'flood', 'disaster', 'hurricane'] },
  { layer: 'companies', words: ['compan', 'sector', 'stocks', 'equities', 'semiconductor'] },
];

const TYPE_KEYWORDS: Array<{ type: string; words: string[] }> = [
  { type: 'conflict', words: ['conflict', 'war', 'attack'] },
  { type: 'military', words: ['military', 'troops', 'drill'] },
  { type: 'sanction', words: ['sanction'] },
  { type: 'trade', words: ['trade'] },
  { type: 'tariff', words: ['tariff'] },
  { type: 'energy', words: ['oil', 'gas', 'energy', 'opec'] },
  { type: 'shipping', words: ['shipping', 'freight', 'red sea'] },
  { type: 'monetary', words: ['inflation', 'rates', 'central bank', 'fed'] },
  { type: 'natural_disaster', words: ['earthquake', 'flood', 'hurricane', 'disaster'] },
];

export function planQuery(raw: string): QueryPlan {
  const q = raw.trim().toLowerCase();
  const activateLayers = new Set<string>(['events']);
  const eventTypes = new Set<string>();
  const commodities = classifyCommodities(q);
  const countries = extractCountries(q).map((c) => c.iso2);

  for (const { layer, words } of LAYER_KEYWORDS) {
    if (words.some((w) => q.includes(w))) activateLayers.add(layer);
  }
  for (const { type, words } of TYPE_KEYWORDS) {
    if (words.some((w) => q.includes(w))) eventTypes.add(type);
  }
  if (countries.length > 0 || q.includes('world')) activateLayers.add('markets');

  const parts: string[] = [];
  if (activateLayers.size > 1) parts.push(`layers: ${[...activateLayers].join(', ')}`);
  if (eventTypes.size > 0) parts.push(`event types: ${[...eventTypes].join(', ')}`);
  if (commodities.length > 0) parts.push(`commodities: ${commodities.join(', ')}`);
  if (countries.length > 0) parts.push(`countries: ${countries.map((c) => countryByIso2(c)?.name ?? c).join(', ')}`);

  return {
    query: raw,
    activateLayers: [...activateLayers],
    eventTypes: [...eventTypes],
    commodities,
    countries,
    explanation: parts.length > 0 ? `Activated ${parts.join(' · ')}` : 'No specific filters detected — showing all events.',
  };
}

/**
 * Rank events against a plan (used to highlight matches from NL search).
 * Severity is only a TIE-BREAKER: an event must actually match a type, country
 * or commodity to score above zero, otherwise every event would "match" a
 * broad query and the highlight would be meaningless.
 */
export function scoreEventAgainstPlan(event: NormalizedEvent, plan: QueryPlan): number {
  let score = 0;
  if (plan.eventTypes.includes(event.eventType)) score += 3;
  if (plan.countries.some((c) => event.countries.includes(c))) score += 2;
  if (plan.commodities.some((c) => event.commodities.includes(c))) score += 2;
  if (score === 0) return 0;
  return score + severityWeight(event.severity) * 0.5;
}

export { severityWeight };
