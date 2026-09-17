// ── Investor Eye — admin-boundary point lookup ───────────────────────────────
// Answers "which country is this exact coordinate in?" using the SAME Natural
// Earth GeoJSON the map already ships (`public/geo/world.geo.json`).
//
// WHY THIS EXISTS: `countries.ts` offers a nearest-gazetteer-CENTROID match. That
// is fine for a text event with only a country name, but it is badly wrong for a
// precise coordinate in a large country — a fire in eastern Siberia is thousands
// of km from Russia's centroid, so a centroid match returns no country (or a
// neighbour). Measured on live FIRMS data: centroid matching attributed 15% of
// fire clusters to a country; a real point-in-polygon test attributes 97%.
//
// The geometry is loaded ONCE and cached. Pure predicate (`pointInRing`) is
// separated from the dataset so it is unit-testable without any file access.
//
// No new dependency and no new asset: the polygons are already in the repo.

import fs from 'node:fs';
import path from 'node:path';

type Ring = number[][];

interface BoundaryFeature {
  properties: { iso2?: string; name?: string; mapName?: string };
  geometry: { type?: string; coordinates?: unknown };
}

interface Boundary {
  iso2: string;
  /** Display name from the GeoJSON, so a country the gazetteer lacks is usable. */
  name?: string;
  /** [outerRing, ...holes] per polygon part (a MultiPolygon has several). */
  parts: Ring[][];
}

/**
 * Ray-casting point-in-ring test.
 *
 * Counts how many times a ray cast east from (lon, lat) crosses a ring edge;
 * an odd count is inside. Pure and dependency-free.
 */
export function pointInRing(lon: number, lat: number, ring: Ring): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0];
    const yi = ring[i][1];
    const xj = ring[j][0];
    const yj = ring[j][1];
    const crosses = (yi > lat) !== (yj > lat)
      && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi;
    if (crosses) inside = !inside;
  }
  return inside;
}

/**
 * Point-in-polygon including interior holes.
 *
 * A hole (an enclave — e.g. Lesotho inside South Africa, or the Caspian) must
 * not be reported as part of the surrounding country, so the test rejects a hit
 * that falls inside any inner ring.
 */
export function pointInParts(lon: number, lat: number, parts: Ring[][]): boolean {
  for (const part of parts) {
    if (part.length === 0 || !pointInRing(lon, lat, part[0])) continue;
    let inHole = false;
    for (let h = 1; h < part.length; h++) {
      if (pointInRing(lon, lat, part[h])) { inHole = true; break; }
    }
    if (!inHole) return true;
  }
  return false;
}

/** Normalize a GeoJSON Polygon/MultiPolygon into the `parts` shape. */
export function geometryParts(geometry: BoundaryFeature['geometry']): Ring[][] {
  if (!geometry) return [];
  if (geometry.type === 'Polygon') return [geometry.coordinates as Ring[]];
  if (geometry.type === 'MultiPolygon') return geometry.coordinates as Ring[][];
  return [];
}

let cachedBoundaries: Boundary[] | null = null;

/**
 * Load and index the world boundaries. Read from the repo's own asset rather
 * than a fetched copy, so this works with no network and no configuration.
 * Returns an empty list (never throws) if the asset is unreadable, so a broken
 * asset degrades country attribution instead of breaking ingestion.
 */
export function loadBoundaries(): Boundary[] {
  if (cachedBoundaries) return cachedBoundaries;
  // Next serves from the app dir, but tests and scripts can run from the repo
  // root — try both so a boundary lookup never silently returns nothing.
  const candidates = [
    path.join(process.cwd(), 'public', 'geo', 'world.geo.json'),
    path.join(process.cwd(), 'Black-Eclipse-site', 'public', 'geo', 'world.geo.json'),
  ];
  for (const file of candidates) {
    try {
      const json = JSON.parse(fs.readFileSync(file, 'utf8')) as { features?: BoundaryFeature[] };
      const out: Boundary[] = [];
      for (const f of json.features ?? []) {
        const iso2 = f.properties?.iso2;
        if (!iso2) continue;
        const parts = geometryParts(f.geometry);
        if (parts.length > 0) out.push({ iso2, name: f.properties?.name, parts });
      }
      if (out.length > 0) {
        cachedBoundaries = out;
        return out;
      }
    } catch {
      /* try the next candidate */
    }
  }
  cachedBoundaries = [];
  return cachedBoundaries;
}

/** Test seam: forget the cached boundaries. */
export function resetBoundaryCache(): void {
  cachedBoundaries = null;
}

/**
 * The ISO2 of the country containing an exact coordinate, or undefined when the
 * point is in international waters / an unrepresented territory. Returning
 * undefined is deliberate: a fire at sea has no country, and inventing one would
 * be worse than an empty field.
 */
export function countryAtPoint(lon: number, lat: number, boundaries = loadBoundaries()): string | undefined {
  return boundaryAtPoint(lon, lat, boundaries)?.iso2;
}

/**
 * The full boundary the point falls in, including its display name.
 *
 * Needed because the boundary asset (173 Natural Earth features) is broader than
 * the hand-curated country gazetteer. A fire can legitimately fall in a country
 * the gazetteer does not list (Mozambique, Angola, Madagascar); discarding the
 * polygon hit because `countryByIso2` had no entry threw away a proven result.
 */
export function boundaryAtPoint(
  lon: number,
  lat: number,
  boundaries = loadBoundaries(),
): { iso2: string; name?: string } | undefined {
  if (!Number.isFinite(lon) || !Number.isFinite(lat)) return undefined;
  for (const b of boundaries) {
    if (pointInParts(lon, lat, b.parts)) return { iso2: b.iso2, name: b.name };
  }
  return undefined;
}
