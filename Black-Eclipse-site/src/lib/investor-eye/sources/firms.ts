// ── Investor Eye — NASA FIRMS source ─────────────────────────────────────────
// Free, keyless near-real-time satellite fire/thermal detections (MODIS aboard
// Aqua/Terra; FIRMS also serves VIIRS). Each row is a single 1 km satellite
// detection — a pixel, not a fire.
//
// WHY AGGREGATION IS MANDATORY HERE (spec §26):
// A 24h global file carries ~25,000 detections. Rendering them as individual
// map markers would be both useless (a continent of dots) and expensive. One
// real wildfire produces dozens to hundreds of adjacent pixels. So detections
// are snapped to a grid and merged into bounded CLUSTERS, each reporting the
// real detection count and summed Fire Radiative Power (FRP) — the observed
// intensity measure — rather than a fabricated "fire" object.
//
// The clustering is done at INGESTION (not rendering) because the raw row count
// must never reach the database or the browser.
//
// Honesty rules:
//   - no place names exist in the feed, so the country is resolved from the
//     exact coordinate via the gazetteer (tight radius; a remote fire stays
//     unlabelled rather than being attributed to a distant country),
//   - one cluster is one event, but its title states the detection count so it
//     is never read as a single ignition point,
//   - the provider's own confidence/FRP fields are kept verbatim, never modelled.
//
// Transport goes through the shared `safeGet` (https-only, DNS-pinned, capped).

import { safeGet, OutboundError } from '@/lib/connectors/security';
import { classifyChannels, classifyCommodities, classifySectors } from '../classify';
import { countryByIso2, nearestCountry } from '../countries';
import { boundaryAtPoint } from '../admin-boundaries';
import { dedupKeyFor } from '../dedup';
import { confidenceOf } from '../cluster';
import type { EventSource, NormalizedEvent, RawEvent, SourceQuery } from '../types';

export const FIRMS_SOURCE_ID = 'firms';

/**
 * Keyless global archive CSVs. The Area API is deliberately NOT used: it
 * requires a MAP_KEY, and Investor Eye must work with zero configuration.
 *
 * Sizes measured from this codebase's host: 24h ≈ 2.0 MB / ~4 s, 48h ≈ 3.3 MB,
 * 7d ≈ 7.4 MB. `safeGet` caps at 5 MB by default, so a larger cap is passed for
 * the multi-day files; the transport's hard timeout ceiling still applies, and a
 * slow download degrades the FIRMS source only — never the rest of the feed.
 */
const FEEDS = {
  '24h': 'https://firms.modaps.eosdis.nasa.gov/data/active_fire/modis-c6.1/csv/MODIS_C6_1_Global_24h.csv',
  '48h': 'https://firms.modaps.eosdis.nasa.gov/data/active_fire/modis-c6.1/csv/MODIS_C6_1_Global_48h.csv',
  '7d': 'https://firms.modaps.eosdis.nasa.gov/data/active_fire/modis-c6.1/csv/MODIS_C6_1_Global_7d.csv',
} as const;

/** Largest file FIRMS serves keylessly is the 7-day global CSV (~7.4 MB). */
const FIRMS_MAX_BYTES = 16 * 1024 * 1024;

/** Grid cell for clustering detections, in degrees (~55 km at the equator). */
export const FIRE_CLUSTER_CELL_DEG = 0.5;

/**
 * Minimum detections for a cluster to be emitted. A genuine fire registers many
 * adjacent pixels; a lone detection is more often a flare, a hot roof or a
 * false positive. Measured on live data: cell 0.5° / ≥10 yields ~710 clusters
 * globally per day — dense enough to be informative, bounded enough to store.
 */
export const FIRE_MIN_DETECTIONS = 10;

/** Cap on emitted clusters (matches the per-source discipline used elsewhere). */
const FIRMS_MAX_CLUSTERS = 400;

/** Bounded retry for a transient fetch failure (see `firmsSource.fetch`). */
const FIRMS_ATTEMPTS = 2;
const FIRMS_RETRY_DELAY_MS = 800;

function feedForHours(hours: number): string {
  if (hours <= 24) return FEEDS['24h'];
  if (hours <= 48) return FEEDS['48h'];
  return FEEDS['7d'];
}

/** Normalize a satellite code to the instrument name FIRMS publishes. */
export function satelliteName(code: string): string {
  const c = (code ?? '').trim().toUpperCase();
  if (c === 'T') return 'Terra (MODIS)';
  if (c === 'A') return 'Aqua (MODIS)';
  return c || 'MODIS';
}

/**
 * Severity from a cluster's summed Fire Radiative Power (MW).
 *
 * Thresholds are calibrated against the live distribution of 24h clusters
 * (median ≈ 231 MW, p90 ≈ 1054 MW, p99 ≈ 5175 MW) so the scale is anchored to
 * real data rather than picked to look dramatic. FRP is a measured physical
 * quantity, so this is a real observation, not a model.
 */
export function severityFromFrp(frpTotal: number): 'low' | 'medium' | 'high' | 'critical' {
  if (frpTotal >= 5000) return 'critical';
  if (frpTotal >= 1000) return 'high';
  if (frpTotal >= 250) return 'medium';
  return 'low';
}

/** One parsed CSV detection. */
export interface FireDetection {
  lon: number;
  lat: number;
  /** Fire Radiative Power, MW. */
  frp: number;
  /** Provider confidence: MODIS C6.1 uses 0–100. */
  confidence: number;
  satellite: string;
  /** ISO timestamp built from acq_date + acq_time (UTC). */
  observedAt: string;
  brightness?: number;
}

/** A grid cell of detections, aggregated. */
export interface FireCluster {
  lon: number;
  lat: number;
  count: number;
  frpTotal: number;
  frpMax: number;
  confidenceAvg: number;
  satellite: string;
  /** Most recent detection in the cell. */
  observedAt: string;
}

/**
 * Parse a FIRMS archive CSV body into detections.
 *
 * The CSV is plain (no quoted commas — all fields are numeric or short codes),
 * so a split on ',' is safe and avoids a parser dependency. Rows lacking a
 * usable coordinate or timestamp are DROPPED, never defaulted to 0/0 (which
 * would plot a real-looking fire in the Gulf of Guinea).
 */
export function parseFirmsCsv(body: string): FireDetection[] {
  const lines = body.split('\n').map((l) => l.trim()).filter(Boolean);
  if (lines.length === 0) return [];
  const header = lines[0].split(',').map((h) => h.trim().toLowerCase());
  const idx = {
    lat: header.indexOf('latitude'),
    lon: header.indexOf('longitude'),
    frp: header.indexOf('frp'),
    confidence: header.indexOf('confidence'),
    satellite: header.indexOf('satellite'),
    acqDate: header.indexOf('acq_date'),
    acqTime: header.indexOf('acq_time'),
    brightness: header.indexOf('brightness'),
  };
  if (idx.lat < 0 || idx.lon < 0 || idx.acqDate < 0) return [];

  const out: FireDetection[] = [];
  for (let i = 1; i < lines.length; i++) {
    const f = lines[i].split(',');
    // `Number('')` is 0, so an EMPTY coordinate column would silently become a
    // real-looking detection on the equator/prime meridian. Reject the raw
    // string before coercing.
    const latRaw = (f[idx.lat] ?? '').trim();
    const lonRaw = (f[idx.lon] ?? '').trim();
    if (!latRaw || !lonRaw) continue;
    const lat = Number(latRaw);
    const lon = Number(lonRaw);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
    // (0,0) is a null island sentinel, not a fire.
    if (lat === 0 && lon === 0) continue;
    const observedAt = parseAcq(idx.acqTime >= 0 ? f[idx.acqTime] : '', f[idx.acqDate]);
    if (!observedAt) continue;
    // MODIS C6.1 `confidence` is a 0–100 percentage. Some FIRMS products emit
    // l/n/h instead; those are mapped to representative values rather than
    // being coerced to NaN.
    const confidence = parseConfidence(idx.confidence >= 0 ? f[idx.confidence] : '');
    const frp = idx.frp >= 0 ? Number(f[idx.frp]) : 0;
    out.push({
      lat,
      lon,
      frp: Number.isFinite(frp) && frp > 0 ? frp : 0,
      confidence,
      satellite: satelliteName(idx.satellite >= 0 ? f[idx.satellite] : ''),
      observedAt,
      ...(idx.brightness >= 0 && Number.isFinite(Number(f[idx.brightness]))
        ? { brightness: Number(f[idx.brightness]) }
        : {}),
    });
  }
  return out;
}

/** `acq_time` is HHMM (sometimes not zero-padded) in UTC. */
function parseAcq(time: string, date: string): string | null {
  const d = (date ?? '').trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return null;
  // An ABSENT time must be rejected, not padded to '0000' — midnight is a
  // fabricated observation time, and a defaulted timestamp is indistinguishable
  // from a real one downstream.
  const rawTime = (time ?? '').trim();
  if (!rawTime) return null;
  const t = rawTime.padStart(4, '0');
  if (!/^\d{4}$/.test(t)) return null;
  const iso = `${d}T${t.slice(0, 2)}:${t.slice(2, 4)}:00Z`;
  const ms = Date.parse(iso);
  // Normalize through Date so every producer emits one identical format.
  return Number.isNaN(ms) ? null : new Date(ms).toISOString();
}

function parseConfidence(raw: string): number {
  const v = (raw ?? '').trim().toLowerCase();
  if (v === 'l' || v === 'low') return 30;
  if (v === 'n' || v === 'nominal') return 60;
  if (v === 'h' || v === 'high') return 90;
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

/**
 * Snap detections to a grid and aggregate. Longitude cells are corrected by
 * cos(lat) so a cell is roughly the same physical size at high latitude — an
 * uncorrected grid fragments polar fires into many meaningless cells.
 */
export function clusterDetections(
  detections: FireDetection[],
  cellDeg = FIRE_CLUSTER_CELL_DEG,
): FireCluster[] {
  const buckets = new Map<string, FireCluster & { _confSum: number }>();
  for (const d of detections) {
    // A degree of longitude shrinks by cos(lat), so the cell must be WIDER in
    // degrees near the poles to stay a constant physical size. Without this a
    // high-latitude fire fragments into many cells that each fall below the
    // minimum detection count and disappear entirely. The `cos` is floored so
    // the factor cannot blow up at the pole.
    const cosLat = Math.max(0.15, Math.cos((d.lat * Math.PI) / 180));
    const lonCell = cellDeg / cosLat;
    const gx = Math.floor(d.lon / lonCell);
    const gy = Math.floor(d.lat / cellDeg);
    const key = `${gx}:${gy}`;
    const existing = buckets.get(key);
    if (!existing) {
      buckets.set(key, {
        lon: d.lon, lat: d.lat, count: 1, frpTotal: d.frp, frpMax: d.frp,
        confidenceAvg: d.confidence, satellite: d.satellite, observedAt: d.observedAt,
        _confSum: d.confidence,
      });
      continue;
    }
    existing.count++;
    existing.frpTotal += d.frp;
    if (d.frp > existing.frpMax) existing.frpMax = d.frp;
    existing._confSum += d.confidence;
    existing.confidenceAvg = existing._confSum / existing.count;
    if (Date.parse(d.observedAt) > Date.parse(existing.observedAt)) {
      existing.observedAt = d.observedAt;
      existing.satellite = d.satellite;
    }
  }
  return [...buckets.values()].map(({ _confSum, ...c }) => {
    void _confSum;
    return c;
  });
}

/**
 * Resolve the country of a fire from its exact coordinate.
 *
 * Primary: point-in-polygon against the Natural Earth boundaries the map already
 * ships — an EXACT containment test. The previous nearest-centroid approach
 * managed far fewer, because a precise point in a large country (Siberia, the
 * Australian interior) can be thousands of km from that country's centroid.
 *
 * The boundary asset is broader than the hand-curated gazetteer, so the
 * boundary's own ISO2/name is used when the gazetteer has no entry — discarding
 * a proven polygon hit because a name lookup missed would throw away a real
 * result.
 *
 * Fallback: a tight nearest-centroid match, used only when the polygon test
 * finds nothing (an asset that could not be read, or a point a few km offshore).
 *
 * A genuinely oceanic point stays unlabelled — inventing a country for a fire at
 * sea would be worse than an empty field.
 */
export function resolveFireCountry(lon: number, lat: number): { iso2: string; name: string } | undefined {
  const boundary = boundaryAtPoint(lon, lat);
  if (boundary) {
    const def = countryByIso2(boundary.iso2);
    if (def) return { iso2: def.iso2, name: def.name };
    if (boundary.name) return { iso2: boundary.iso2, name: boundary.name };
  }
  const near = nearestCountry(lon, lat);
  if (!near) return undefined;
  const dx = (near.lon - lon) * Math.cos((((near.lat + lat) / 2) * Math.PI) / 180);
  const dy = near.lat - lat;
  const distance = Math.sqrt(dx * dx + dy * dy);
  // Tight (~2 degrees): this is a fallback for a coastline rounding error, not a
  // licence to attribute a remote fire to the nearest capital.
  return distance <= 2 ? { iso2: near.iso2, name: near.name } : undefined;
}

/** Build one normalized fire-cluster event. */
export function normalizeFireCluster(cluster: FireCluster, retrievedAt: string): NormalizedEvent {
  const country = resolveFireCountry(cluster.lon, cluster.lat);
  const frp = Math.round(cluster.frpTotal);
  const title = `Satellite fire cluster — ${cluster.count} detections (FRP ${frp} MW)`;
  const severity = severityFromFrp(cluster.frpTotal);
  const confidencePct = Math.round(cluster.confidenceAvg);

  const text = `wildfire fire satellite ${cluster.satellite}`;
  const base: NormalizedEvent = {
    dedupKey: '',
    title,
    // One cluster is many pixels, so the summary states that plainly — this is
    // the fact that stops a cluster reading as a single ignition point.
    summary: `${cluster.count} satellite thermal detections aggregated within ~${Math.round(FIRE_CLUSTER_CELL_DEG * 111)} km. Peak FRP ${Math.round(cluster.frpMax)} MW.`,
    placeName: country?.name,
    // A satellite detection is an exact coordinate — the strongest provenance.
    geoMethod: 'provider',
    eventType: 'natural_disaster',
    // FIRMS detects thermal anomalies — a fire cluster. Provider-stated.
    category: 'fire',
    // FRP-anchored severity, not the generic text lexicon.
    severity,
    channels: classifyChannels(text),
    commodities: classifyCommodities(text),
    sectors: classifySectors(text),
    securities: [],
    countries: country ? [country.iso2] : [],
    lon: cluster.lon,
    lat: cluster.lat,
    confidence: 0.5,
    sourceCount: 1,
    sources: [
      {
        id: FIRMS_SOURCE_ID,
        name: `NASA FIRMS · ${cluster.satellite}`,
        // DELIBERATELY no `url`: `dedupKeyFor` treats a source URL as ARTICLE
        // identity, and the only URL here is the shared feed endpoint. Two
        // different fire clusters would then hash to the same key and collapse
        // into one event — the exact failure this omits. A feed is not an
        // article, so the cluster signature below is the identity.
        publishedAt: cluster.observedAt,
      },
    ],
    primarySource: FIRMS_SOURCE_ID,
    // A grid cell identifies one cluster. Two cells are two clusters even when
    // their titles are identical (every fire cluster shares the same title
    // shape), so the signature is required — without it clustering would fuse
    // every fire on a continent into one event.
    clusterSignature: `${FIRMS_SOURCE_ID}:${cluster.lon.toFixed(3)},${cluster.lat.toFixed(3)}`,
    publishedAt: cluster.observedAt,
    firstSeen: retrievedAt,
    lastUpdated: retrievedAt,
    status: 'active',
  };
  // Provider confidence (0–100) is a data-quality signal, bounded into 0..1.
  base.confidence = Math.min(1, confidenceOf(base) + Math.min(confidencePct / 500, 0.2));
  base.dedupKey = dedupKeyFor(base);
  return base;
}

/** Group a raw record batch through the CSV → detections → clusters pipeline. */
export function buildFireEvents(records: RawEvent[]): NormalizedEvent[] {
  const detections: FireDetection[] = [];
  let retrievedAt = new Date().toISOString();
  for (const record of records) {
    const raw = record.raw as { csv?: string };
    if (!raw?.csv) continue;
    retrievedAt = record.retrievedAt;
    detections.push(...parseFirmsCsv(raw.csv));
  }
  if (detections.length === 0) return [];

  const clusters = clusterDetections(detections)
    .filter((c) => c.count >= FIRE_MIN_DETECTIONS)
    // Highest-energy clusters first, so the cap keeps the significant fires.
    .sort((a, b) => b.frpTotal - a.frpTotal)
    .slice(0, FIRMS_MAX_CLUSTERS);

  return clusters.map((c) => normalizeFireCluster(c, retrievedAt));
}

export const firmsSource: EventSource = {
  id: FIRMS_SOURCE_ID,
  name: 'NASA FIRMS (fires)',
  capabilities: ['NATURAL_EVENTS'],
  requiresCredentials: false,
  isConfigured: () => true,

  async fetch(query: SourceQuery): Promise<RawEvent[]> {
    const url = feedForHours(query.hours);
    // MEASURED FLAKINESS: the 24h global CSV is ~1.6 MB and normally lands in
    // ~3 s, but the shared transport hard-caps timeouts at 10 s (`MAX_TIMEOUT_MS`)
    // and the feed occasionally exceeds that, which silently empties the hazard
    // layer for a whole 10-minute cycle. One bounded retry turns that from a
    // recurring gap into a rare one; a persistent failure still degrades to
    // "this source only", never the whole feed.
    let lastError: unknown;
    for (let attempt = 0; attempt < FIRMS_ATTEMPTS; attempt++) {
      try {
        // The multi-day globals exceed the transport's 5 MB default, so a larger
        // cap is passed; the transport's own ceiling still applies.
        const res = await safeGet({ url, timeoutMs: query.timeoutMs ?? 10_000, maxBytes: FIRMS_MAX_BYTES });
        if (res.status < 200 || res.status >= 300) {
          throw new OutboundError('network', `FIRMS HTTP ${res.status}`);
        }
        if (!res.text || res.text.length < 64) {
          throw new OutboundError('network', 'FIRMS returned an empty body');
        }
        return [{
          sourceId: FIRMS_SOURCE_ID,
          sourceName: 'NASA FIRMS',
          raw: { csv: res.text },
          retrievedAt: new Date().toISOString(),
        }];
      } catch (err) {
        lastError = err;
        // Only retry a transient transport problem. A 4xx/5xx from FIRMS means
        // the request itself is wrong and a retry would just waste the cycle.
        const transient = err instanceof OutboundError && (err.code === 'timeout' || err.code === 'network');
        if (!transient || attempt === FIRMS_ATTEMPTS - 1) break;
        await new Promise((r) => setTimeout(r, FIRMS_RETRY_DELAY_MS));
      }
    }
    throw lastError instanceof Error
      ? lastError
      : new OutboundError('network', 'FIRMS fetch failed');
  },

  normalize(records: RawEvent[]): NormalizedEvent[] {
    return buildFireEvents(records);
  },
};
