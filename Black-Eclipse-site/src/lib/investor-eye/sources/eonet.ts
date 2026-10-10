// ── Investor Eye — NASA EONET source ─────────────────────────────────────────
// NASA's Earth Observatory Natural Event Tracker (EONET) v3 is a free, keyless,
// JSON, global feed of *curated* natural events: wildfires, severe storms,
// floods, volcanoes, droughts, dust/haze, landslides, sea/lake ice, snow,
// temperature extremes, water colour and some man-made incidents.
//
// WHY THIS SOURCE (spec §5): before this, the hazard layer carried only
// earthquakes (USGS) and fires (FIRMS) — both single-phenomenon providers.
// EONET adds the missing storm/flood/drought/volcano/ice coverage with a single
// request and no credential, and it is the authoritative NASA aggregator (each
// event cites the agencies that reported it), so it is also a corroboration
// source for events other feeds only hint at.
//
// HONESTY RULES (same discipline as the other adapters):
//   - The EONET event id is a provider-stated stable identity, so it is used as
//     the cluster signature — an event is never fuzzy-merged with news text.
//   - Geometry is an observation *history*; the most recent observation is the
//     current position. A polygon event (large fires, sea ice) is reduced to a
//     representative centroid so it can be plotted; that is a coordinate derived
//     from provider geometry, not a fabricated one.
//   - Only the EONET `link` (unique per event) is carried as a source URL. The
//     corroborating agency URLs are recorded by name/id but NOT as source URLs,
//     because a shared agency URL (e.g. one InciWeb page) would otherwise be read
//     as article identity and fuse unrelated events.
//   - Severity uses the provider's own magnitude ONLY where the unit is known
//     (earthquake magnitude, storm wind speed in knots); everything else falls
//     back to the honest text lexicon.
//
// Transport goes through the shared `safeGet` (https-only, DNS-pinned, capped).

import { safeGet, OutboundError } from '@/lib/connectors/security';
import { classifyChannels, classifyCommodities, classifySectors, classifySeverity } from '../classify';
import { dedupKeyFor } from '../dedup';
import { confidenceOf } from '../cluster';
import { resolveFireCountry } from './firms';
import type {
  EventSeverity, EventSource, NormalizedEvent, RawEvent, SourceQuery,
} from '../types';

export const EONET_SOURCE_ID = 'eonet';

const EONET_BASE = 'https://eonet.gsfc.nasa.gov/api/v3/events';

/** Maximum look-back EONET is asked for, in days (bounded request). */
const EONET_MAX_DAYS = 20;

/** Bounded retry for a transient fetch failure (mirrors `firmsSource`). */
const EONET_ATTEMPTS = 2;
const EONET_RETRY_DELAY_MS = 800;

/**
 * EONET category id → Investor Eye `category`. The provider categories are
 * already precise, so most map one-to-one; the two that overlap our existing
 * hazard vocabulary are folded onto it so a wildfire from EONET and one from
 * FIRMS share the same layer key.
 */
export const EONET_CATEGORY_MAP: Record<string, string> = {
  wildfires: 'fire',
  earthquakes: 'earthquake',
  severeStorms: 'storm',
  volcanoes: 'volcano',
  floods: 'flood',
  drought: 'drought',
  dustAndHaze: 'dust',
  landslides: 'landslide',
  seaLakeIce: 'sea_lake_ice',
  snow: 'snow',
  temperatureExtremes: 'temperature_extreme',
  waterColor: 'water_color',
  manmade: 'manmade',
};

/** Map a raw EONET category id to our normalized sub-category. */
export function mapEonetCategory(id: string | undefined): string | undefined {
  if (!id) return undefined;
  return EONET_CATEGORY_MAP[id] ?? id.toLowerCase();
}

interface EonetGeometry {
  magnitudeValue?: number | null;
  magnitudeUnit?: string | null;
  date?: string | null;
  type?: string | null;
  coordinates?: unknown;
}

interface EonetSource {
  id?: string | null;
  url?: string | null;
  source?: string | null;
}

interface EonetEvent {
  id?: string | null;
  title?: string | null;
  description?: string | null;
  link?: string | null;
  closed?: string | null;
  categories?: Array<{ id?: string | null; title?: string | null }>;
  sources?: EonetSource[];
  geometry?: EonetGeometry[];
}

interface EonetResponse {
  events?: EonetEvent[];
}

/**
 * Reduce an EONET geometry to a single [lon, lat].
 *
 * EONET geometry is a list of observations over the event's life, so the LAST
 * entry is the current position. Point/LineString coordinates are taken at their
 * first vertex (a line's start is a real reported position); Polygon rings are
 * averaged to a representative centroid. A malformed geometry yields null rather
 * than a defaulted (0,0) — which would plot a real-looking event off Africa.
 */
export function pickLatestGeometry(
  geometries: EonetGeometry[] | undefined,
): { lon: number; lat: number; at: string | null } | null {
  if (!geometries || geometries.length === 0) return null;
  // Most recent observation first (fall back to last on unparsable dates).
  const sorted = [...geometries].sort((a, b) => {
    const ta = Date.parse(a.date ?? '');
    const tb = Date.parse(b.date ?? '');
    if (Number.isNaN(ta) && Number.isNaN(tb)) return 0;
    if (Number.isNaN(ta)) return 1;
    if (Number.isNaN(tb)) return -1;
    return tb - ta;
  });
  for (const g of sorted) {
    const point = geometryPoint(g);
    // (0,0) is a null-island sentinel, not a real observation. Reject the whole
    // geometry rather than plotting a real-looking event in the Gulf of Guinea.
    if (point && !(point.lon === 0 && point.lat === 0)) {
      return { ...point, at: g.date ?? null };
    }
  }
  return null;
}

function toCoord(pair: unknown): [number, number] | null {
  if (!Array.isArray(pair) || pair.length < 2) return null;
  const lon = Number(pair[0]);
  const lat = Number(pair[1]);
  if (!Number.isFinite(lon) || !Number.isFinite(lat)) return null;
  return [lon, lat];
}

/** True when two coordinate pairs are numerically identical. */
function samePair(a: unknown, b: unknown): boolean {
  const ca = toCoord(a);
  const cb = toCoord(b);
  return Boolean(ca && cb && ca[0] === cb[0] && ca[1] === cb[1]);
}

function geometryPoint(g: EonetGeometry): { lon: number; lat: number } | null {
  const coords = g.coordinates;
  const type = (g.type ?? '').toLowerCase();
  if (type === 'point') {
    const c = toCoord(coords);
    return c ? { lon: c[0], lat: c[1] } : null;
  }
  if (type === 'linestring') {
    if (!Array.isArray(coords) || coords.length === 0) return null;
    const c = toCoord(coords[0]);
    return c ? { lon: c[0], lat: c[1] } : null;
  }
  if (type === 'polygon' && Array.isArray(coords) && coords.length > 0) {
    const ring = coords[0];
    if (!Array.isArray(ring) || ring.length === 0) return null;
    // GeoJSON closes a ring by repeating the first vertex; averaging it again
    // biases the representative point toward that corner.
    const vertices = ring.length > 1 && samePair(ring[0], ring[ring.length - 1])
      ? ring.slice(0, -1)
      : ring;
    let sx = 0;
    let sy = 0;
    let n = 0;
    for (const pair of vertices) {
      const c = toCoord(pair);
      if (!c) continue;
      sx += c[0];
      sy += c[1];
      n++;
    }
    return n > 0 ? { lon: sx / n, lat: sy / n } : null;
  }
  return null;
}

/**
 * Storm severity from wind speed in knots (the unit EONET reports for
 * `severeStorms`). Thresholds follow the Saffir–Simpson / tropical-cyclone
 * bands: ≥96 kt (Cat 3+) critical, ≥64 kt (Cat 1+) high, ≥34 kt (tropical
 * storm) medium, below that low. Returns undefined when the unit is not knots
 * so the caller falls back to the text lexicon rather than mis-scaling a value.
 */
export function severityFromWindKnots(knots: number, unit?: string | null): EventSeverity | undefined {
  const u = (unit ?? '').toLowerCase();
  if (u && !u.includes('kt') && !u.includes('knot') && !u.includes('m/s') && !u.includes('mph')) return undefined;
  // Normalize non-knot wind units to knots so one scale applies.
  let kt = knots;
  if (u.includes('m/s')) kt = knots * 1.94384;
  else if (u.includes('mph')) kt = knots * 0.868976;
  if (!Number.isFinite(kt)) return undefined;
  if (kt >= 96) return 'critical';
  if (kt >= 64) return 'high';
  if (kt >= 34) return 'medium';
  return 'low';
}

/**
 * Severity for an EONET event. Earthquake magnitude reuses the established
 * earthquake scale; storms use the wind-speed scale; everything else is scored
 * from the real title/description text. Never guesses a magnitude that is not
 * present.
 */
export function eonetSeverity(
  category: string | undefined,
  magnitude: number | null | undefined,
  unit: string | null | undefined,
  text: string,
): EventSeverity {
  if (typeof magnitude === 'number' && Number.isFinite(magnitude)) {
    if (category === 'earthquake') return classifySeverity(text, 'natural_disaster', magnitude);
    if (category === 'storm') {
      const w = severityFromWindKnots(magnitude, unit);
      if (w) return w;
    }
  }
  return classifySeverity(text, 'natural_disaster');
}

/** Build one normalized event from a raw EONET event, or null without geometry. */
export function normalizeEonetEvent(raw: EonetEvent, retrievedAt: string): NormalizedEvent | null {
  const id = raw.id?.trim();
  if (!id) return null;
  const point = pickLatestGeometry(raw.geometry);
  if (!point) return null;

  const { lon, lat, at } = point;
  const title = raw.title?.trim() || `Natural event — ${id}`;
  const description = raw.description?.trim() || undefined;
  const category = mapEonetCategory(raw.categories?.[0]?.id ?? undefined);

  // The provider's own magnitude (from the chosen observation), when present.
  const latestGeom = latestGeometryWithMagnitude(raw.geometry);
  const text = `${title} ${description ?? ''} ${raw.categories?.map((c) => c.title ?? '').join(' ') ?? ''}`;
  const severity = eonetSeverity(category, latestGeom?.magnitudeValue, latestGeom?.magnitudeUnit, text);

  const country = resolveFireCountry(lon, lat);

  // The EONET event link is unique per event, so it is safe as the source URL
  // (it becomes the stable article-identity key). The corroborating agency
  // sources are recorded by id/name only — a shared agency URL must not fuse
  // unrelated events.
  const agencySources = (raw.sources ?? [])
    .filter((s) => s && (s.id || s.source))
    .slice(0, 12)
    .map((s) => ({
      id: s.id ? `eonet:${s.id}` : `eonet:${(s.source ?? 'source').toLowerCase()}`,
      name: s.source ?? s.id ?? 'EONET source',
      publishedAt: at ?? undefined,
    }));

  const publishedAt = at && !Number.isNaN(Date.parse(at)) ? new Date(Date.parse(at)).toISOString() : retrievedAt;

  const base: NormalizedEvent = {
    dedupKey: '',
    title,
    summary: description,
    placeName: country?.name,
    // Coordinates come from the provider's observation geometry.
    geoMethod: 'provider',
    eventType: 'natural_disaster',
    category,
    severity,
    channels: classifyChannels(text),
    commodities: classifyCommodities(text),
    sectors: classifySectors(text),
    securities: [],
    countries: country ? [country.iso2] : [],
    lon,
    lat,
    confidence: 0.5,
    // Primary + any corroborating agencies EONET cites. At least 1 (EONET).
    sourceCount: agencySources.length + 1,
    sources: [
      {
        id: EONET_SOURCE_ID,
        name: 'NASA EONET',
        url: raw.link ?? undefined,
        publishedAt,
      },
      ...agencySources,
    ],
    primarySource: EONET_SOURCE_ID,
    // EONET's own event id is the provider-stated identity. Two events with
    // different ids are different events, whatever their titles look like.
    clusterSignature: `${EONET_SOURCE_ID}:${id}`,
    publishedAt,
    firstSeen: retrievedAt,
    lastUpdated: retrievedAt,
    status: 'active',
  };
  base.dedupKey = dedupKeyFor(base);
  base.confidence = confidenceOf(base);
  return base;
}

/** Return the observation with a numeric magnitude (prefer the most recent). */
function latestGeometryWithMagnitude(geometries: EonetGeometry[] | undefined): EonetGeometry | undefined {
  if (!geometries || geometries.length === 0) return undefined;
  const withMag = geometries.filter(
    (g) => typeof g.magnitudeValue === 'number' && Number.isFinite(g.magnitudeValue),
  );
  if (withMag.length === 0) return undefined;
  return withMag.sort((a, b) => {
    const ta = Date.parse(a.date ?? '');
    const tb = Date.parse(b.date ?? '');
    if (Number.isNaN(ta)) return 1;
    if (Number.isNaN(tb)) return -1;
    return tb - ta;
  })[0];
}

/** Convert a raw EONET batch into normalized events. */
export function buildEonetEvents(records: RawEvent[]): NormalizedEvent[] {
  const out: NormalizedEvent[] = [];
  for (const record of records) {
    const raw = record.raw as EonetEvent;
    const event = normalizeEonetEvent(raw, record.retrievedAt);
    if (event) out.push(event);
  }
  return out;
}

/** Map an hour window to EONET's `days` parameter (bounded). */
export function daysForHours(hours: number): number {
  return Math.min(EONET_MAX_DAYS, Math.max(1, Math.ceil(hours / 24)));
}

export const eonetSource: EventSource = {
  id: EONET_SOURCE_ID,
  name: 'NASA EONET (natural events)',
  capabilities: ['NATURAL_EVENTS'],
  requiresCredentials: false,
  isConfigured: () => true,

  async fetch(query: SourceQuery): Promise<RawEvent[]> {
    const url = `${EONET_BASE}?status=open&days=${daysForHours(query.hours)}`;
    // One bounded retry: EONET is normally fast and reliable, but the same
    // transport cap that occasionally clips FIRMS can clip it too, and a
    // transient miss should not blank the whole hazard layer for a cycle.
    let lastError: unknown;
    for (let attempt = 0; attempt < EONET_ATTEMPTS; attempt++) {
      try {
        const res = await safeGet({ url, timeoutMs: query.timeoutMs ?? 10_000 });
        if (res.status < 200 || res.status >= 300) {
          throw new OutboundError('network', `EONET HTTP ${res.status}`);
        }
        let parsed: EonetResponse;
        try {
          parsed = JSON.parse(res.text) as EonetResponse;
        } catch {
          throw new OutboundError('network', 'EONET returned non-JSON');
        }
        const retrievedAt = new Date().toISOString();
        const events = parsed.events ?? [];
        return events.map((event) => ({
          sourceId: EONET_SOURCE_ID,
          sourceName: 'NASA EONET',
          raw: event,
          retrievedAt,
        }));
      } catch (err) {
        lastError = err;
        const transient = err instanceof OutboundError && (err.code === 'timeout' || err.code === 'network');
        if (!transient || attempt === EONET_ATTEMPTS - 1) break;
        await new Promise((r) => setTimeout(r, EONET_RETRY_DELAY_MS));
      }
    }
    throw lastError instanceof Error
      ? lastError
      : new OutboundError('network', 'EONET fetch failed');
  },

  normalize(records: RawEvent[]): NormalizedEvent[] {
    return buildEonetEvents(records);
  },
};
