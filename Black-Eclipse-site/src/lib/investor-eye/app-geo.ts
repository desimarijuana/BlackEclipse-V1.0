// ── Investor Eye — geography loader ──────────────────────────────────────────
// Loads the slimmed Natural Earth GeoJSON vendored at `public/geo/world.geo.json`
// (produced by `scripts/fetch-world-geo.mjs`) and registers it with ECharts.
//
// Loaded once and cached in-module so switching layers/tabs never refetches the
// 175 KB asset. The dataset is NOT embedded in a component.

import * as echarts from 'echarts';
import { WORLD_MAP_NAME } from './map-echarts';

const GEO_URL = '/geo/world.geo.json';

let loadPromise: Promise<GeoFeature[]> | null = null;
let registered = false;

export interface GeoFeature {
  type: 'Feature';
  properties: { name: string; mapName: string; iso2: string; iso3: string };
  geometry: unknown;
}

/** Fetch the GeoJSON (cached). Rejects only on a real network/parse failure. */
export function loadWorldGeo(): Promise<GeoFeature[]> {
  if (loadPromise) return loadPromise;
  loadPromise = (async () => {
    const res = await fetch(GEO_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status} loading ${GEO_URL}`);
    const json = (await res.json()) as { features?: GeoFeature[] };
    if (!Array.isArray(json.features) || json.features.length === 0) {
      throw new Error('World GeoJSON had no features');
    }
    return json.features;
  })();
  return loadPromise;
}

/**
 * Ensure the world map is registered with ECharts. Idempotent.
 * ECharts `registerMap` keys features by `properties.name`, so we register the
 * raw FeatureCollection (the `name` values are what click events return).
 */
export async function ensureWorldMapRegistered(): Promise<GeoFeature[]> {
  const features = await loadWorldGeo();
  if (!registered) {
    echarts.registerMap(WORLD_MAP_NAME, { type: 'FeatureCollection', features } as never);
    registered = true;
  }
  return features;
}

/** Feature name (what ECharts returns on click) → ISO2. */
export function iso2ForFeatureName(features: GeoFeature[], name: string): string | undefined {
  const f = features.find((x) => x.properties.name === name || x.properties.mapName === name);
  return f?.properties.iso2;
}
