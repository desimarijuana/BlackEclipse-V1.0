// ── Investor Eye — layer builders ────────────────────────────────────────────
// Pure functions that turn world state into `MapLayer[]`. The map component
// renders whatever it is handed; all business logic lives here and in
// `analytics.ts`, never in the visualization.
//
// Phase 1 activates `events` + `markets`. Phase 2 registers the rest through
// the same `registerLayer()` mechanism, so adding a layer never rewrites the
// map (spec §60).

import { aggregatePoints, zoomForCount } from './geo';
import { severityWeight } from './classify';
import { formatUtc } from './format';
import { GEO_METHOD_LABEL } from './geo-resolve';
import type {
  CompanyPoint, CountrySummary, EventSeverity, InvestorEyeState, LayerDatum, MapLayer,
  MarketObservation, NormalizedEvent, TooltipContent,
} from './types';

/** Every layer id the app knows about, in controller order. */
export const ALL_LAYER_IDS = [
  'events', 'markets', 'conflict', 'shipping', 'trade', 'energy', 'commodities',
  'economy', 'weather', 'fires', 'companies', 'risk', 'portfolio',
] as const;
export type LayerId = (typeof ALL_LAYER_IDS)[number];

/**
 * Intelligence groups. Layers are colour-coded by group so a dense controller
 * strip (and the map legend) communicates "what is what" without reading every
 * label. Groups describe the *kind of data* a layer draws — they are not a
 * claim about the data's meaning.
 */
export const LAYER_GROUPS = [
  { id: 'events', name: 'Events', color: '#38bdf8' },
  { id: 'hazards', name: 'Hazards', color: '#22d3ee' },
  { id: 'flows', name: 'Energy & Trade', color: '#fb923c' },
  { id: 'economy', name: 'Economy', color: '#a78bfa' },
  { id: 'markets', name: 'Markets', color: '#34d399' },
] as const;

export type LayerGroupId = (typeof LAYER_GROUPS)[number]['id'];

/**
 * Marker shape per layer, so event categories are distinguishable without
 * relying on colour alone (spec §8 / §34). Rendered in the legend and passed to
 * the map adapter where the series type supports it.
 */
export type LayerSymbol = 'circle' | 'diamond' | 'triangle' | 'square' | 'ring';
export interface LayerMeta {
  name: string;
  phase: 1 | 2;
  group: LayerGroupId;
  /** Per-layer accent (falls back to the group colour when absent). */
  color: string;
  /** Only meaningful for point layers. */
  symbol?: LayerSymbol;
  /** One-line description of what the layer draws, shown in tooltips. */
  hint: string;
}

export const LAYER_META: Record<LayerId, LayerMeta> = {
  events: { name: 'Events', phase: 1, group: 'events', color: '#38bdf8', symbol: 'circle', hint: 'All geolocated world events' },
  markets: { name: 'Markets', phase: 1, group: 'markets', color: '#34d399', symbol: 'circle', hint: 'Index observations by country' },
  conflict: { name: 'Conflict', phase: 2, group: 'events', color: '#ef4444', symbol: 'circle', hint: 'Conflict, military and protest events' },
  shipping: { name: 'Shipping', phase: 2, group: 'flows', color: '#0ea5e9', symbol: 'ring', hint: 'Shipping, ports, straits and supply-chain events' },
  trade: { name: 'Trade', phase: 2, group: 'flows', color: '#eab308', symbol: 'square', hint: 'Trade, tariff and sanction co-mentions' },
  energy: { name: 'Energy', phase: 2, group: 'flows', color: '#fb923c', symbol: 'diamond', hint: 'Oil, gas and power events' },
  commodities: { name: 'Commodities', phase: 2, group: 'economy', color: '#f59e0b', symbol: 'triangle', hint: 'Events naming a traded commodity' },
  economy: { name: 'Economy', phase: 2, group: 'economy', color: '#a78bfa', hint: 'Country metric fill (real series only)' },
  weather: { name: 'Earthquakes', phase: 2, group: 'hazards', color: '#22d3ee', symbol: 'triangle', hint: 'USGS seismic events' },
  fires: { name: 'Fires', phase: 2, group: 'hazards', color: '#f97316', symbol: 'diamond', hint: 'NASA FIRMS satellite fire clusters' },
  companies: { name: 'Companies', phase: 2, group: 'markets', color: '#60a5fa', symbol: 'square', hint: 'Listed companies by HQ country' },
  risk: { name: 'Risk', phase: 2, group: 'events', color: '#f472b6', hint: 'Event density per country' },
  portfolio: { name: 'Portfolio', phase: 2, group: 'markets', color: '#818cf8', symbol: 'ring', hint: 'Countries your holdings are exposed to' },
};

/** Accent for a layer: its own colour, else its group's. */
export function layerColor(id: string): string {
  return LAYER_META[id as LayerId]?.color ?? LAYER_GROUPS[0].color;
}

/** Stable group order for rendering the controller / legend. */
export function groupedLayerIds(): Array<{ group: (typeof LAYER_GROUPS)[number]; ids: LayerId[] }> {
  return LAYER_GROUPS.map((group) => ({
    group,
    ids: ALL_LAYER_IDS.filter((id) => LAYER_META[id].group === group.id),
  })).filter((g) => g.ids.length > 0);
}

const SEVERITY_COLOR: Record<EventSeverity, string> = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#38bdf8',
};

/** Severity palette + order, exported so legends and rails stay in sync. */
export const SEVERITY_COLORS = SEVERITY_COLOR;
export const SEVERITY_ORDER: EventSeverity[] = ['low', 'medium', 'high', 'critical'];

export function severityColor(severity: EventSeverity): string {
  return SEVERITY_COLOR[severity] ?? SEVERITY_COLOR.low;
}

function eventTooltip(event: NormalizedEvent): TooltipContent {
  // Defensive: a tooltip must never throw and take the whole map down with it.
  // The map is the primary interface, so a malformed datum degrades to a
  // minimal tooltip instead of a React error boundary.
  if (!event || typeof event !== 'object' || typeof event.eventType !== 'string') {
    return { title: 'Event', rows: [{ label: 'Detail', value: 'unavailable' }] };
  }
  const rows: Array<{ label: string; value: string }> = [
    { label: 'Type', value: event.eventType.replace(/_/g, ' ') },
    { label: 'Severity', value: event.severity },
  ];
  if (event.countries.length > 0) rows.push({ label: 'Countries', value: event.countries.join(', ') });
  rows.push({ label: 'First detected', value: formatUtc(event.publishedAt) });
  rows.push({ label: 'Sources', value: String(event.sourceCount) });
  if (event.relevance !== undefined) {
    rows.push({ label: 'Relevance', value: `${Math.round(event.relevance * 100)}%` });
  }
  if (event.placeName) rows.push({ label: 'Location', value: event.placeName });
  if (event.geoMethod) rows.push({ label: 'Precision', value: GEO_METHOD_LABEL[event.geoMethod] });
  if (event.channels.length > 0) rows.push({ label: 'Affected channels', value: event.channels.join(', ') });
  if (event.commodities.length > 0) rows.push({ label: 'Commodities', value: event.commodities.join(', ') });
  // Separate what is observed from what is potential.
  const why = event.relevanceReasons?.length ? `Why it matters: ${event.relevanceReasons.join(', ')}. ` : '';
  // Explain an approximate marker, so a hollow ring is never read as an exact fix.
  const geo = event.geoMethod === 'centroid'
    ? 'Location is the country centre only (shown hollow) — not a confirmed position. '
    : '';
  return {
    title: event.title,
    subtitle: event.summary,
    rows,
    note: `${geo}${why}Event and entities are observed from source data. Channels and exposure are potential, not causal.`,
  };
}

/** Events layer — aggregated when dense so the map never renders raw floods. */
export function buildEventsLayer(events: NormalizedEvent[], onSelect?: (e: NormalizedEvent) => void): MapLayer {
  const anchorable = events.filter((e) => typeof e.lon === 'number' && typeof e.lat === 'number');
  const zoom = zoomForCount(anchorable.length);
  const byId = new Map(anchorable.map((e) => [e.id ?? e.dedupKey, e]));
  const points = anchorable.map((e) => ({
    id: e.id ?? e.dedupKey,
    lon: e.lon as number,
    lat: e.lat as number,
    severity: e.severity,
    weight: severityWeight(e.severity),
    event: e,
  }));
  const clusters = aggregatePoints(points, zoom, 25);

  const data: LayerDatum[] = clusters.map((c, i) => {
    const rep = byId.get(c.members[0].id) ?? c.members[0].event;
    return {
      id: `cluster-${i}`,
      lon: c.lon,
      lat: c.lat,
      value: c.count,
      label: c.count > 1 ? `${c.count} events` : rep.title,
      severity: c.maxSeverity,
      // A single event keeps its own precision; an aggregated cell is by
      // definition approximate, so it is shown as such.
      geoMethod: c.count > 1 ? 'centroid' : rep.geoMethod,
      data: { cluster: c, representative: rep },
    };
  });

  return {
    id: 'events',
    name: 'Events',
    enabled: true,
    type: 'effect-scatter',
    zIndex: 30,
    data: () => data,
    tooltip: (datum) => {
      const payload = datum.data as { cluster: typeof clusters[number]; representative: NormalizedEvent };
      if (payload.cluster.count <= 1) return eventTooltip(payload.representative);
      return {
        title: `${payload.cluster.count} nearby events`,
        rows: [
          { label: 'Highest severity', value: payload.cluster.maxSeverity },
          { label: 'Example', value: payload.representative.title },
          { label: 'Countries', value: payload.representative.countries.join(', ') || '—' },
        ],
        note: 'Aggregated for performance. Zoom in or scrub the timeline to separate events.',
      };
    },
    onClick: (datum) => {
      const payload = datum.data as { representative: NormalizedEvent };
      onSelect?.(payload.representative);
    },
  };
}

/** Markets layer — a point per country with an index observation. */
export function buildMarketsLayer(
  markets: MarketObservation[],
  countries: CountrySummary[],
  onSelect?: (m: MarketObservation) => void,
): MapLayer {
  const countryByIso = new Map(countries.map((c) => [c.iso2, c]));
  const data: LayerDatum[] = markets.reduce<LayerDatum[]>((acc, m) => {
    const c = m.iso2 ? countryByIso.get(m.iso2) : undefined;
    if (!c || typeof c.lon !== 'number' || typeof c.lat !== 'number') return acc;
    acc.push({
      id: `market-${m.marketId}`,
      lon: c.lon,
      lat: c.lat,
      value: m.changePct,
      label: `${m.name} ${m.symbol}`,
      severity: m.changePct >= 0 ? 'low' : 'high',
      data: m,
    });
    return acc;
  }, []);

  return {
    id: 'markets',
    name: 'Markets',
    enabled: true,
    type: 'scatter',
    zIndex: 20,
    data: () => data,
    tooltip: (datum) => {
      const m = datum.data as MarketObservation;
      return {
        title: `${m.name} — ${m.symbol}`,
        rows: [
          { label: 'Last', value: `${m.price.toFixed(2)} ${m.currency ?? ''}`.trim() },
          { label: 'Change', value: `${m.changePct >= 0 ? '+' : ''}${m.changePct.toFixed(2)}%` },
          { label: 'Freshness', value: m.provenance },
        ],
        note: m.provenance === 'CACHED' ? 'Cached observation — not a live print.' : undefined,
      };
    },
    onClick: (datum) => onSelect?.(datum.data as MarketObservation),
  };
}

// ── Phase 2 layer builders ───────────────────────────────────────────────────

/**
 * Domain layers match on the event TYPE **or** the economic CHANNEL.
 *
 * WHY BOTH: `classify.ts` assigns one event type (the strongest signal) but any
 * number of channels. An event whose type is `conflict` can still carry the
 * "Shipping & Logistics" channel — a Red Sea attack, say. Matching only on type
 * hid those: measured against live data, 204 events were tagged with the
 * Shipping channel in a 24h window while only 26 were *typed* `shipping`, so the
 * layer drew 13% of the signal that existed. The same held for energy (375
 * channel-tagged vs 91 typed).
 *
 * So a domain layer is "events whose type is X **or** which transmit through
 * channel Y". That is an observed classification, not an inference — the channel
 * came from the text the source published.
 */
const CHANNEL = {
  shipping: 'Shipping & Logistics',
  energy: 'Energy',
  trade: 'Trade & Tariffs',
  rates: 'Rates & Credit',
  defense: 'Defense & Aerospace',
  metals: 'Metals & Mining',
  agriculture: 'Agriculture',
  tech: 'Technology',
} as const;

interface DomainSpec {
  id: string;
  name: string;
  types: string[];
  channels?: string[];
  /** An event must name at least one commodity to qualify. */
  requiresCommodity?: boolean;
  /** Categories this layer must never include (used to split hazards). */
  excludeCategory?: string;
  /** Scope to exactly this provider-stated category. */
  category?: string;
}

/** Conflict layer — conflict/military/protest events with severity fill. */
export function buildConflictLayer(events: NormalizedEvent[], onSelect?: (e: NormalizedEvent) => void): MapLayer {
  return buildDomainLayer({ id: 'conflict', name: 'Conflict', types: ['conflict', 'military', 'protest'], channels: [CHANNEL.defense, CHANNEL.energy] }, events, onSelect);
}

/** Shipping layer — the supply-chain domain, by type OR channel. */
export function buildShippingLayer(events: NormalizedEvent[], onSelect?: (e: NormalizedEvent) => void): MapLayer {
  return buildDomainLayer({ id: 'shipping', name: 'Shipping', types: ['shipping'], channels: [CHANNEL.shipping] }, events, onSelect);
}

/** Weather layer — natural-disaster events (USGS earthquakes, legacy rows). */
export function buildWeatherLayer(events: NormalizedEvent[], onSelect?: (e: NormalizedEvent) => void): MapLayer {
  // EXCLUDE-BY-CATEGORY rather than require `earthquake`: rows persisted before
  // the category field existed carry no category, and they must keep their
  // original layer rather than vanishing (no migration is needed for this, the
  // same reasoning as `reResolveEventLocation`).
  return buildDomainLayer({ id: 'weather', name: 'Earthquakes', types: ['natural_disaster'], excludeCategory: 'fire' }, events, onSelect);
}

/** Fires layer — NASA FIRMS satellite fire clusters (spec §21). */
export function buildFiresLayer(events: NormalizedEvent[], onSelect?: (e: NormalizedEvent) => void): MapLayer {
  return buildDomainLayer({ id: 'fires', name: 'Fires', types: ['natural_disaster'], category: 'fire' }, events, onSelect);
}

/** Energy layer — oil, gas and power, by type OR channel. */
export function buildEnergyLayer(events: NormalizedEvent[], onSelect?: (e: NormalizedEvent) => void): MapLayer {
  return buildDomainLayer({ id: 'energy', name: 'Energy', types: ['energy'], channels: [CHANNEL.energy] }, events, onSelect);
}

/**
 * Commodities layer — every event that names a traded commodity.
 *
 * This is the one layer keyed purely off the commodity extraction, so it
 * surfaces the physical-supply reading regardless of how the event was typed.
 */
export function buildCommoditiesLayer(events: NormalizedEvent[], onSelect?: (e: NormalizedEvent) => void): MapLayer {
  return buildDomainLayer({ id: 'commodities', name: 'Commodities', types: [], requiresCommodity: true }, events, onSelect);
}

function buildDomainLayer(
  spec: DomainSpec,
  events: NormalizedEvent[],
  onSelect?: (e: NormalizedEvent) => void,
): MapLayer {
  const subset = events.filter((e) => {
    if (typeof e.lon !== 'number') return false;
    if (spec.category && e.category !== spec.category) return false;
    if (spec.excludeCategory && e.category === spec.excludeCategory) return false;
    // A purely commodity-driven layer has no type/channel scope: naming a traded
    // commodity IS the membership test, whatever the event was typed as.
    if (spec.requiresCommodity) return e.commodities.length > 0;
    const typeHit = spec.types.includes(e.eventType);
    const channelHit = spec.channels?.some((c) => e.channels.includes(c)) ?? false;
    return typeHit || channelHit;
  });
  return eventsToScatterLayer(spec.id, spec.name, subset, onSelect);
}

/** Build a plain point layer from a pre-filtered event list. */
function eventsToScatterLayer(
  id: string,
  name: string,
  events: NormalizedEvent[],
  onSelect?: (e: NormalizedEvent) => void,
): MapLayer {
  const data: LayerDatum[] = events.map((e) => ({
    id: `evt-${e.id ?? e.dedupKey}`,
    lon: e.lon as number,
    lat: e.lat as number,
    value: severityWeight(e.severity),
    label: e.title,
    severity: e.severity,
    geoMethod: e.geoMethod,
    data: e,
  }));
  return {
    id,
    name,
    enabled: false,
    type: 'scatter',
    zIndex: 25,
    data: () => data,
    tooltip: (datum) => eventTooltip(datum.data as NormalizedEvent),
    // Without this the pin only showed a tooltip and a click did nothing — the
    // category layers are exactly the ones users click to ask "what is this?".
    onClick: (datum) => onSelect?.(datum.data as NormalizedEvent),
  };
}

/**
 * Trade layer — directional `lines` from a country to its top trade/reporting
 * partner among events. Only emitted when the SAME event names both endpoints,
 * so a line is an observed co-mention, never an inferred trade route.
 */
export function buildTradeLayer(
  events: NormalizedEvent[],
  countries: CountrySummary[],
  onSelect?: (e: NormalizedEvent) => void,
): MapLayer {
  const byIso = new Map(countries.map((c) => [c.iso2, c]));
  const lines: LayerDatum[] = [];
  for (const e of events) {
    // Same type-or-channel rule as the point layers: a `conflict` event that
    // names two countries and transmits through the Trade channel IS a trade
    // link, even though its type is conflict.
    const isTradeDomain =
      e.eventType === 'trade' || e.eventType === 'tariff' || e.eventType === 'shipping' ||
      e.channels.includes(CHANNEL.trade) || e.channels.includes(CHANNEL.shipping);
    if (!isTradeDomain) continue;
    if (e.countries.length < 2) continue;
    for (let i = 0; i < e.countries.length - 1; i++) {
      const a = byIso.get(e.countries[i]);
      const b = byIso.get(e.countries[i + 1]);
      if (!a || !b || a.lon == null || b.lon == null) continue;
      lines.push({
        id: `line-${e.id ?? e.dedupKey}-${i}`,
        label: e.title,
        data: {
          from: [a.lon, a.lat],
          to: [b.lon, b.lat],
          event: e,
          relation: 'OBSERVED',
        },
      });
      break; // one representative link per event keeps the layer legible
    }
  }
  return {
    id: 'trade',
    name: 'Trade',
    enabled: false,
    type: 'lines',
    zIndex: 35,
    data: () => lines,
    tooltip: (datum) => {
      const d = datum.data as { event: NormalizedEvent };
      return eventTooltip(d.event);
    },
    onClick: (datum) => {
      const d = datum.data as { event: NormalizedEvent };
      onSelect?.(d.event);
    },
  };
}

/** Economy layer — country-fill from real economic values keyed by ISO2. */
export function buildEconomyLayer(
  values: Record<string, number>,
  metricLabel: string,
): MapLayer {
  const entries = Object.entries(values).filter(([, v]) => Number.isFinite(v));
  const nums = entries.map(([, v]) => v);
  const min = nums.length ? Math.min(...nums) : 0;
  const max = nums.length ? Math.max(...nums) : 1;
  const data: LayerDatum[] = entries.map(([iso2, value]) => ({
    id: `econ-${iso2}`,
    countryIso: iso2,
    value,
    label: iso2,
    data: { metricLabel, raw: value, min, max },
  }));
  return {
    id: 'economy',
    name: 'Economy',
    enabled: false,
    type: 'country-fill',
    zIndex: 10,
    data: () => data,
    tooltip: (datum) => {
      const d = datum.data as { metricLabel: string; raw: number };
      return { title: datum.label ?? '', rows: [{ label: d.metricLabel, value: String(d.raw) }] };
    },
  };
}

/** Country event-density fill — used for the Risk layer's spatial component. */
export function buildCountryEventFill(
  countries: CountrySummary[],
  id = 'risk',
  name = 'Event Density',
  enabled = false,
): MapLayer {
  const max = Math.max(1, ...countries.map((c) => c.eventCount));
  const data: LayerDatum[] = countries
    .filter((c) => c.eventCount > 0)
    .map((c) => ({
      id: `density-${c.iso2}`,
      countryIso: c.iso2,
      value: c.eventCount / max,
      label: c.name,
      data: c,
    }));
  return {
    id,
    name,
    enabled,
    type: 'country-fill',
    zIndex: 8,
    data: () => data,
    tooltip: (datum) => {
      const c = datum.data as CountrySummary;
      return {
        title: c.name,
        rows: [
          { label: 'Events (window)', value: String(c.eventCount) },
          { label: 'Last event', value: c.lastEventAt ? formatUtc(c.lastEventAt) : '—' },
        ],
      };
    },
  };
}

/** Companies layer — JDDS companies with a resolved country centroid. */
export function buildCompaniesLayer(
  companies: CompanyPoint[],
  onSelect?: (c: CompanyPoint) => void,
): MapLayer {
  const data: LayerDatum[] = companies
    .filter((c): c is CompanyPoint & { lon: number; lat: number } => c.lon != null && c.lat != null)
    .map((c) => ({
    id: `co-${c.symbol}`,
    lon: c.lon,
    lat: c.lat,
    label: c.name,
    value: c.changePct ?? 0,
    severity: (c.changePct ?? 0) >= 0 ? 'low' : 'high',
    data: c,
  }));
  return {
    id: 'companies',
    name: 'Companies',
    enabled: false,
    type: 'scatter',
    zIndex: 28,
    data: () => data,
    tooltip: (datum) => {
      const c = datum.data as CompanyPoint;
      return {
        title: `${c.name} (${c.symbol})`,
        rows: [
          { label: 'HQ country', value: c.iso2 },
          { label: 'Sector', value: c.sector ?? '—' },
          ...(c.changePct !== undefined
            ? [{ label: 'Change', value: `${c.changePct >= 0 ? '+' : ''}${c.changePct.toFixed(2)}%` }]
            : []),
        ],
      };
    },
    onClick: (datum) => onSelect?.(datum.data as CompanyPoint),
  };
}

/** Portfolio layer — countries the user's holdings are exposed to. */
export function buildPortfolioLayer(
  exposureCountries: Array<{ iso2: string; weight: number }>,
  countries: CountrySummary[],
): MapLayer {
  const byIso = new Map(countries.map((c) => [c.iso2, c]));
  const data: LayerDatum[] = exposureCountries.reduce<LayerDatum[]>((acc, e) => {
    const c = byIso.get(e.iso2);
    if (!c || c.lon == null || c.lat == null) return acc;
    acc.push({
      id: `pf-${e.iso2}`,
      lon: c.lon,
      lat: c.lat,
      value: e.weight,
      label: c.name,
      data: { ...e, name: c.name },
    });
    return acc;
  }, []);
  return {
    id: 'portfolio',
    name: 'Portfolio',
    enabled: false,
    type: 'effect-scatter',
    zIndex: 40,
    data: () => data,
    tooltip: (datum) => {
      const d = datum.data as { iso2: string; weight: number; name: string };
      return {
        title: `${d.name} exposure`,
        rows: [{ label: 'Portfolio weight', value: `${(d.weight * 100).toFixed(1)}%` }],
        note: 'Exposure relationship only — not a recommendation.',
      };
    },
  };
}

/**
 * Layer factory: builds the layers that currently have data. The caller owns
 * `enabled` state; this returns descriptors only.
 */
export interface LayerInputs {
  state: InvestorEyeState;
  economicValues?: { metricLabel: string; values: Record<string, number> } | null;
  companies?: CompanyPoint[];
  portfolioExposure?: Array<{ iso2: string; weight: number }>;
  onSelectEvent?: (e: NormalizedEvent) => void;
  onSelectMarket?: (m: MarketObservation) => void;
  onSelectCompany?: (c: CompanyPoint) => void;
}

export function buildAllLayers(inputs: LayerInputs): MapLayer[] {
  const { state } = inputs;
  const layers: MapLayer[] = [
    buildCountryEventFill(state.countries, 'density', 'Event Density', false),
    buildEventsLayer(state.events, inputs.onSelectEvent),
    buildMarketsLayer(state.markets, state.countries, inputs.onSelectMarket),
    buildConflictLayer(state.events, inputs.onSelectEvent),
    buildShippingLayer(state.events, inputs.onSelectEvent),
    buildEnergyLayer(state.events, inputs.onSelectEvent),
    buildCommoditiesLayer(state.events, inputs.onSelectEvent),
    buildWeatherLayer(state.events, inputs.onSelectEvent),
    buildFiresLayer(state.events, inputs.onSelectEvent),
    buildTradeLayer(state.events, state.countries, inputs.onSelectEvent),
  ];
  if (inputs.economicValues) {
    layers.push(buildEconomyLayer(inputs.economicValues.values, inputs.economicValues.metricLabel));
  }
  if (inputs.companies && inputs.companies.length > 0) {
    layers.push(buildCompaniesLayer(inputs.companies, inputs.onSelectCompany));
  }
  if (inputs.portfolioExposure && inputs.portfolioExposure.length > 0) {
    layers.push(buildPortfolioLayer(inputs.portfolioExposure, state.countries));
  }
  return layers;
}
