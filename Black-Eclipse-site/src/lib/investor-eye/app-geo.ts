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

/** Surface palettes. `MapSkin` lives in the store; kept structural here so this
 *  module stays free of UI-state imports. */
export type GlobeSkin = 'black' | 'glow';

interface GlobePalette {
  ocean: Array<[number, string]>;
  band: Array<[number, string]>;
  graticule: string;
  /** Two-pass coastline bloom drawn UNDER the land. */
  bloom: { color: string; blur: number; width: number } | null;
  land: Array<[number, string]>;
  coastline: string;
  coastlineWidth: number;
  /** Deterministic city-light stipple; null disables it. */
  stipple: { count: number; minAlpha: number; maxAlpha: number } | null;
}

/**
 * BLUE is the point of the `glow` palette.
 *
 * WHY THE TEXTURE CARRIES THE LOOK: `echarts-gl`'s globe is lit as a surface
 * (`shading: 'lambert'`), so flat fills come out muddy. The visual weight
 * therefore lives in the texture: a deep blue ocean, land that is clearly
 * lighter and blue-lit, and bright cyan coastlines with a real bloom. The
 * emission layer + starfield are added by the map adapter, not here.
 *
 * `black` is the first-draft terminal surface: near-black ocean, opaque grey
 * land, hairline borders, no bloom and no stipple.
 */
const GLOBE_PALETTES: Record<GlobeSkin, GlobePalette> = {
  glow: {
    ocean: [
      [0, '#061530'],
      [0.35, '#0a2450'],
      [0.5, '#0c2d63'],
      [0.65, '#0a2450'],
      [1, '#061530'],
    ],
    band: [
      [0, 'rgba(96,165,250,0.20)'],
      [0.6, 'rgba(96,165,250,0.07)'],
      [1, 'rgba(0,0,0,0)'],
    ],
    graticule: 'rgba(125,211,252,0.10)',
    bloom: { color: 'rgba(56,189,248,0.85)', blur: 22, width: 3 },
    land: [
      [0, '#1b4a86'],
      [0.5, '#2a67b4'],
      [1, '#1b4a86'],
    ],
    coastline: 'rgba(186,240,255,0.95)',
    coastlineWidth: 1.3,
    stipple: { count: 2600, minAlpha: 0.06, maxAlpha: 0.22 },
  },
  black: {
    // GREY, not near-black. A near-black texture under `lambert` lighting with
    // low ambient came out as an almost featureless dark ball. These tones are
    // mid-grey, so the continents read as land at a glance.
    ocean: [
      [0, '#1a1c20'],
      [0.5, '#23262b'],
      [1, '#1a1c20'],
    ],
    band: [[0, 'rgba(255,255,255,0.05)'], [1, 'rgba(0,0,0,0)']],
    graticule: 'rgba(255,255,255,0.09)',
    bloom: null,
    land: [
      [0, '#4b5058'],
      [0.5, '#5a606a'],
      [1, '#4b5058'],
    ],
    coastline: 'rgba(255,255,255,0.55)',
    coastlineWidth: 1,
    stipple: null,
  },
};

const texturePromises = new Map<GlobeSkin, Promise<string>>();

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
 * Render the world as a glowing equirectangular texture for the 3D globe.
 * Resolves to a data URL. Rejects only if a 2D canvas is unavailable (SSR).
 *
 * WHY THE TEXTURE CARRIES THE LOOK: `echarts-gl`'s globe is lit as a surface
 * (`shading: 'lambert'`), so flat fills come out muddy and dark. The visual
 * weight therefore has to live in the texture: a deep-ocean gradient, land that
 * is clearly lighter, and bright cyan coastlines with a real bloom. The
 * atmosphere + starfield are added by the map layer, not here.
 */
export function buildGlobeTexture(features: GeoFeature[], skin: GlobeSkin = 'glow'): Promise<string> {
  const cached = texturePromises.get(skin);
  if (cached) return cached;
  const promise = new Promise<string>((resolve, reject) => {
    const palette = GLOBE_PALETTES[skin];
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

    // ── Ocean ───────────────────────────────────────────────────────────────
    // The `glow` palette is a DEEP BLUE gradient: blue enough that the planet
    // unmistakably reads as blue, dark enough that the pale-blue continents and
    // the cyan coastline still separate from it. `black` is near-black flat.
    const ocean = ctx.createLinearGradient(0, 0, 0, TEXTURE_H);
    for (const [stop, color] of palette.ocean) ocean.addColorStop(stop, color);
    ctx.fillStyle = ocean;
    ctx.fillRect(0, 0, TEXTURE_W, TEXTURE_H);

    // A soft equatorial light band, so the lit side of the sphere has a gradient
    // to travel along rather than a flat tone.
    const band = ctx.createRadialGradient(
      TEXTURE_W / 2, TEXTURE_H / 2, TEXTURE_H * 0.1,
      TEXTURE_W / 2, TEXTURE_H / 2, TEXTURE_H * 0.75,
    );
    for (const [stop, color] of palette.band) band.addColorStop(stop, color);
    ctx.fillStyle = band;
    ctx.fillRect(0, 0, TEXTURE_W, TEXTURE_H);

    // Equirectangular projection with a tiny inset so the ±180 seam is not clipped.
    const x = (lon: number) => ((lon + 180) / 360) * TEXTURE_W;
    const y = (lat: number) => ((90 - lat) / 180) * TEXTURE_H;

    ctx.lineJoin = 'round';

    // ── Graticule: drawn UNDER the land so it never cuts across a continent ──
    ctx.strokeStyle = palette.graticule;
    ctx.lineWidth = 1;
    for (let lon = -180; lon <= 180; lon += 20) {
      ctx.beginPath();
      ctx.moveTo(x(lon), 0);
      ctx.lineTo(x(lon), TEXTURE_H);
      ctx.stroke();
    }
    for (let lat = -80; lat <= 80; lat += 20) {
      ctx.beginPath();
      ctx.moveTo(0, y(lat));
      ctx.lineTo(TEXTURE_W, y(lat));
      ctx.stroke();
    }

    // ── Coastline bloom (glow skin only) ────────────────────────────────────
    // Drawn in its own pass, BELOW the land fill, with a wide blur. The land
    // then covers the inner half of the bloom, leaving a halo that hugs the
    // coast exactly — a real glow rather than a stroke.
    if (palette.bloom) {
      ctx.save();
      ctx.shadowColor = palette.bloom.color;
      ctx.shadowBlur = palette.bloom.blur;
      ctx.strokeStyle = palette.bloom.color;
      ctx.lineWidth = palette.bloom.width;
      for (const f of features) {
        for (const polygon of geometryPolygons(f.geometry)) {
          ctx.beginPath();
          for (const ring of polygon) traceRing(ctx, ring as unknown as ArrayLike<number>, x, y);
          ctx.stroke();
        }
      }
      ctx.restore();
    }

    // ── Land ────────────────────────────────────────────────────────────────
    // Blue-lit rather than grey, so the continent is clearly part of the same
    // blue planet as the ocean. The vertical gradient keeps a large interior
    // from reading as a flat slab.
    const land = ctx.createLinearGradient(0, 0, 0, TEXTURE_H);
    for (const [stop, color] of palette.land) land.addColorStop(stop, color);
    for (const f of features) {
      for (const polygon of geometryPolygons(f.geometry)) {
        ctx.beginPath();
        for (const ring of polygon) traceRing(ctx, ring as unknown as ArrayLike<number>, x, y);
        ctx.fillStyle = land;
        ctx.fill();
        // A crisp bright coastline on top of the bloom — this is the single
        // strongest "this is a lit planet" cue in the whole texture.
        ctx.strokeStyle = palette.coastline;
        ctx.lineWidth = palette.coastlineWidth;
        ctx.stroke();
      }
    }

    // ── City-light stipple on land (glow skin only) ─────────────────────────
    // A faint deterministic speckle gives the continents texture at close zoom,
    // so a zoomed globe is not a flat colour field.
    const stipple = palette.stipple;
    if (stipple) {
      let seed = 1337;
      const rand = () => {
        // xorshift32 — deterministic, so the texture is identical every session.
        seed ^= seed << 13; seed |= 0;
        seed ^= seed >>> 17;
        seed ^= seed << 5; seed |= 0;
        return ((seed >>> 0) % 100000) / 100000;
      };
      ctx.save();
      const allPolys: number[][][][] = [];
      for (const f of features) for (const p of geometryPolygons(f.geometry)) allPolys.push(p);
      for (let i = 0; i < stipple.count; i++) {
        const lon = rand() * 360 - 180;
        const lat = rand() * 150 - 75;
        const px = x(lon);
        const py = y(lat);
        // Only stipple points that are actually on land.
        let onLand = false;
        for (const polygon of allPolys) {
          if (pointInPolygon(px, py, polygon[0], x, y)) { onLand = true; break; }
        }
        if (!onLand) continue;
        const alpha = stipple.minAlpha + rand() * (stipple.maxAlpha - stipple.minAlpha);
        ctx.fillStyle = `rgba(186,230,253,${alpha})`;
        ctx.fillRect(px, py, 1.4, 1.4);
      }
      ctx.restore();
    }

    try {
      resolve(canvas.toDataURL('image/png'));
    } catch (err) {
      reject(err instanceof Error ? err : new Error(String(err)));
    }
  });
  texturePromises.set(skin, promise);
  return promise;
}

/**
 * Point-in-polygon in TEXTURE space (not lon/lat), used only to decide whether a
 * stipple point lands on a continent. Ray casting; holes are ignored, which is
 * harmless for a 1px decorative speckle.
 */
function pointInPolygon(
  px: number,
  py: number,
  ring: number[][],
  x: (n: number) => number,
  y: (n: number) => number,
): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = x(ring[i][0]);
    const yi = y(ring[i][1]);
    const xj = x(ring[j][0]);
    const yj = y(ring[j][1]);
    if ((yi > py) !== (yj > py) && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** The globe texture for the already-registered world geometry. */
export async function worldGlobeTexture(skin: GlobeSkin = 'glow'): Promise<string> {
  const features = await ensureWorldMapRegistered();
  return buildGlobeTexture(features, skin);
}

// ── Globe emission (coastline glow) ──────────────────────────────────────────
// The globe supports `layers` with `{ type: 'blend', blendTo: 'emission' }`,
// whose shader adds the texture additively:
//
//   gl_FragColor.rgb += texel.rgb * texel.a * intensity
//
// That is a genuine glow — light emitted from the surface — and it is the right
// tool for an aura. It replaces the `atmosphere` component, which paints
// `glowColor * pow(1 - dot(normal, viewDir), glowPower)` and therefore peaks
// EXACTLY on the silhouette: a hard ring, no matter how `glowPower` is tuned.
//
// The emission texture is coastlines only, on a transparent field, so the glow
// traces the continents and leaves the ocean dark.

const GLOW_W = 2048;
const GLOW_H = 1024;

let glowPromise: Promise<string> | null = null;

/** Draw a coastlines-only emission map (transparent everywhere else). */
export function buildGlobeGlowTexture(features: GeoFeature[]): Promise<string> {
  if (glowPromise) return glowPromise;
  glowPromise = new Promise<string>((resolve, reject) => {
    if (typeof document === 'undefined') {
      reject(new Error('no document'));
      return;
    }
    const canvas = document.createElement('canvas');
    canvas.width = GLOW_W;
    canvas.height = GLOW_H;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      reject(new Error('no 2d context'));
      return;
    }
    // Deliberately NOT filled — the emission layer's alpha decides where light
    // is added, so a transparent field means "glow only where we draw".
    const x = (lon: number) => ((lon + 180) / 360) * GLOW_W;
    const y = (lat: number) => ((90 - lat) / 180) * GLOW_H;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';

    // Two passes: a soft halo, then a tight bright core. Because this is ADDED
    // to the globe's lit colour, the halo reads as light bleeding off the
    // coastline rather than as a stroke drawn on top of it.
    //
    // Alpha and width here set the STRENGTH of the aura, and additive light
    // compounds fast: a wide opaque stroke turns the whole hemisphere into a
    // glowing blob. Measured on screen, ~0.28 peak alpha with an 5px stroke
    // gives a coastline that glows without washing out the land.
    ctx.save();
    ctx.strokeStyle = 'rgba(56,189,248,0.28)';
    ctx.lineWidth = 5;
    ctx.shadowColor = 'rgba(56,189,248,0.55)';
    ctx.shadowBlur = 12;
    for (const f of features) {
      for (const polygon of geometryPolygons(f.geometry)) {
        ctx.beginPath();
        for (const ring of polygon) traceRing(ctx, ring as unknown as ArrayLike<number>, x, y);
        ctx.stroke();
      }
    }
    ctx.restore();

    ctx.strokeStyle = 'rgba(186,230,253,0.55)';
    ctx.lineWidth = 1.1;
    for (const f of features) {
      for (const polygon of geometryPolygons(f.geometry)) {
        ctx.beginPath();
        for (const ring of polygon) traceRing(ctx, ring as unknown as ArrayLike<number>, x, y);
        ctx.stroke();
      }
    }

    try {
      resolve(canvas.toDataURL('image/png'));
    } catch (err) {
      reject(err instanceof Error ? err : new Error(String(err)));
    }
  });
  return glowPromise;
}

/** The emission texture for the already-registered world geometry. */
export async function worldGlobeGlowTexture(): Promise<string> {
  const features = await ensureWorldMapRegistered();
  return buildGlobeGlowTexture(features);
}
