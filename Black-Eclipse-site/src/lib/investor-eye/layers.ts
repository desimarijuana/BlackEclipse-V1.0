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
  'economy', 'weather', 'fires', 'companies', 'risk', 'portfolio', 'event-heatmap',
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
 *
 * Beyond the primitive shapes, a layer may carry an SVG `path://` glyph. That is
 * what lets a conflict render as a blast, an earthquake as seismic rings and a
 * fire as a flame, instead of every layer being the same dot. ECharts' symbol
 * helper supports `path://` in the 2D renderer AND echarts-gl's sprite builder
 * uses the same helper, so one glyph serves both projections.
 */
export type LayerSymbol =
  | 'circle' | 'diamond' | 'triangle' | 'square' | 'ring'
  | 'path://';

/**
 * A 100x100 viewBox is the convention ECharts' symbol helper expects.
 *
 * Glyph design rules:
 *   - drawn as a solid silhouette, because the map tints the whole path,
 *   - visually distinct at 8–18px, so no fine detail,
 *   - recognisable in silhouette (a flame, a blast, a wave) rather than by
 *     internal line-work that disappears when scaled down.
 */
export const SYMBOL_PATHS = {
  /** Blast: an 8-point starburst with a jagged core — conflict/attack. */
  blast: 'path://M50,4 L58,32 L78,14 L72,42 L96,38 L76,58 L96,66 L70,70 L80,94 L56,78 L50,96 L44,78 L20,94 L30,70 L4,66 L24,58 L4,38 L28,42 L22,14 L42,32 Z',
  /**
   * Seismic rings: concentric HOLLOW rings radiating from a centre.
   *
   * Two rules make this work, and both bit us:
   *   1. Each circle is TWO 180° arcs, not one near-full arc. A single
   *      `A r,r 0 1,1 x,y` back to a point 0.1px away renders as a lumpy
   *      circle that lands off-centre.
   *   2. Alternating rings are wound in OPPOSITE directions. A canvas/SVG fill
   *      uses the nonzero winding rule, so drawing every ring the same way
   *      fills the disc solid — the earthquake layer shipped as a plain dot,
   *      indistinguishable from the catch-all event marker.
   */
  seismic:
    'path://M86,50 A36,36 0 1,1 14,50 A36,36 0 1,1 86,50 Z ' +
    'M74,50 A24,24 0 1,0 26,50 A24,24 0 1,0 74,50 Z ' +
    'M68,50 A18,18 0 1,1 32,50 A18,18 0 1,1 68,50 Z ' +
    'M58,50 A8,8 0 1,0 42,50 A8,8 0 1,0 58,50 Z',
  /** Flame: a tapered teardrop with a notch — fire. */
  flame: 'path://M50,4 C64,26 82,38 82,58 C82,76 68,92 50,92 C32,92 18,76 18,58 C18,42 30,34 38,20 C40,32 46,38 50,26 C52,20 51,12 50,4 Z',
  /** Wave + hull: a ship riding two swells — shipping. */
  wave: 'path://M50,16 L78,20 L84,34 L74,34 L72,54 L28,54 L26,34 L16,34 L22,20 Z M8,66 C22,56 34,76 48,66 C62,56 74,76 88,66 L92,80 C74,92 58,72 48,80 C38,88 22,72 4,80 Z',
  /** Opposed arrows: exchange — trade. Two separated arrows, never overlapping. */
  exchange: 'path://M6,16 L46,16 L46,6 L74,26 L46,46 L46,36 L6,36 Z M94,64 L54,64 L54,54 L26,74 L54,94 L54,84 L94,84 Z',
  /** Bolt in a droplet — energy. */
  bolt: 'path://M50,4 L88,50 L66,50 L74,96 L26,44 L48,44 Z',
  /** Hexagonal ingot — commodities. */
  ingot: 'path://M28,22 L72,22 L92,50 L72,78 L28,78 L8,50 Z',
  /** Upward bars with a trend arrow — markets. */
  market: 'path://M10,90 L10,60 L24,60 L24,90 Z M30,90 L30,44 L44,44 L44,90 Z M50,90 L50,28 L64,28 L64,90 Z M74,34 L88,18 L94,24 L80,40 Z',
  /** Office block with a pinnacle — companies. */
  company: 'path://M18,92 L18,26 L50,10 L50,92 Z M58,92 L58,38 L86,50 L86,92 Z M28,38 L38,38 L38,48 L28,48 Z M28,58 L38,58 L38,68 L28,68 Z',
  /**
   * Open ring — portfolio exposure.
   *
   * Same construction as `seismic`: two 180° arcs per circle (a single
   * near-full arc renders off-centre), with the hole wound the opposite way so
   * the nonzero fill rule punches it out.
   */
  portfolio:
    'path://M90,50 A40,40 0 1,1 10,50 A40,40 0 1,1 90,50 Z ' +
    'M72,50 A22,22 0 1,0 28,50 A22,22 0 1,0 72,50 Z',
  /**
   * Warning triangle — risk.
   *
   * The centre triangle is listed in the OPPOSITE vertex order to the outer one
   * so the nonzero fill rule punches it out. Listed the same way round (as it
   * was) the triangle renders solid and reads as a plain shape.
   */
  risk: 'path://M50,8 L96,88 L4,88 Z M50,36 L36,68 L64,68 Z',
  /**
   * A small solid dot — the generic "everything" marker.
   *
   * Deliberately the LEAST distinctive glyph: the `events` layer is a catch-all
   * over every geolocated event, so it must read as background texture. A large
   * shape here (a diamond was the first choice) visually buries the meaningful
   * category glyphs drawn on top of it.
   *
   * Built from two 180° arcs — a single near-full arc lands off-centre.
   */
  event: 'path://M78,50 A28,28 0 1,1 22,50 A28,28 0 1,1 78,50 Z',
  /**
   * Density haze — the event heatmap swatch.
   *
   * A solid core plus one faint outer RING (an annulus, hole wound opposite so
   * the nonzero rule punches it out), so a small 11px legend glyph reads as
   * "a blob with a halo" — the heatmap's look — rather than a plain dot.
   */
  heat: 'path://M58,50 A8,8 0 1,1 42,50 A8,8 0 1,1 58,50 Z ' +
    'M86,50 A36,36 0 1,1 14,50 A36,36 0 1,1 86,50 Z ' +
    'M74,50 A24,24 0 1,0 26,50 A24,24 0 1,0 74,50 Z',
} as const;

export type SymbolGlyphName = keyof typeof SYMBOL_PATHS;

export interface LayerMeta {
  name: string;
  phase: 1 | 2;
  group: LayerGroupId;
  /** Per-layer accent (falls back to the group colour when absent). */
  color: string;
  /** Only meaningful for point layers. */
  symbol?: LayerSymbol;
  /**
   * The category glyph. Preferred over `symbol` wherever it is set — this is
   * what makes each domain visually its own thing.
   */
  glyph?: SymbolGlyphName;
  /** One-line description of what the layer draws, shown in tooltips. */
  hint: string;
}

export const LAYER_META: Record<LayerId, LayerMeta> = {
  events: { name: 'Events', phase: 1, group: 'events', color: '#38bdf8', glyph: 'event', hint: 'All geolocated world events' },
  markets: { name: 'Markets', phase: 1, group: 'markets', color: '#34d399', glyph: 'market', hint: 'Index observations by country' },
  conflict: { name: 'Conflict', phase: 2, group: 'events', color: '#ef4444', glyph: 'blast', hint: 'Conflict, military and protest events' },
  shipping: { name: 'Shipping', phase: 2, group: 'flows', color: '#0ea5e9', glyph: 'wave', hint: 'Shipping, ports, straits and supply-chain events' },
  trade: { name: 'Trade', phase: 2, group: 'flows', color: '#eab308', glyph: 'exchange', hint: 'Trade, tariff and sanction co-mentions' },
  energy: { name: 'Energy', phase: 2, group: 'flows', color: '#fb923c', glyph: 'bolt', hint: 'Oil, gas and power events' },
  commodities: { name: 'Commodities', phase: 2, group: 'economy', color: '#f59e0b', glyph: 'ingot', hint: 'Events naming a traded commodity' },
  economy: { name: 'Economy', phase: 2, group: 'economy', color: '#a78bfa', hint: 'Country metric fill (real series only)' },
  weather: { name: 'Earthquakes', phase: 2, group: 'hazards', color: '#22d3ee', glyph: 'seismic', hint: 'USGS seismic events' },
  fires: { name: 'Fires', phase: 2, group: 'hazards', color: '#f97316', glyph: 'flame', hint: 'NASA FIRMS satellite fire clusters' },
  companies: { name: 'Companies', phase: 2, group: 'markets', color: '#60a5fa', glyph: 'company', hint: 'Listed companies by HQ country' },
  risk: { name: 'Risk', phase: 2, group: 'events', color: '#f472b6', glyph: 'risk', hint: 'Event density per country' },
  portfolio: { name: 'Portfolio', phase: 2, group: 'markets', color: '#818cf8', glyph: 'portfolio', hint: 'Countries your holdings are exposed to' },
  'event-heatmap': { name: 'Event Heatmap', phase: 2, group: 'events', color: '#f43f5e', glyph: 'heat', hint: 'Severity-weighted event density — Bloomberg-style heat layer' },
};

/** Accent for a layer: its own colour, else its group's. */
export function layerColor(id: string): string {
  return LAYER_META[id as LayerId]?.color ?? LAYER_GROUPS[0].color;
}

/**
 * The ECharts `symbol` value for a layer.
 *
 * A `glyph` wins over the primitive `symbol`: the whole point of the glyph set
 * is that a conflict reads as a blast and a fire as a flame. Falls back to the
 * primitive shape, then to a circle.
 */
export function layerSymbol(id: string): string {
  const meta = LAYER_META[id as LayerId];
  if (!meta) return 'circle';
  if (meta.glyph) return SYMBOL_PATHS[meta.glyph];
  return meta.symbol && meta.symbol !== 'path://' ? meta.symbol : 'circle';
}

/** The inline glyph name for a layer, for rendering the legend. */
export function layerGlyph(id: string): SymbolGlyphName | undefined {
  return LAYER_META[id as LayerId]?.glyph;
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
    // BELOW the category layers (zIndex 25). `events` is a catch-all over every
    // geolocated event, so it must read as background texture; when it sat at 30
    // its dot was drawn ON TOP of the conflict/fire/energy glyphs and buried the
    // very shapes that say what each event is.
    zIndex: 15,
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

/**
 * Density cell size (degrees) for the event heatmap, chosen from the event
 * count so the grid never degrades into per-event specks or one global smear.
 * Coarser than the pin clustering on purpose: a hotspot is a REGION, not a
 * point.
 */
function heatmapCellDegrees(count: number): number {
  if (count > 4000) return 8;
  if (count > 1500) return 5;
  if (count > 600) return 3;
  if (count > 200) return 2;
  return 1.5;
}

/**
 * Severity-weighted event DENSITY heatmap (Bloomberg-style). Events are
 * aggregated onto a grid and each cell's intensity is the SUM of its members'
 * severity weights, so a hotspot is literally "where the most — and most
 * severe — events are happening". Emitting one datum per raw event instead
 * (the first cut) drew a flat blue wash: every point had the same ~1px weight
 * and ECharts' heat brush then blurred single events below visibility.
 */
export function buildEventHeatmapLayer(events: NormalizedEvent[]): MapLayer {
  const anchorable = events.filter((e) => typeof e.lon === 'number' && typeof e.lat === 'number');
  const points = anchorable.map((e) => ({
    id: e.id ?? e.dedupKey,
    lon: e.lon as number,
    lat: e.lat as number,
    severity: e.severity,
    weight: severityWeight(e.severity),
    event: e,
  }));
  // A COARSE regional grid — deliberately much coarser than the pin-cluster
  // grid. A heatmap answers "where is activity concentrated?", so neighbouring
  // events must accumulate into one hotspot; at the pins' fine 0.1° grid every
  // event was its own faint speck and the layer read as noise.
  const clusters = aggregatePoints(points, heatmapCellDegrees(anchorable.length), 1);
  const data: LayerDatum[] = clusters.map((c, i) => ({
    id: `heat-${i}`,
    lon: c.lon,
    lat: c.lat,
    // Summed severity weight IS the intensity — dense critical clusters burn
    // hottest, a lone low event barely registers.
    value: c.weight,
    severity: c.maxSeverity,
    label: c.members[0]?.event.title,
    geoMethod: c.count > 1 ? 'centroid' : c.members[0]?.event.geoMethod,
    data: { cluster: c, representative: c.members[0]?.event },
  }));
  return {
    id: 'event-heatmap',
    name: 'Event Heatmap',
    enabled: false,
    type: 'heatmap',
    zIndex: 6,
    data: () => data,
    tooltip: (datum) => {
      const payload = datum.data as { cluster: typeof clusters[number]; representative?: NormalizedEvent };
      const c = payload.cluster;
      if (c.count <= 1 && payload.representative) {
        const e = payload.representative;
        return {
          title: e.title,
          rows: [
            { label: 'Severity', value: e.severity },
            { label: 'Type', value: e.eventType },
            { label: 'Published', value: formatUtc(e.publishedAt) },
          ],
        };
      }
      return {
        title: `${c.count} nearby events`,
        rows: [
          { label: 'Highest severity', value: c.maxSeverity },
          { label: 'Density weight', value: c.weight.toFixed(2) },
        ],
        note: 'Aggregated severity-weighted density. Zoom in to separate events.',
      };
    },
  };
}

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
          fromName: a.name,
          toName: b.name,
          fromIso: a.iso2,
          toIso: b.iso2,
          event: e,
          /** Stable key so the map can emphasise the clicked line. */
          eventKey: e.id ?? e.dedupKey,
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
      const d = datum.data as { event: NormalizedEvent; fromName?: string; toName?: string };
      return tradeTooltip(d.event, d.fromName, d.toName);
    },
    onClick: (datum) => {
      const d = datum.data as { event: NormalizedEvent };
      onSelect?.(d.event);
    },
  };
}

/**
 * Tooltip for a trade ROUTE. Unlike a generic event tooltip, a trade line's
 * whole meaning is the pair of endpoints, so the route leads and the traded
 * goods/provenance follow. This is the "can I see what is being traded between
 * these two?" answer.
 */
function tradeTooltip(event: NormalizedEvent, fromName?: string, toName?: string): TooltipContent {
  if (!event || typeof event !== 'object' || typeof event.eventType !== 'string') {
    return { title: 'Trade link', rows: [{ label: 'Detail', value: 'unavailable' }] };
  }
  const route = fromName && toName ? `${fromName} ↔ ${toName}` : event.countries.join(' ↔ ') || 'Trade link';
  const rows: Array<{ label: string; value: string }> = [
    { label: 'Route', value: route },
    { label: 'Type', value: event.eventType.replace(/_/g, ' ') },
    { label: 'Severity', value: event.severity },
  ];
  if (event.commodities.length > 0) rows.push({ label: 'Traded goods', value: event.commodities.join(', ') });
  if (event.channels.length > 0) rows.push({ label: 'Channels', value: event.channels.join(', ') });
  rows.push({ label: 'First detected', value: formatUtc(event.publishedAt) });
  rows.push({ label: 'Sources', value: String(event.sourceCount) });
  return {
    title: event.title,
    subtitle: event.summary,
    rows,
    note:
      'A link is drawn only when the same event names both countries — an observed co-mention, not a confirmed trade flow.',
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
    buildEventHeatmapLayer(state.events),
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
