// ── Investor Eye — event geo resolution ──────────────────────────────────────
// Decides WHERE an event is plotted, in preference order, and records HOW it was
// decided so the UI can be honest about precision.
//
// The problem this solves: `CountryDef.lon/lat` is a country's GEOGRAPHIC
// CENTROID. That is a fine anchor for a country-wide event, but for a POLICY
// event it is badly wrong — "the Fed raises rates" plotted at the USA centroid
// lands in Kansas; "Brazil's central bank cuts rates" lands in the Amazon.
// Policy, monetary and diplomatic news is reported FROM the capital.
//
// Order:
//   1. a NAMED place in the text (port, chokepoint, city, energy hub)  → `place`
//   2. an exact provider coordinate (GDELT/USGS)                       → `provider`
//   3. the CAPITAL, for policy-type events, when the capital is known  → `capital`
//   4. the country centroid                                            → `centroid`
//
// Pure: callers pass the text and the resolved country, so this is unit-testable
// with no DB and no network.

import { countryByIso2, capitalByIso2, type CountryDef } from './countries';
import { resolvePlace, type Place } from './places';
import type { EventType, NormalizedEvent } from './types';

/** How a coordinate was determined. Extends the original three with `capital`. */
export type GeoMethod = 'provider' | 'place' | 'capital' | 'centroid';

/**
 * Event types that are reported FROM a capital: the story is about a government,
 * a central bank or a regulator, so the capital is the meaningful location.
 *
 * Deliberately excludes `conflict`, `military`, `natural_disaster`, `energy` and
 * `shipping` — those have a real physical location that is usually NOT the
 * capital, and forcing them to the capital would be a regression.
 */
const CAPITAL_CENTRIC_TYPES: ReadonlySet<EventType> = new Set<EventType>([
  'monetary', 'fiscal', 'regulatory', 'diplomatic', 'election', 'sanction', 'trade', 'tariff',
]);

export interface ResolvedLocation {
  lon?: number;
  lat?: number;
  placeName?: string;
  geoMethod?: GeoMethod;
}

/**
 * Resolve the anchor for a text-derived event (news).
 *
 * @param text        Headline + summary used for place matching.
 * @param eventType   Drives whether the capital is an appropriate anchor.
 * @param countries   ISO2 codes already extracted from the event.
 * @param country     The primary resolved country, if any.
 */
export function resolveEventLocation(
  text: string,
  eventType: EventType,
  countries: string[],
  country?: CountryDef,
): ResolvedLocation {
  // 1. A named place is the most specific signal and always wins.
  const place: Place | undefined = resolvePlace(text, countries);
  if (place) {
    return { lon: place.lon, lat: place.lat, placeName: place.name, geoMethod: 'place' };
  }

  // 2. For policy-type events, prefer the capital over the geographic centre.
  if (CAPITAL_CENTRIC_TYPES.has(eventType)) {
    const capital = capitalByIso2(country?.iso2);
    if (capital) {
      return { lon: capital.lon, lat: capital.lat, placeName: capital.name, geoMethod: 'capital' };
    }
  }

  // 3. Fall back to the country centroid (or nothing when the country is unknown).
  if (country) {
    return { lon: country.lon, lat: country.lat, geoMethod: 'centroid' };
  }
  return {};
}

/**
 * Re-derive a stored event's location with the CURRENT rules.
 *
 * Event rows persisted before `capital` existed (or before place resolution was
 * added to a source) keep a stale `geoMethod` and a centroid coordinate. Rather
 * than a migration, resolution is deterministic and cheap, so it is recomputed on
 * read. This is what upgrades historical rows without touching the database.
 *
 * Returns the original values when nothing better can be determined.
 */
export function reResolveEventLocation(event: NormalizedEvent): ResolvedLocation {
  // An exact provider coordinate (GDELT action geo, USGS epicentre) is ground
  // truth — never second-guess it.
  if (event.geoMethod === 'provider' && typeof event.lat === 'number') {
    return { lon: event.lon, lat: event.lat, placeName: event.placeName, geoMethod: 'provider' };
  }

  const text = `${event.title} ${event.summary ?? ''}`;
  const primary = event.countries.length > 0 ? countryByIso2(event.countries[0]) : undefined;
  const resolved = resolveEventLocation(text, event.eventType, event.countries, primary);

  // Only accept an improvement, never a downgrade to "no location".
  if (resolved.geoMethod === undefined && event.lat !== undefined) {
    return { lon: event.lon, lat: event.lat, placeName: event.placeName, geoMethod: event.geoMethod as GeoMethod | undefined };
  }
  // A previously-resolved `place` already beat capital/centroid; keep it.
  if (event.geoMethod === 'place' && resolved.geoMethod !== 'place') {
    return { lon: event.lon, lat: event.lat, placeName: event.placeName, geoMethod: 'place' };
  }
  return resolved;
}

/** Human label for the UI, so precision is never overstated. */
export const GEO_METHOD_LABEL: Record<GeoMethod, string> = {
  provider: 'exact coordinates from source',
  place: 'resolved from a named place',
  capital: 'country capital (policy event)',
  centroid: 'country centre only',
};

/** How much to trust each anchor — higher is more precise. */
export const GEO_METHOD_RANK: Record<GeoMethod, number> = {
  provider: 3, place: 3, capital: 2, centroid: 1,
};
