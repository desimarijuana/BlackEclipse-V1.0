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

// ── Globe surface texture ────────────────────────────────────────────────────
// `echarts-gl`'s `globe` component has NO `map`/`geo` property — it takes a
// raster `baseTexture`. Its built-in default is a bright photographic world
// image, and the previous attempt replaced it with a *solid dark* 16×16 PNG to
// stop the sphere out-shining the pins. The result was an invisible sphere:
// dark texture on a dark background, so the globe read as floating dots.
//
// The fix is to draw the real landmasses ourselves, at runtime, from the SAME
// GeoJSON the 2D map already uses — a dark planet that is unmistakably a globe.
// Equirectangular projection (lon → x, lat → y) is exactly what a globe texture
// expects. Drawn once and cached; no asset to ship, no extra network request.

const TEXTURE_W = 2048;
const TEXTURE_H = 1024;

let texturePromise: Promise<string> | null = null;

/** Draw one ring/polygon path from a ring of [lon, lat] pairs. */
function traceRing(ctx: CanvasRenderingContext2D, ring: ArrayLike<number>, x: (n: number) => number, y: (n: number) => number): void {
  for (let i = 0; i < ring.length; i++) {
    const pair = ring[i] as unknown as [number, number];
    const lon = pair[0];
    const lat = pair[1];
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;
    const px = x(lon);
    const py = y(lat);
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.closePath();
}

/**
 * Normalize a (Multi)Polygon geometry into a list of POLYGONS, where each
 * polygon is a list of rings (outer + holes) and each ring is a list of
 * [lon, lat] pairs.
 *
 * The GeoJSON nesting is easy to get wrong: a Polygon's `coordinates` is
 * already `ring[]` (= one polygon), while a MultiPolygon's is `polygon[]`.
 * Returning rings for one and polygons for the other silently drew nothing.
 */
function geometryPolygons(geometry: unknown): number[][][][] {
  const g = geometry as { type?: string; coordinates?: unknown };
  if (!g || !g.coordinates) return [];
  if (g.type === 'Polygon') return [g.coordinates as number[][][]];
  if (g.type === 'MultiPolygon') return g.coordinates as number[][][][];
  return [];
}

/**
 * Render the world as a dark equirectangular texture for the 3D globe.
 * Resolves to a data URL. Rejects only if a 2D canvas is unavailable (SSR).
 */
export function buildGlobeTexture(features: GeoFeature[]): Promise<string> {
  if (texturePromise) return texturePromise;
  texturePromise = new Promise<string>((resolve, reject) => {
    if (typeof document === 'undefined') {
      reject(new Error('no document'));
      return;
    }
    const canvas = document.createElement('canvas');
    canvas.width = TEXTURE_W;
    canvas.height = TEXTURE_H;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      reject(new Error('no 2d context'));
      return;
    }

    // Ocean: very dark, but not pure black — a pure-black ocean on a black page
    // is what made the sphere invisible before. `#0b1220` reads as water and
    // separates cleanly from the lighter land fill.
    ctx.fillStyle = '#0b1220';
    ctx.fillRect(0, 0, TEXTURE_W, TEXTURE_H);

    // Equirectangular projection with a tiny inset so the ±180 seam is not clipped.
    const x = (lon: number) => ((lon + 180) / 360) * TEXTURE_W;
    const y = (lat: number) => ((90 - lat) / 180) * TEXTURE_H;

    ctx.lineJoin = 'round';
    // Landmasses: one path per feature so borders land crisply on top. The fill
    // is deliberately much lighter than the ocean so the continents (and their
    // shape) are unmistakable at a glance — the whole point of the globe.
    for (const f of features) {
      for (const polygon of geometryPolygons(f.geometry)) {
        ctx.beginPath();
        for (const ring of polygon) traceRing(ctx, ring as unknown as ArrayLike<number>, x, y);
        ctx.fillStyle = '#2b3442';
        ctx.fill();
        ctx.strokeStyle = 'rgba(125,211,252,0.55)';
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    }

    // A faint graticule so rotation is legible even over open ocean.
    ctx.strokeStyle = 'rgba(148,163,184,0.10)';
    ctx.lineWidth = 1;
    for (let lon = -180; lon <= 180; lon += 30) {
      ctx.beginPath();
      ctx.moveTo(x(lon), 0);
      ctx.lineTo(x(lon), TEXTURE_H);
      ctx.stroke();
    }
    for (let lat = -60; lat <= 60; lat += 30) {
      ctx.beginPath();
      ctx.moveTo(0, y(lat));
      ctx.lineTo(TEXTURE_W, y(lat));
      ctx.stroke();
    }

    try {
      resolve(canvas.toDataURL('image/png'));
    } catch (err) {
      reject(err instanceof Error ? err : new Error(String(err)));
    }
  });
  return texturePromise;
}

/** The globe texture for the already-registered world geometry. */
export async function worldGlobeTexture(): Promise<string> {
  const features = await ensureWorldMapRegistered();
  return buildGlobeTexture(features);
}
