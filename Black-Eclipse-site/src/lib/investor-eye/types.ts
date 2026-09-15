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
  eventType: EventType;
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
}

/** A connector's declared health/status, shown on the Data Health screen. */
export interface SourceStatus {
  id: string;
  name: string;
  /** What the source provides, e.g. ['EVENTS'], ['NATURAL_EVENTS']. */
  capabilities: string[];
  /** Whether the source needs an operator credential to work. */
  requiresCredentials: boolean;
  /** Honest state: available | configured | optional | unavailable. */
  state: 'available' | 'configured' | 'optional' | 'unavailable';
  lastSuccess?: string;
  lastError?: string;
  latencyMs?: number;
  recordsLastRun?: number;
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
}
