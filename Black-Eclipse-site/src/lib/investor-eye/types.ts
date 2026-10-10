// ── Investor Eye — core types ────────────────────────────────────────────────
// The normalized world-state vocabulary. Everything the UI renders comes from
// these shapes, and every shape that originates outside this app is normalized
// into one of them before it is stored or displayed.
//
// Provenance rules (hard requirements):
//   - `UNAVAILABLE` means "no real data" — never a fabricated payload.
//   - A *failed* source is UNAVAILABLE; a healthy source that observed zero
//     events may honestly return 0.
//   - Nothing simulated is ever labelled LIVE.

/** Where a value came from, in decreasing order of freshness. */
export type Provenance =
  | 'LIVE'
  | 'DELAYED'
  | 'CACHED'
  | 'HISTORICAL'
  | 'ESTIMATED'
  | 'DEMO'
  | 'UNAVAILABLE';

export type EventType =
  | 'conflict'
  | 'military'
  | 'protest'
  | 'election'
  | 'diplomatic'
  | 'sanction'
  | 'trade'
  | 'tariff'
  | 'cyber'
  | 'energy'
  | 'shipping'
  | 'natural_disaster'
  | 'monetary'
  | 'fiscal'
  | 'regulatory'
  | 'other';

export type EventSeverity = 'low' | 'medium' | 'high' | 'critical';

/**
 * Sub-categories for events whose type is too coarse on its own. Currently the
 * hazard sub-types: both are `natural_disaster`, but they are independent
 * physical phenomena with their own sources, layers and detail presentation.
 */
export const HAZARD_CATEGORIES = ['earthquake', 'fire'] as const;
export type HazardCategory = (typeof HAZARD_CATEGORIES)[number];

/** One independent source that reported (or confirmed) an event. */
export interface SourceRef {
  id: string;
  name: string;
  url?: string;
  publishedAt?: string;
}

/** Entity kinds an event can be joined to. */
export type EntityKind =
  | 'country'
  | 'actor'
  | 'location'
  | 'commodity'
  | 'sector'
  | 'security'
  | 'market';

export interface EventEntityRef {
  kind: EntityKind;
  entityId: string;
  name: string;
  lon?: number;
  lat?: number;
}

/** One actor in an event (a state, an organisation, a named group). */
export interface EventActor {
  name: string;
  /** ISO3 country code of the actor, when the provider gives one. */
  countryCode?: string;
  /** Provider actor-type code (GDELT's 3-letter type, e.g. GOV/MIL/REB). */
  typeCode?: string;
}

/**
 * A normalized, deduplicated event. One instance per real-world event, not per
 * article. `confidence` is internal data-quality confidence — it is never
 * presented as scientific certainty.
 */
export interface NormalizedEvent {
  /** JDDS row id — present only for persisted events read back from the DB. */
  id?: string;
  dedupKey: string;
  title: string;
  summary?: string;
  /**
   * A real article headline, when one is available. GDELT's bulk export has
   * none (only URLs), so this is populated by the news-corpus enrichment or left
   * absent — NEVER synthesized from the actors, because a fabricated headline
   * would read as reporting that does not exist.
   */
  headline?: string;
  /** A real article description/summary, same provenance rules as `headline`. */
  description?: string;
  /**
   * Named actors, when the provider supplies them (GDELT's Actor1/Actor2). This
   * is the "who" of an event and is what makes a conflict readable — it was
   * previously parsed and then thrown away.
   */
  actors?: EventActor[];
  /**
   * Provider-native classification, kept verbatim for transparency: GDELT's
   * CAMEO root code and Goldstein intensity. Not interpreted — shown as-is.
   */
  providerCodes?: { cameoRoot?: string; goldstein?: number };
  /** The place name the coordinates resolved to, when known. */
  placeName?: string;
  /**
   * How the coordinate was determined — so the UI never implies more precision
   * than we have. `provider` = the source gave exact coordinates (GDELT/USGS);
   * `place` = resolved from a named place (gazetteer); `capital` = the country's
   * capital, used for policy events where the centroid would be misleading;
   * `centroid` = only a country was known, so it plots at the country centre.
   */
  geoMethod?: 'provider' | 'place' | 'capital' | 'centroid';
  eventType: EventType;
  /**
   * Provider-level sub-classification, kept when the event type alone is too
   * coarse to be useful. The motivating case (spec §7/§8): `natural_disaster`
   * covers both an EARTHQUAKE and a FIRE, and those need their own map layers
   * and their own detail treatment. Only set from a provider that actually
   * states it (USGS = earthquake, FIRMS = fire) — never inferred from text.
   */
  category?: string;
  severity: EventSeverity;
  /** Economic channels the event could transmit through (observed relevance). */
  channels: string[];
  commodities: string[];
  sectors: string[];
  securities: string[];
  /** ISO2 country codes. */
  countries: string[];
  lon?: number;
  lat?: number;
  confidence: number;
  sourceCount: number;
  sources: SourceRef[];
  primarySource: string;
  publishedAt: string;
  firstSeen?: string;
  lastUpdated?: string;
  status?: 'active' | 'archived';
  /**
   * 0..1 investor-relevance (see `relevance.ts`). Distinct from `confidence`:
   * confidence is "how well corroborated", relevance is "does this matter to a
   * portfolio". Optional because non-GDELT sources may not score it.
   */
  relevance?: number;
  /** Why it scored that relevance (shown in the UI, never a bare number). */
  relevanceReasons?: string[];
  /**
   * True when this event was served from the persisted JDDS window rather than
   * the sources fetched in THIS assembly — i.e. it is real, within-window
   * evidence observed in an earlier cycle and replayed so the map does not lose
   * an event the moment it ages out of the latest provider file. In-memory only
   * (never written back), so it does not affect stored rows.
   */
  replayed?: boolean;
  /**
   * A source-declared STABLE identity for this record, when the provider already
   * has one (GDELT's GLOBALEVENTID).
   *
   * Clustering merges records it believes describe one real-world event, using
   * fuzzy title similarity. That is safe for articles but WRONG for records the
   * provider has already identified: two GDELT events with distinct ids are two
   * events, even when their titles look alike (every GDELT title ends with the
   * same "— City, Region, Country" tail, which made unrelated stories in one
   * city look similar and fuse). When either side carries a signature, records
   * merge ONLY on an exact signature match.
   */
  clusterSignature?: string;
}

/** A connector's declared health/status, shown on the Data Health screen. */
export interface SourceStatus {
  id: string;
  name: string;
  /** What the source provides, e.g. ['EVENTS'], ['NATURAL_EVENTS']. */
  capabilities: string[];
  /** Whether the source needs an operator credential to work. */
  requiresCredentials: boolean;
  /**
   * Honest state:
   *   available   healthy and producing data
   *   configured  configured but has not run yet
   *   optional    needs an operator credential (not a failure)
   *   rate_limited throttled upstream — temporary, not broken
   *   error       failed for another reason
   *   unavailable never ran / no data
   */
  state: 'available' | 'configured' | 'optional' | 'rate_limited' | 'error' | 'unavailable';
  lastSuccess?: string;
  lastError?: string;
  latencyMs?: number;
  recordsLastRun?: number;
  /** Seconds until a throttled source may be retried (rate_limited only). */
  retryAfterSec?: number;
}

/** Structured result of one ingestion attempt, for observability. */
export interface SourceRunSummary {
  source: string;
  startedAt: string;
  finishedAt: string;
  durationMs: number;
  recordsReceived: number;
  recordsAccepted: number;
  recordsRejected: number;
  error?: string;
  /** Distinct outcome, so a throttle is never reported as a broken source. */
  status?: 'ok' | 'empty' | 'rate_limited' | 'error';
  provenance: Provenance;
}

/**
 * The raw payload a source adapter yields before normalization. Kept loose so
 * each adapter can carry its provider's native shape; the normalizer owns the
 * conversion into `NormalizedEvent`.
 */
export interface RawEvent {
  sourceId: string;
  sourceName: string;
  /** Provider-native record. */
  raw: unknown;
  retrievedAt: string;
}

export interface SourceQuery {
  /** Look-back window in hours. */
  hours: number;
  maxRecords?: number;
  /** Optional free-text query (provider-specific). */
  text?: string;
  /** Abort/timeout override, clamped by the transport. */
  timeoutMs?: number;
}

/**
 * The Investor Eye source-adapter contract. Shaped like the existing
 * `lib/connectors` `DataConnector` but additive — it does not replace or fork
 * that registry. All transport goes through the shared `safeGet`.
 */
export interface EventSource {
  readonly id: string;
  readonly name: string;
  readonly capabilities: string[];
  readonly requiresCredentials: boolean;
  /** True when the source can run in this environment right now. */
  isConfigured(): boolean;
  /** Fetch raw records for a query. */
  fetch(query: SourceQuery): Promise<RawEvent[]>;
  /** Convert raw records into normalized events (may return []). */
  normalize(records: RawEvent[]): NormalizedEvent[];
}

// ── Relationship graph (spec §41) ────────────────────────────────────────────
// A relational, typed, directed graph over entities. Deliberately NOT a graph
// database (ADR-011): edges live in the `Relationship` table and are aggregated
// into a render-ready node/link view by the pure `graph.ts` builder.

/** Node kinds the graph understands. */
export type GraphNodeKind =
  | 'country'
  | 'company'
  | 'security'
  | 'commodity'
  | 'sector'
  | 'market'
  | 'event';

/** How an edge was established — never present an inference as a fact. */
export type RelationClass = 'OBSERVED' | 'HISTORICAL' | 'INFERRED' | 'AI-INTERPRETED';

/** A directed edge between two entities, as stored. */
export interface RelationshipEdge {
  edgeKey: string;
  fromKind: string;
  fromId: string;
  fromName: string;
  toKind: string;
  toId: string;
  toName: string;
  relation: string;
  relationClass: RelationClass;
  weight: number;
  evidence: Array<{ eventId?: string; source?: string; url?: string; note?: string }>;
  provenance: Provenance;
  lastSeen?: string;
}

/** A render-ready graph node (identity + degree + kind). */
export interface GraphNode {
  id: string;
  kind: string;
  name: string;
  /** Number of edges incident to this node (drives node size). */
  degree: number;
  /** Sum of incident edge weights (drives node emphasis). */
  weight: number;
  /** ISO2 when this node is a country (lets the graph offer a map pivot). */
  iso2?: string;
}

/** A render-ready graph link, carrying the strongest class among its edges. */
export interface GraphLink {
  source: string;
  target: string;
  relation: string;
  relationClass: RelationClass;
  weight: number;
  /** Distinct relations collapsed into this link. */
  relations: string[];
}

export interface RelationshipGraph {
  nodes: GraphNode[];
  links: GraphLink[];
  /** Edge totals before any node limit was applied (honest truncation). */
  totals: { edges: number; nodes: number; truncated: boolean };
  generatedAt: string;
  provenance: Provenance;
}

// ── Map layer contract ───────────────────────────────────────────────────────
// A layer is a data + behavior descriptor. The ECharts adapter translates it
// into series; the map component carries NO business logic.

export type MapLayerType =
  | 'country-fill'
  | 'scatter'
  | 'effect-scatter'
  | 'lines'
  | 'heatmap'
  | 'custom'
  | 'symbol';

/** A single datum a layer can render. */
export interface LayerDatum {
  id: string;
  /** Anchor position, when the layer is point/symbol based. */
  lon?: number;
  lat?: number;
  /** Fill value for region layers (country-fill/heatmap). */
  countryIso?: string;
  value?: number;
  label?: string;
  severity?: EventSeverity;
  /**
   * How precise this point's location is. A country-centroid point is drawn as a
   * hollow marker so a user can tell "we know the country" from "we know the
   * place" — otherwise a guess looks identical to an exact fix.
   */
  geoMethod?: 'provider' | 'place' | 'capital' | 'centroid';
  /** Arbitrary payload handed back to tooltip/onClick. */
  data?: unknown;
}

export interface TooltipContent {
  title: string;
  subtitle?: string;
  rows: Array<{ label: string; value: string }>;
  /** Explicitly separated so inference is never shown as fact. */
  note?: string;
}

export interface MapLayer {
  id: string;
  name: string;
  enabled: boolean;
  type: MapLayerType;
  zIndex: number;
  /** Datum accessor — supplied by the caller, never fetched inside the map. */
  data: () => LayerDatum[];
  tooltip?: (datum: LayerDatum) => TooltipContent;
  onClick?: (datum: LayerDatum) => void;
}

// ── Aggregate state ──────────────────────────────────────────────────────────

/** Market observation for the market layer (reuses /api/indices data). */
export interface MarketObservation {
  marketId: string;
  iso2?: string;
  name: string;
  symbol: string;
  price: number;
  changePct: number;
  currency?: string;
  provenance: Provenance;
  updatedAt?: string;
}

export interface CountrySummary {
  iso2: string;
  iso3?: string;
  name: string;
  region?: string;
  lon?: number;
  lat?: number;
  eventCount: number;
  lastEventAt?: string;
  markets: MarketObservation[];
}

export interface DataStatus {
  provenance: Provenance;
  updatedAt: string | null;
  /** Human label, e.g. "UPDATED 42s AGO". */
  label: string;
  sources: SourceStatus[];
}

/** A company positioned on the map (Phase 2 companies layer). */
export interface CompanyPoint {
  symbol: string;
  name: string;
  iso2: string;
  sector?: string;
  changePct?: number;
  /** Present when the API has resolved a map position (buildCompanies). */
  lon?: number;
  lat?: number;
}

/** One economic metric across countries (Phase 2 economy layer). */
export interface EconomicLayerData {
  metricId: string;
  metricLabel: string;
  unit: string;
  /** ISO2 → value. Only countries with a real value appear. */
  values: Record<string, number>;
  provenance: Provenance;
}

/** The top-level object the API returns and the map visualizes. */
export interface InvestorEyeState {
  generatedAt: string;
  windowHours: number;
  events: NormalizedEvent[];
  countries: CountrySummary[];
  markets: MarketObservation[];
  status: DataStatus;
  /** Present when the event feed itself could not be produced. */
  eventsUnavailable?: boolean;
  lastKnownAt?: string | null;
  /**
   * True when this payload is a stale snapshot served immediately while a
   * rebuild runs in the background (stale-while-revalidate). The UI shows it as
   * cached/last-known rather than live, which is why it is explicit.
   */
  refreshing?: boolean;
}
