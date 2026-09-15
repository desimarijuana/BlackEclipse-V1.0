// ── Investor Eye — geo aggregation ──────────────────────────────────────────
// Pure helpers that keep the browser payload small (spec §27/§45). When many
// events share a location, they are snapped to a grid and aggregated into one
// weighted datum instead of rendering thousands of overlapping points.

import type { EventSeverity } from './types';
import { SEVERITY_RANK } from './classify';

export interface GeoPoint {
  lon: number;
  lat: number;
  severity?: EventSeverity;
  weight?: number;
}

export interface GeoCluster<T extends GeoPoint> {
  lon: number;
  lat: number;
  count: number;
  /** Highest severity present in the cluster. */
  maxSeverity: EventSeverity;
  /** Sum of member weights (defaults to count when unset). */
  weight: number;
  /** Representative members (bounded). */
  members: T[];
}

const GRID_DEGREES: Record<'low' | 'medium' | 'high', number> = {
  low: 2,     // whole world zoomed out — ~200 km cells
  medium: 0.5, // ~55 km cells
  high: 0.1,  // ~11 km cells
};

function gridKey(lon: number, lat: number, cell: number): string {
  const gx = Math.floor(lon / cell);
  const gy = Math.floor(lat / cell);
  return `${gx}:${gy}`;
}

/**
 * Snap points to a grid and aggregate. `maxMembers` bounds the representatives
 * carried per cluster (the map only needs coordinates + a label).
 */
export function aggregatePoints<T extends GeoPoint>(
  points: T[],
  zoom: 'low' | 'medium' | 'high' = 'low',
  maxMembers = 25,
): GeoCluster<T>[] {
  const cell = GRID_DEGREES[zoom];
  const buckets = new Map<string, GeoCluster<T>>();
  for (const p of points) {
    const key = gridKey(p.lon, p.lat, cell);
    const existing = buckets.get(key);
    const weight = p.weight ?? 1;
    const sev = p.severity ?? 'low';
    if (!existing) {
      buckets.set(key, {
        lon: p.lon,
        lat: p.lat,
        count: 1,
        maxSeverity: sev,
        weight,
        members: [p],
      });
      continue;
    }
    existing.count++;
    existing.weight += weight;
    if (SEVERITY_RANK[sev] > SEVERITY_RANK[existing.maxSeverity]) existing.maxSeverity = sev;
    if (existing.members.length < maxMembers) existing.members.push(p);
  }
  return [...buckets.values()];
}

/** Choose an aggregation zoom from the event count (keeps render bounded). */
export function zoomForCount(count: number): 'low' | 'medium' | 'high' {
  if (count > 4000) return 'low';
  if (count > 800) return 'medium';
  return 'high';
}
