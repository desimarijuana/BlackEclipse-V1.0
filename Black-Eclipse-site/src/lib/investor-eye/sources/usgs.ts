// ── Investor Eye — USGS source ───────────────────────────────────────────────
// Free public earthquake feed (no key). Earthquakes are a real, precisely
// geolocated natural event with an objective magnitude, so they are the ideal
// proof that the event model handles point data — and they anchor the
// "natural events" layer in Phase 2.
//
// Transport goes through the shared `safeGet`.

import { safeGet, OutboundError } from '@/lib/connectors/security';
import { classifyChannels, classifyCommodities, classifySectors, classifySeverity } from '../classify';
import { extractCountries, nearestCountry, type CountryDef } from '../countries';
import { dedupKeyFor } from '../dedup';
import { confidenceOf } from '../cluster';
import type { EventSource, NormalizedEvent, RawEvent, SourceQuery } from '../types';

export const USGS_SOURCE_ID = 'usgs';

// USGS `place` is "N km DIR of <locality>". Many US quakes name only a state,
// and a state name is far more reliable than a nearest-centroid guess (the US
// centroid sits in Kansas, so "Texas" would otherwise resolve to Mexico).
const US_STATES = new Set([
  'alabama', 'alaska', 'arizona', 'arkansas', 'california', 'colorado',
  'connecticut', 'delaware', 'florida', 'georgia', 'hawaii', 'idaho',
  'illinois', 'indiana', 'iowa', 'kansas', 'kentucky', 'louisiana', 'maine',
  'maryland', 'massachusetts', 'michigan', 'minnesota', 'mississippi',
  'missouri', 'montana', 'nebraska', 'nevada', 'new hampshire', 'new jersey',
  'new mexico', 'new york', 'north carolina', 'north dakota', 'ohio',
  'oklahoma', 'oregon', 'pennsylvania', 'puerto rico', 'rhode island',
  'south carolina', 'south dakota', 'tennessee', 'texas', 'utah', 'vermont',
  'virginia', 'washington', 'west virginia', 'wisconsin', 'wyoming',
]);

/**
 * Resolve the country of a USGS event. Preference order:
 *   1. a country named in the `place` text,
 *   2. a US state named in the `place` text,
 *   3. the nearest gazetteer centroid — but ONLY within a tight radius, so a
 *      remote quake is left un-tagged rather than attributed to a distant
 *      country. The precise lon/lat is always kept either way.
 */
export function resolveQuakeCountry(place: string, lon: number, lat: number): CountryDef | undefined {
  const named = extractCountries(place);
  if (named.length > 0) return named[0];
  const lower = place.toLowerCase();
  for (const state of US_STATES) {
    if (lower.includes(state)) {
      return { iso2: 'US', iso3: 'USA', name: 'United States', region: 'North America', lon, lat };
    }
  }
  const near = nearestCountry(lon, lat);
  if (!near) return undefined;
  const dx = (near.lon - lon) * Math.cos((((near.lat + lat) / 2) * Math.PI) / 180);
  const dy = near.lat - lat;
  const distance = Math.sqrt(dx * dx + dy * dy);
  // ~8 degrees (~900 km) is generous but keeps ocean/remote quakes unlabelled.
  return distance <= 8 ? near : undefined;
}

// Summary feeds are fixed, free, and already filtered by magnitude/window.
const FEEDS = {
  '1h': 'https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_hour.geojson',
  '1d': 'https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson',
  '7d': 'https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson',
} as const;

function feedForHours(hours: number): string {
  if (hours <= 2) return FEEDS['1h'];
  if (hours <= 36) return FEEDS['1d'];
  return FEEDS['7d'];
}

interface UsgsFeature {
  id?: string;
  properties?: {
    mag?: number | null;
    place?: string | null;
    time?: number | null;
    url?: string | null;
    title?: string | null;
    tsunami?: number | null;
  };
  geometry?: { type?: string; coordinates?: number[] };
}

interface UsgsResponse {
  features?: UsgsFeature[];
}

/** Build one normalized earthquake event, or null if coordinates are missing. */
export function normalizeQuake(feature: UsgsFeature, retrievedAt: string): NormalizedEvent | null {
  const coords = feature.geometry?.coordinates;
  if (!coords || coords.length < 2) return null;
  const [lon, lat] = coords;
  if (typeof lon !== 'number' || typeof lat !== 'number') return null;

  const props = feature.properties ?? {};
  const mag = typeof props.mag === 'number' ? props.mag : undefined;
  const place = props.place ?? 'Unknown location';
  const title = props.title ?? (mag !== undefined ? `M ${mag.toFixed(1)} earthquake — ${place}` : `Earthquake — ${place}`);
  const publishedAt = props.time ? new Date(props.time).toISOString() : retrievedAt;

  // Country resolution prefers the place text, then US states, then a tight
  // centroid match (see resolveQuakeCountry). The precise point is always kept.
  const country = resolveQuakeCountry(place, lon, lat);

  const base: NormalizedEvent = {
    dedupKey: '',
    title,
    summary: place,
    placeName: place,
    // USGS reports an exact epicentre — the strongest geo provenance.
    geoMethod: 'provider',
    eventType: 'natural_disaster',
    severity: classifySeverity(title, 'natural_disaster', mag),
    channels: classifyChannels(title),
    commodities: classifyCommodities(title),
    sectors: classifySectors(title),
    securities: [],
    countries: country ? [country.iso2] : [],
    lon,
    lat,
    confidence: 0.5,
    sourceCount: 1,
    sources: [
      {
        id: USGS_SOURCE_ID,
        name: 'USGS',
        url: props.url ?? undefined,
        publishedAt,
      },
    ],
    primarySource: USGS_SOURCE_ID,
    // A USGS feature id identifies one physical quake. It must never fuzzy-merge
    // with news coverage of quakes, nor two distinct quakes near each other.
    ...(feature.id ? { clusterSignature: `${USGS_SOURCE_ID}:${feature.id}` } : {}),
    publishedAt,
    firstSeen: retrievedAt,
    lastUpdated: retrievedAt,
    status: 'active',
  };
  base.dedupKey = dedupKeyFor(base);
  base.confidence = confidenceOf(base);
  return base;
}

export const usgsSource: EventSource = {
  id: USGS_SOURCE_ID,
  name: 'USGS (earthquakes)',
  capabilities: ['NATURAL_EVENTS'],
  requiresCredentials: false,
  isConfigured: () => true,

  async fetch(query: SourceQuery): Promise<RawEvent[]> {
    const url = feedForHours(query.hours);
    const res = await safeGet({ url, timeoutMs: query.timeoutMs ?? 10_000 });
    if (res.status < 200 || res.status >= 300) {
      throw new OutboundError('network', `USGS HTTP ${res.status}`);
    }
    let parsed: UsgsResponse;
    try {
      parsed = JSON.parse(res.text) as UsgsResponse;
    } catch {
      throw new OutboundError('network', 'USGS returned non-JSON');
    }
    const retrievedAt = new Date().toISOString();
    return (parsed.features ?? []).map((feature) => ({
      sourceId: USGS_SOURCE_ID,
      sourceName: 'USGS',
      raw: feature,
      retrievedAt,
    }));
  },

  normalize(records: RawEvent[]): NormalizedEvent[] {
    const events: NormalizedEvent[] = [];
    for (const record of records) {
      const event = normalizeQuake(record.raw as UsgsFeature, record.retrievedAt);
      if (event) events.push(event);
    }
    return events;
  },
};
