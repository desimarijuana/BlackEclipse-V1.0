// ── Investor Eye — ECharts map adapter ───────────────────────────────────────
// Translates the provider-agnostic `MapLayer[]` into an ECharts option. This is
// the ONLY place that knows the map is drawn with ECharts; the layers, the
// component and the data layer stay visualization-agnostic (spec §44).
//
// Styling follows the BlackEclipse dark terminal language; tooltips follow the
// frosted-glass rules in `.opencode/skills/black-eclipse-ui/SKILL.md` (translucent
// tint ≤0.55, `appendTo: 'body'`, standard `backdrop-filter` only).

import type { EChartsOption } from 'echarts';
import { LAYER_META, layerColor, layerSymbol, severityColor, type LayerId, type LayerSymbol } from './layers';
import { COUNTRIES } from './countries';
import type { MapLayer, LayerDatum } from './types';

/** Legend symbol → ECharts symbol name. Keeps shapes readable on the dark map. */
const ECHARTS_SYMBOL: Record<Exclude<LayerSymbol, 'path://'>, string> = {
  circle: 'circle',
  diamond: 'diamond',
  triangle: 'triangle',
  square: 'rect',
  ring: 'circle',
};

/**
 * Marker symbol for a layer, from the canonical registry.
 *
 * `layerSymbol` resolves the category GLYPH (`path://…`) first, so a conflict
 * renders as a blast and an earthquake as seismic rings rather than every layer
 * sharing a dot. Both renderers consume the same value: ECharts resolves
 * `path://` in canvas, and echarts-gl's sprite builder calls the same
 * `createSymbol` helper, so one glyph serves the 2D map and the globe.
 */
function symbolForLayer(layerId: string): string | undefined {
  const meta = LAYER_META[layerId as LayerId];
  if (!meta) return undefined;
  if (meta.glyph) return layerSymbol(layerId);
  return meta.symbol && meta.symbol !== 'path://' ? ECHARTS_SYMBOL[meta.symbol] : undefined;
}

/**
 * Layers whose points ARE the category (spec §8). These are tinted with the
 * layer's own accent so `conflict` / `weather` / `energy` read as distinct
 * categories; severity still drives marker size, and the tooltip still states it.
 * Layers that mix categories (`events`) or encode a direction of change
 * (`markets`, `companies`) keep severity/sign colouring instead.
 */
const CATEGORY_COLORED = new Set<string>(['conflict', 'weather', 'energy', 'fires', 'shipping', 'commodities', 'portfolio']);

/** World map registration name — must match the GeoJSON `name` in app/geo.ts. */
export const WORLD_MAP_NAME = 'blackeclipse-world';

/**
 * Whether a container box is large enough to initialise the ECharts geo map.
 *
 * WHY THIS EXISTS: ECharts' geo/`View` code path dereferences a null matrix when
 * `setOption` runs against a ZERO-size container — it throws
 * `Cannot read properties of null (reading '0')` and the chart never recovers.
 * A full-screen map always has an explicit height, but an EMBEDDED map (the
 * Command Center widget) can mount a frame before flex layout resolves its
 * height, so initialization must wait for a real box. Any non-zero size works;
 * `WorldMap` observes the container and initialises once this is true.
 */
export function hasDrawableBox(width: number, height: number): boolean {
  return width >= 1 && height >= 1;
}

/**
 * Note on the 3D globe surface: `echarts-gl`'s `globe` component has no `map`
 * property — it takes a raster `baseTexture`. Rather than ship a binary asset
 * or a flat fill, the texture is drawn at runtime from the same world GeoJSON
 * the 2D map uses (`app-geo.worldGlobeTexture`) and passed in via
 * `MapOptionOptions.globeTexture`.
 */

const GLASS_TOOLTIP = {
  backgroundColor: 'rgba(18,18,20,0.5)',
  borderColor: 'rgba(255,255,255,0.12)',
  borderWidth: 1,
  padding: [8, 10] as [number, number],
  textStyle: { color: '#e5e7eb', fontSize: 11 },
  extraCssText:
    'backdrop-filter: blur(18px) saturate(1.35); border-radius: 14px; ' +
    'box-shadow: 0 8px 30px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.06);',
};

/** Light-scheme twin of {@link GLASS_TOOLTIP} — same frosted recipe, light tint. */
const LIGHT_TOOLTIP = {
  backgroundColor: 'rgba(255,255,255,0.62)',
  borderColor: 'rgba(0,0,0,0.10)',
  borderWidth: 1,
  padding: [8, 10] as [number, number],
  textStyle: { color: '#18181b', fontSize: 11 },
  extraCssText:
    'backdrop-filter: blur(18px) saturate(1.35); border-radius: 14px; ' +
    'box-shadow: 0 8px 30px rgba(0,0,0,0.14), inset 0 1px 0 rgba(255,255,255,0.55);',
};

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Clamp a tooltip string to a single line. The map tooltip is a glance surface,
 * not a dossier — a long event title (e.g. a full wire headline) used to wrap to
 * two or three lines and cover the very map it describes. Values are truncated
 * with an ellipsis; the panel holds the full text on click.
 */
function clampText(s: string, max: number): string {
  const t = s.trim();
  return t.length > max ? `${t.slice(0, max - 1).trimEnd()}…` : t;
}

/**
 * Unwrap the `LayerDatum` from an ECharts callback payload.
 *
 * ECharts hands tooltip/click callbacks its OWN wrapper object
 * (`{ name, value, severity, _datum }`), never the `LayerDatum` itself. Reading
 * `params.data.data` (as an earlier version did) is always `undefined`, which
 * crashed `eventTooltip` on every hover with
 * "Cannot read properties of undefined (reading 'eventType')".
 *
 * Exported so the contract is unit-tested — the crash was invisible to tsc
 * because the payload is typed as `unknown` at the ECharts boundary.
 */
export function unwrapDatum<T extends LayerDatum>(params: { data?: T & { _datum?: T } } | undefined): T | undefined {
  const raw = params?.data;
  return raw?._datum ?? raw;
}

/** Build the tooltip HTML from a layer's structured `TooltipContent`. */
function tooltipFormatter(layer: MapLayer) {
  return (params: { data?: LayerDatum }): string => {
    const datum = unwrapDatum(params);
    if (!datum || !layer.tooltip) return '';
    const content = layer.tooltip(datum);
    const rows = content.rows
      .map(
        (r) =>
          `<div style="display:flex;justify-content:space-between;gap:12px;margin-top:2px">` +
          `<span style="color:#9ca3af;flex:0 0 auto">${escapeHtml(r.label)}</span>` +
          `<span style="color:#e5e7eb;font-weight:600;text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:150px">${escapeHtml(clampText(r.value, 44))}</span>` +
          `</div>`,
      )
      .join('');
    const subtitle = content.subtitle
      ? `<div style="color:#9ca3af;margin-top:3px;max-width:240px;white-space:normal">${escapeHtml(clampText(content.subtitle, 96))}</div>`
      : '';
    const note = content.note
      ? `<div style="color:#6b7280;font-size:10px;margin-top:5px;max-width:240px;white-space:normal;border-top:1px solid rgba(255,255,255,0.08);padding-top:4px">${escapeHtml(clampText(content.note, 140))}</div>`
      : '';
    return (
      `<div style="min-width:160px;max-width:250px">` +
      `<div style="font-weight:700;font-size:12px;line-height:1.3;max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(clampText(content.title, 64))}</div>` +
      subtitle + rows + note +
      `</div>`
    );
  };
}

/**
 * Marker visuals.
 *
 * Bloomberg-style density reading: markers are deliberately SMALL so the map
 * stays legible when hundreds are on screen, and clusters of events do not
 * collapse into one blob. Severity is carried by the glow radius rather than a
 * big disc, so a critical event still reads as heavier without dominating.
 */
const PIN_SIZE: Record<string, number> = { critical: 8, high: 6, medium: 5, low: 4 };
/** Glow radius per severity — the visual weight carries the urgency. */
const PIN_GLOW: Record<string, number> = { critical: 12, high: 8, medium: 5, low: 3 };

/**
 * Globe marker sizing.
 *
 * `scatter3D` resolves `symbolSize` through `getItemVisual`, so a per-item
 * callback WOULD work — but the glyph is the information carrier here, and a
 * blob-sized shape erases its own silhouette. So the globe uses one tight size
 * where the glyph is legible, and severity is carried by COLOUR plus the faint
 * critical ring rather than by scale.
 */
const GLOBE_CORE_SIZE = 9;
const GLOBE_HALO_SIZE = 13;
const GLOBE_HALO_OPACITY = 0.22;

/**
 * Map presentation: 2D projection or a rotatable 3D globe.
 *
 * `black` is the original flat terminal look — a solid near-black landmass with
 * hairline borders and no glow. `glow` is a retained internal variant: the blue
 * "lit planet" look (translucent blue continent, cyan coastline, globe bloom).
 * The product now ships the simple surface only; the variant is kept for tests
 * and future skins, and switching it never rebuilds the data.
 */
export type MapMode = '2d' | 'globe';
export type MapSkin = 'black' | 'glow';
/**
 * Color scheme the map is rendered in. The map's own geo fills are canvas-drawn,
 * so they cannot follow the app's CSS tokens — the scheme is passed in from
 * `WorldMap` (which observes the `dark` class) so a light-mode page gets a light
 * landmass/backdrop instead of the hard-coded dark terminal surface.
 */
export type MapScheme = 'dark' | 'light';

/**
 * Globe surface radius in world units. Purely a modelling constant — the camera
 * distance is derived from it plus the container box so the sphere fills the
 * view. Not a pixel size.
 */
export const GLOBE_RADIUS = 100;

/** Perspective camera vertical field of view (echarts-gl default is 50°). */
const GLOBE_FOV_DEG = 50;
const GLOBE_HALF_FOV_TAN = Math.tan((GLOBE_FOV_DEG / 2) * (Math.PI / 180));

/**
 * Camera distance (measured from the globe SURFACE — echarts-gl adds the radius
 * itself) so the sphere fills `fill` of the container's SHORTER dimension.
 *
 * WHY THE BOX IS NEEDED: the old option hard-coded `globeRadius: 86` and
 * `distance: 200`. A sphere projects to a circle whose screen radius is
 * `R / ((distance + R) · tan(fov/2))` of the viewport's half-height, so that
 * pair rendered the globe at ~65% of the viewport height regardless of size —
 * small on a wide desktop map. Deriving the distance from the real box makes the
 * globe fill the map instead of floating in it.
 *
 * A sphere projects to the same pixel radius on both axes (perspective is
 * isotropic), so the limiting dimension is `min(width, height)`; the
 * `height / min` factor corrects for a non-square box.
 */
export function globeViewDistance(width: number, height: number, radius = GLOBE_RADIUS, fill = 0.92): number {
  // A sphere of radius R whose centre is D from the camera has silhouette angular
  // radius `asin(R/D)`; its screen radius as a fraction of the viewport half-height
  // is `tan(asin(R/D)) / tan(fov/2) = R / (√(D²−R²) · tan(fov/2))`. Solving that
  // for the target fill (fraction of the SHORTER viewport dimension) gives the
  // centre distance below. A sphere images isotropically, so only the shorter
  // dimension constrains it — hence the `height / min` correction for a
  // non-square box. echarts-gl measures `distance` from the SURFACE, so R is
  // subtracted at the end.
  const safeW = width > 0 ? width : height;
  const safeH = height > 0 ? height : width;
  if (!(safeW > 0) || !(safeH > 0)) {
    // No box yet (SSR / pre-layout): a default that still fits.
    const d = radius / (fill * GLOBE_HALF_FOV_TAN);
    return Math.max(radius * 0.25, Math.sqrt(radius * radius + d * d) - radius);
  }
  const min = Math.min(safeW, safeH);
  const projected = (radius * safeH) / (fill * GLOBE_HALF_FOV_TAN * min);
  const centreDistance = Math.sqrt(radius * radius + projected * projected);
  return Math.max(radius * 0.25, centreDistance - radius);
}

/**
 * Countries to label, from the gazetteer centroids. Natural Earth's raw ADMIN
 * names are not always what a user expects ("United States of America"), and the
 * geo component cannot hide overlapping labels, so the curated gazetteer is used
 * for both projections — short names, stable centroids, one code path.
 */
const COUNTRY_LABELS = COUNTRIES.map((c) => ({ name: c.name, lon: c.lon, lat: c.lat }));

const GEO_BY_SKIN = {
  black: {
    itemStyle: {
      // The first-draft terminal fill: opaque, flat, no glow.
      areaColor: '#141416',
      borderColor: 'rgba(255,255,255,0.10)',
      borderWidth: 0.5,
      shadowColor: 'rgba(0,0,0,0)',
      shadowBlur: 0,
    },
    emphasis: {
      label: { show: false },
      itemStyle: { areaColor: '#1f2937', borderColor: 'rgba(255,255,255,0.25)', borderWidth: 1, shadowBlur: 0 },
    },
    select: {
      label: { show: false },
      itemStyle: { areaColor: '#1e3a5f', borderColor: '#60a5fa' },
    },
  },
  glow: {
    itemStyle: {
      // BLUE, and translucent. The blue is the "lit planet" cue; the alpha lets
      // the animated starfield read through the continents, which is what makes
      // the flat map feel like the same surface as the globe.
      areaColor: 'rgba(23,52,94,0.66)',
      borderColor: 'rgba(125,232,255,0.72)',
      borderWidth: 0.8,
      shadowColor: 'rgba(56,189,248,0.65)',
      shadowBlur: 8,
    },
    emphasis: {
      label: { show: false },
      itemStyle: {
        areaColor: 'rgba(41,86,140,0.82)',
        borderColor: 'rgba(186,246,255,0.98)',
        borderWidth: 1.3,
        shadowColor: 'rgba(56,189,248,0.95)',
        shadowBlur: 16,
      },
    },
    select: {
      label: { show: false },
      itemStyle: { areaColor: 'rgba(45,96,160,0.9)', borderColor: '#8be9ff' },
    },
  },
} as const;

/**
 * Light-scheme 2D base map. Same structure as {@link GEO_BY_SKIN} but with a
 * light landmass and dark hairline borders so the map reads on a white page.
 * The `black`/`glow` skins are dark-surface looks; in light mode both collapse
 * to this one legible light palette.
 */
const GEO_LIGHT = {
  itemStyle: {
    areaColor: '#e3e8ef',
    borderColor: 'rgba(15,23,42,0.28)',
    borderWidth: 0.5,
    shadowColor: 'rgba(0,0,0,0)',
    shadowBlur: 0,
  },
  emphasis: {
    label: { show: false },
    itemStyle: { areaColor: '#cbd5e1', borderColor: 'rgba(15,23,42,0.55)', borderWidth: 1, shadowBlur: 0 },
  },
  select: {
    label: { show: false },
    itemStyle: { areaColor: '#bfdbfe', borderColor: '#2563eb' },
  },
} as const;

/**
 * The 2D base map, per skin (see `MapSkin`) and scheme. In light mode the dark
 * skins (`black`/`glow`) are replaced by {@link GEO_LIGHT} so the map is legible
 * on a white page.
 *
 * The map is the hero: no competing labels until a country is hovered, and
 * hover/select brighten rather than recolour so the glow language holds.
 */
function baseGeo(skin: MapSkin, scheme: MapScheme = 'dark') {
  return {
    map: WORLD_MAP_NAME,
    roam: true,
    zoom: 1.15,
    silent: false,
    ...(scheme === 'light' ? GEO_LIGHT : GEO_BY_SKIN[skin]),
    label: { show: false },
  };
}

export interface MapOptionOptions {
  layers: MapLayer[];
  /**
   * Countries highlighted by an NL search, with their centroids so the map can
   * visibly respond even when no event pins exist there.
   */
  highlightPoints?: Array<{ iso2: string; name: string; lon: number; lat: number }>;
  /**
   * Live container size in CSS pixels. Used to derive the globe camera distance
   * so the sphere fills the view (see `globeViewDistance`). Optional so pure
   * tests and SSR can omit it; a sane default is used when absent.
   */
  width?: number;
  height?: number;
  /** Draw country names. Defaults to true. */
  showCountryLabels?: boolean;
  /**
   * Key (`id ?? dedupKey`) of the currently selected event. When it matches a
   * trade line, that route is drawn emphasised and every other route dimmed, so
   * a click answers "what is traded on THIS link?" instead of leaving the whole
   * web equally loud.
   */
  selectedEventKey?: string | null;
  /**
   * ISO2 of the country under the pointer. When the Trade layer is on, only the
   * routes touching this country stay visible; every other route is hidden, so
   * hovering a country answers "what does THIS country trade?". A clicked
   * selection (`selectedEventKey`) wins over hover.
   */
  hoveredCountryIso?: string | null;
  /**
   * Hovered/highlighted country OUTLINE, as `[lon, lat]` rings. The 2D `geo`
   * component highlights a country natively on hover, but the 3D globe is a
   * texture with no per-country geometry — so the globe draws the picked
   * country's rings as a `lines3D` polyline to give the same feedback.
   */
  highlightCountryRings?: Array<Array<[number, number]>>;
  /** Presentation mode. Defaults to the flat map. */
  mode?: MapMode;
  /**
   * Surface skin. `black` is the flat terminal look and the default; `glow` is
   * a retained internal variant (blue lit planet) that is no longer exposed in
   * the UI. Ignored for the 2D map when `scheme` is `light`.
   */
  skin?: MapSkin;
  /**
   * App color scheme. Defaults to `dark` (the shipped look). `light` swaps the
   * canvas-drawn geo fills and the tooltip to light-surface variants, since the
   * map cannot follow the app's CSS tokens.
   */
  scheme?: MapScheme;
  /**
   * Globe-only: the equirectangular world texture drawn from the same GeoJSON.
   * Produced asynchronously (`worldGlobeTexture()`), so it is passed in rather
   * than imported here.
   */
  globeTexture?: string;
  /**
   * Globe-only: the coastlines-only EMISSION map (`worldGlobeGlowTexture()`).
   * Added as an additive light layer, so the globe's aura comes from the surface
   * instead of an atmosphere shell (which can only ever draw a ring).
   */
  globeGlowTexture?: string;
}

/**
 * The globe's hovered-country outline series.
 *
 * Extracted so `WorldMap` can push a new outline on hover WITHOUT rebuilding the
 * whole option (`setOption({ series: [...] })` merges by id). `polyline: true`
 * tells `lines3D` to treat each item's `coords` as one continuous path rather
 * than a single segment between two points.
 */
export function buildCountryOutlineSeries(rings: Array<Array<[number, number]>>) {
  return {
    id: 'country-outline',
    name: 'Country',
    type: 'lines3D',
    coordinateSystem: 'globe',
    polyline: true,
    z: 90,
    silent: true,
    // A bright, thick stroke with a dark under-halo reads over both the blue
    // `glow` surface and the grey `black` one. `lines3D` has no shadow, so the
    // width carries the contrast — 3px is the thinnest that still stands out
    // against the glowing coastline at a normal zoom.
    lineStyle: { color: '#e0f2fe', width: 3, opacity: 1 },
    data: rings.filter((r) => r.length >= 3).map((ring) => ({ coords: ring })),
    tooltip: { show: false },
  };
}

/** Convert ISO2 → the ECharts map feature name is handled via `nameMap`. */
export function buildMapOption(options: MapOptionOptions): EChartsOption {
  const { layers } = options;
  const mode: MapMode = options.mode ?? '2d';
  const skin: MapSkin = options.skin ?? 'black';
  const scheme: MapScheme = options.scheme ?? 'dark';
  const isLight = scheme === 'light';
  const isGlow = skin === 'glow';
  const enabled = layers.filter((l) => l.enabled).sort((a, b) => a.zIndex - b.zIndex);

  const series: EChartsOption['series'] = [];

  // Country-fill layers first (they paint regions, not points). In globe mode
  // the base sphere itself carries the country borders, so fills are skipped —
  // painting a flat map over a sphere would be wrong.
  if (mode === '2d') {
    for (const layer of enabled) {
      if (layer.type !== 'country-fill') continue;
      const data = layer.data();
      series.push({
        id: layer.id,
        name: layer.name,
        type: 'map',
        map: WORLD_MAP_NAME,
        roam: false,
        z: layer.zIndex,
        // Fill layers render as an overlay: transparent where no value exists.
        geoIndex: 0,
        data: data
          .filter((d) => d.countryIso)
          .map((d) => ({
            name: d.countryIso as string,
            value: d.value ?? 0,
            // Attach the datum so the tooltip can read it back.
            _datum: d,
          })),
        itemStyle: {
          areaColor: 'rgba(0,0,0,0)',
          borderColor: 'rgba(0,0,0,0)',
        },
        emphasis: {
          itemStyle: { areaColor: 'rgba(96,165,250,0.25)' },
        },
        selectedMode: false,
      } as never);
    }
  }

  // Severity-weighted density heatmap (Bloomberg-style). ECharts' `heatmap`
  // series only works against the 2D `geo` coordinate system — echarts-gl has
  // no heatmap, so on the globe this layer is simply not drawn (the pins layer
  // already communicates density there).
  let heatmapMax = 0;
  let heatmapSeriesId: string | null = null;
  if (mode === '2d') {
    for (const layer of enabled) {
      if (layer.type !== 'heatmap') continue;
      const data = layer.data();
      heatmapSeriesId = layer.id;
      for (const d of data) heatmapMax = Math.max(heatmapMax, d.value ?? 0);
      series.push({
        id: layer.id,
        name: layer.name,
        type: 'heatmap',
        coordinateSystem: 'geo',
        z: layer.zIndex,
        // Tight, overlapping blobs: wide enough that a cluster becomes a single
        // hotspot, small enough that every cell does not smear into a wash.
        pointSize: 16,
        blurSize: 18,
        // A LOW floor is the point: sparse areas stay dark and only genuine
        // concentrations light up. A high floor painted the whole map a muddy
        // blue and was what made the layer look like noise.
        minOpacity: 0.12,
        maxOpacity: 0.85,
        progressive: 400,
        data: data.map((d) => ({
          name: d.label ?? d.id,
          value: [d.lon, d.lat, d.value ?? 1],
          severity: d.severity,
          _datum: d,
        })),
        label: { show: false },
        // The heat canvas is silent per ECharts; the tooltip is wired through
        // the visualMap's own hover so a cell can still explain itself.
        tooltip: layer.tooltip ? { formatter: tooltipFormatter(layer) } : undefined,
      } as never);
    }
  }

  // Points/lines anchor to whichever coordinate system is active.
  const coordSystem = mode === 'globe' ? 'globe' : 'geo';

  const isGlobe = mode === 'globe';
  const pointSeriesTypes = new Set(['scatter', 'effect-scatter', 'symbol']);
  for (const layer of enabled) {
    if (!pointSeriesTypes.has(layer.type)) continue;
    const data = layer.data();
    // Ripple animation on a globe is expensive; keep it for small sets only.
    const isEffect = layer.type === 'effect-scatter' && data.length <= (isGlobe ? 120 : 300);
    // IMPORTANT: echarts-gl registers `globe` as a coordinate system for its
    // 3D series ONLY. A plain 2D `scatter` with `coordinateSystem: 'globe'`
    // silently falls back to index positioning, which is why the pins appeared
    // as a clump in the top-left corner instead of on the sphere. Globe mode
    // must use `scatter3D`.
    const seriesType = isGlobe
      ? 'scatter3D'
      : (isEffect ? 'effectScatter' : 'scatter');
    // Shapes come from the layer registry so the legend and the map agree.
    const symbol = symbolForLayer(layer.id);

    // On the globe, each point layer is drawn TWICE: a wide, low-opacity halo
    // pass underneath, then the solid core. Overlapping halos composite into a
    // real bloom (the look in the reference design), which `shadowBlur` cannot
    // deliver on a WebGL surface — echarts-gl has no canvas shadow for 3D
    // symbols. The halo is silent so it never steals a hover or a click from
    // the core.
    const colorOf = (raw: unknown, fallbackLayerId: string): string => {
      const item = raw as { data?: { severity?: string } };
      if (CATEGORY_COLORED.has(fallbackLayerId)) return layerColor(fallbackLayerId);
      if (!item.data?.severity) return layerColor(fallbackLayerId);
      return severityColor((item.data?.severity ?? 'low') as never);
    };

    if (isGlobe) {
      // NO halo discs on the globe. A halo is a second, larger copy of the same
      // glyph behind the core; with category glyphs that reads as a fuzzy blob
      // that erases the very shape carrying the information. The glow comes from
      // the globe's post-process bloom instead, which lights the glyph without
      // covering it. Only the highest-severity pins get a faint ring, purely to
      // flag them among their neighbours.
      series.push({
        id: `${layer.id}__critical_ring`,
        name: layer.name,
        type: 'scatter3D',
        coordinateSystem: coordSystem,
        z: layer.zIndex - 0.5,
        symbolSize: GLOBE_HALO_SIZE,
        symbol: 'circle',
        silent: true,
        itemStyle: { color: (raw: unknown) => colorOf(raw, layer.id), opacity: GLOBE_HALO_OPACITY },
        data: data
          .filter((d) => d.severity === 'critical')
          .map((d) => ({ name: d.label ?? d.id, value: [d.lon, d.lat], severity: d.severity })),
        tooltip: { show: false },
      } as never);
    }

    series.push({
      id: layer.id,
      name: layer.name,
      type: seriesType,
      coordinateSystem: coordSystem,
      z: layer.zIndex,
      // The category GLYPH, in BOTH projections. echarts-gl resolves `path://`
      // through the same `createSymbol` helper as the 2D renderer, so one glyph
      // definition serves the flat map and the globe.
      ...(symbol ? { symbol } : {}),
      // Only animate when there is a small, curated set of points. `scatter3D`
      // has no ripple effect, so globe mode never animates.
      ...(isEffect && !isGlobe
        ? { showEffectOn: 'render', rippleEffect: { brushType: 'stroke', scale: 3, period: 5 } }
        : {}),
      ...(isGlobe
        ? {
            symbolSize: GLOBE_CORE_SIZE,
            itemStyle: {
              // A callback is safe here: it is resolved by ECharts' visual
              // pipeline before echarts-gl reads the item (verified — the globe
              // renders per-severity colour). Only `opacity`/`symbolSize` must
              // stay scalar, because echarts-gl reads those directly.
              // The glyph keeps its CATEGORY colour: the shape already says what
              // it is, and a whitened glyph loses the colour coding. The globe's
              // bloom supplies the light.
              color: (raw: unknown) => colorOf(raw, layer.id),
              opacity: 1,
            },
            emphasis: { itemStyle: { opacity: 1 } },
          }
        : {
            symbolSize: (raw: unknown) => {
              const item = raw as { data?: { value?: number; severity?: string; approximate?: boolean } };
              const sev = item.data?.severity ?? 'low';
              const size = PIN_SIZE[sev] ?? PIN_SIZE.low;
              // Approximate points render slightly smaller — a visual cue that
              // the position is a country centre, not a confirmed location.
              return item.data?.approximate ? Math.max(3, size - 2) : size;
            },
            itemStyle: {
              color: (raw: unknown) => {
                const item = raw as { data?: { severity?: string; approximate?: boolean } };
                // Hollow centre for approximate fixes: the fill is transparent
                // and the accent moves to the border, so the marker reads as a
                // ring rather than a solid dot.
                if (item.data?.approximate) return 'rgba(0,0,0,0)';
                if (CATEGORY_COLORED.has(layer.id)) return layerColor(layer.id);
                return item.data?.severity
                  ? severityColor(item.data.severity as never)
                  : layerColor(layer.id);
              },
              borderColor: (raw: unknown) => {
                const item = raw as { data?: { severity?: string; approximate?: boolean } };
                // A dark ring separates overlapping pins without hiding colour.
                if (!item.data?.approximate) return 'rgba(8,9,12,0.92)';
                // Match the ring to what the fill would have been.
                if (CATEGORY_COLORED.has(layer.id)) return layerColor(layer.id);
                return item.data?.severity
                  ? severityColor(item.data.severity as never)
                  : layerColor(layer.id);
              },
              borderWidth: (raw: unknown) => {
                const item = raw as { data?: { approximate?: boolean } };
                return item.data?.approximate ? 2 : 1.5;
              },
              borderType: (raw: unknown) => {
                const item = raw as { data?: { approximate?: boolean } };
                return item.data?.approximate ? 'dashed' : 'solid';
              },
              // A coloured halo sized by severity, so a critical event is
              // visibly heavier than a low one at the same zoom.
              shadowBlur: (raw: unknown) => {
                const item = raw as { data?: { severity?: string } };
                return PIN_GLOW[item.data?.severity ?? 'low'] ?? PIN_GLOW.low;
              },
              shadowColor: (raw: unknown) => {
                const item = raw as { data?: { severity?: string; approximate?: boolean } };
                if (item.data?.approximate) return 'rgba(148,163,184,0.55)';
                if (CATEGORY_COLORED.has(layer.id)) return layerColor(layer.id);
                return item.data?.severity
                  ? severityColor(item.data.severity as never)
                  : layerColor(layer.id);
              },
              opacity: 1,
            },
            emphasis: { scale: 1.5 },
          }),
      data: data.map((d) => ({
        name: d.label ?? d.id,
        // `scatter3D` reads a THIRD array element as ALTITUDE. Passing `value`
        // there (as a 2D scatter legitimately does) lifted the points off the
        // globe into radiating spikes. 3D series get exactly [lon, lat].
        value: isGlobe ? [d.lon, d.lat] : [d.lon, d.lat, d.value ?? 1],
        severity: d.severity,
        /** Country-centroid anchors are shown as hollow/dashed markers. */
        approximate: d.geoMethod === 'centroid',
        _datum: d,
      })),
      tooltip: layer.tooltip ? { formatter: tooltipFormatter(layer) } : undefined,
    } as never);
  }

  // Directional lines (trade). `lines` needs explicit coords + data.
  const selectedEventKey = options.selectedEventKey ?? null;
  const hoverIso = options.hoveredCountryIso ?? null;
  for (const layer of enabled) {
    if (layer.type !== 'lines') continue;
    const data = layer.data();
    // When a trade link is selected, each line is tagged so the click target
    // stands out and the rest recede — the map answers "what is traded on this
    // route" instead of showing every route at equal weight.
    const hasSelection = selectedEventKey != null
      && data.some((d) => (d.data as { eventKey?: string }).eventKey === selectedEventKey);
    // Hovering a country ISOLATES its routes: only links that touch the hovered
    // country are drawn, so the map answers "what does THIS country trade?".
    // A click-selection takes precedence. A country with no routes shows none —
    // honest rather than falling back to the full web.
    const touches = (d: LayerDatum) => {
      const p = d.data as { fromIso?: string; toIso?: string };
      return p.fromIso === hoverIso || p.toIso === hoverIso;
    };
    const hasHover = !hasSelection && hoverIso != null;
    const visibleData = hasHover ? data.filter(touches) : data;
    const lineData = visibleData.map((d) => {
      const payload = d.data as { from: [number, number]; to: [number, number]; eventKey?: string; fromIso?: string };
      const selected = hasSelection && payload.eventKey === selectedEventKey;
      // Per-item style: the selected route stays full-strength, siblings fade
      // back so the chosen trade link is unambiguous.
      return {
        coords: [payload.from, payload.to],
        _datum: d,
        selected,
        fromIso: payload.fromIso,
        ...(hasSelection
          ? {
              lineStyle: selected
                ? { width: isGlobe ? 3 : 2.4, opacity: 1, color: layerColor(layer.id) }
                : { width: isGlobe ? 1 : 0.8, opacity: 0.1, color: layerColor(layer.id) },
            }
          : hasHover
            ? { lineStyle: { width: isGlobe ? 3 : 2.2, opacity: 1, color: layerColor(layer.id) } }
            : {}),
      };
    });

    // On the globe, draw a wide translucent pass under the thin bright pass —
    // the same two-pass bloom trick the points use, so routes read as glowing
    // arcs rather than faint hairlines.
    if (isGlobe) {
      series.push({
        id: `${layer.id}__glow`,
        name: layer.name,
        type: 'lines3D',
        coordinateSystem: coordSystem,
        z: layer.zIndex - 0.5,
        silent: true,
        lineStyle: { color: layerColor(layer.id), width: 4, opacity: 0.16 },
        data: lineData,
        tooltip: { show: false },
      } as never);
    }

    series.push({
      id: layer.id,
      name: layer.name,
      // Like scatter, echarts-gl needs its own `lines3D` for the globe
      // coordinate system; a 2D `lines` would not project onto the sphere.
      type: isGlobe ? 'lines3D' : 'lines',
      coordinateSystem: coordSystem,
      z: layer.zIndex,
      // While isolated to a hovered country, the routes are made SILENT so they
      // cannot steal the pointer from the geo region underneath — otherwise
      // entering a route fired the country's `mouseout`, the routes vanished,
      // the pointer fell back on the country, and the layer flickered.
      ...(hasHover ? { silent: true } : {}),
      // 2D lines support a flowing effect; lines3D does not. The flow animation
      // is dropped once a single route is selected or the map is narrowed to a
      // hovered country, so the emphasis reads as a pinpoint, not a moving target.
      ...(isGlobe || hasSelection || hasHover
        ? {}
        : { effect: { show: data.length <= 60, period: 4, trailLength: 0.2, symbol: 'arrow', symbolSize: 5 } }),
      lineStyle: {
        color: layerColor(layer.id),
        width: isGlobe ? 1.4 : 1,
        opacity: isGlobe ? 0.75 : 0.5,
        curveness: 0.2,
      },
      data: lineData,
      tooltip: layer.tooltip ? { formatter: tooltipFormatter(layer) } : undefined,
    } as never);

    // Endpoint markers for the SELECTED route: two glowing nodes labelling the
    // countries the clicked link connects, so "what is traded between X and Y"
    // is readable straight off the map.
    const endpoints = hasSelection
      ? data.filter((d) => (d.data as { eventKey?: string }).eventKey === selectedEventKey)
          .flatMap((d) => {
            const p = d.data as { from: [number, number]; to: [number, number]; fromName?: string; toName?: string };
            return [
              { name: p.fromName ?? '', value: isGlobe ? p.from : [p.from[0], p.from[1], 1] },
              { name: p.toName ?? '', value: isGlobe ? p.to : [p.to[0], p.to[1], 1] },
            ];
          })
      : [];
    if (endpoints.length > 0) {
      series.push({
        id: `${layer.id}__endpoints`,
        name: layer.name,
        type: isGlobe ? 'scatter3D' : 'effectScatter',
        coordinateSystem: coordSystem,
        z: layer.zIndex + 1,
        silent: true,
        ...(isGlobe
          ? { symbolSize: 9, itemStyle: { color: layerColor(layer.id), opacity: 0.95 } }
          : {
              showEffectOn: 'render',
              rippleEffect: { brushType: 'stroke', scale: 3, period: 5 },
              symbolSize: 8,
              symbol: 'circle',
              itemStyle: { color: layerColor(layer.id), borderColor: 'rgba(8,9,12,0.9)', borderWidth: 1.5 },
            }),
        label: {
          show: true,
          position: 'right',
          formatter: (p: { name?: string }) => p.name ?? '',
          fontSize: 9,
          fontWeight: 600,
          color: '#f5f5f4',
          textShadowColor: 'rgba(2,8,20,0.9)',
          textShadowBlur: 3,
        },
        data: endpoints,
        tooltip: { show: false },
      } as never);
    }
  }

  // Country names, plotted at the gazetteer centroid as a scatter series whose
  // only visible element is the label. A separate series (rather than
  // `geo.label`) is used because it works IDENTICALLY in both projections: the
  // 2D geo component and the 3D globe both accept a point series, whereas the
  // globe has no component-level label support at all. It sits at a high z so
  // the names read over the land but under the event pins.
  if (options.showCountryLabels !== false && COUNTRY_LABELS.length > 0) {
    series.push({
      id: 'country-labels',
      name: 'Countries',
      type: isGlobe ? 'scatter3D' : 'scatter',
      coordinateSystem: coordSystem,
      z: 4,
      silent: true,
      symbolSize: 1,
      // The marker dot is hidden by a TRANSPARENT FILL, never by
      // `itemStyle.opacity: 0` and never by `symbol: 'none'`. Both of those drop
      // the label with it: the label inherits the item's visual opacity (so the
      // text rendered at alpha 0), and ECharts' `SymbolDraw`/`PointsBuilder`
      // skip label creation entirely for `symbol: 'none'`. A zero-alpha fill
      // leaves the symbol invisible while the label keeps its own colour, and
      // `label.opacity: 1` overrides the inherited visual opacity outright.
      itemStyle: { color: 'rgba(0,0,0,0)', opacity: 1 },
      label: {
        show: true,
        position: 'inside',
        opacity: 1,
        formatter: (p: { name?: string }) => p.name ?? '',
        // SMALL and light, matching the reference: a country name is background
        // context, not a headline. The app's own sans stack is named explicitly
        // so the labels match the terminal chrome instead of the browser default.
        fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        fontSize: 9,
        fontWeight: 500,
        color: isGlow ? 'rgba(190,222,248,0.82)' : 'rgba(210,216,224,0.82)',
        // A SOFT SHADOW, not a stroke. `textBorderColor` paints a hard outline
        // around every glyph, which at 9px reads as a smeared halo and makes the
        // text look worse, not more legible. A small shadow separates the name
        // from the land underneath without deforming the letterforms.
        textShadowColor: 'rgba(2,8,20,0.85)',
        textShadowBlur: 3,
        textShadowOffsetX: 0,
        textShadowOffsetY: 1,
      },
      emphasis: { label: { show: false } },
      tooltip: { show: false },
      data: COUNTRY_LABELS.map((c) => ({
        name: c.name,
        // Same altitude rule as every other globe point: exactly [lon, lat].
        value: isGlobe ? [c.lon, c.lat] : [c.lon, c.lat],
      })),
    } as never);
  }

  // Hovered-country outline on the GLOBE. `lines3D` with `polyline: true` draws
  // each ring as a closed path on the sphere. In 2D the geo component already
  // highlights a hovered country, so this series is globe-only. The series is
  // also emitted (empty) so `updateGlobeOutline` can mutate it in place on hover.
  if (isGlobe) {
    series.push(buildCountryOutlineSeries(options.highlightCountryRings ?? []) as never);
  }

  // Highlighted countries from NL search render as a ring of markers at their
  // centroids so the map visibly responds to a query even with no pin data.
  const highlightPoints = options.highlightPoints ?? [];

  // The camera distance is derived from the live container box so the sphere
  // fills the map (see `globeViewDistance`). echarts-gl measures `distance` from
  // the globe SURFACE and adds the radius itself, so the returned value is used
  // directly. The zoom-out floor is generous enough to let a user pull back.
  const globeDistance = globeViewDistance(options.width ?? 0, options.height ?? 0);
  const globeMinDistance = Math.max(1, globeDistance * 0.25);
  const globeMaxDistance = globeDistance * 2.5;

  const base = mode === 'globe'
    ? {
        globe: {
          /**
           * echarts-gl has NO `map` property — it takes a surface TEXTURE. Its
           * built-in default is a bright photographic world image that drowns
           * the pins; a solid dark texture (the previous approach) made the
           * sphere invisible on the dark page. `baseTexture` is therefore drawn
           * at runtime from the SAME GeoJSON the 2D map uses (see
           * `app-geo.worldGlobeTexture`) — deep-ocean gradient, lighter land and
           * a cyan coastline bloom — so the globe reads as a lit planet.
           * Callers pass it in because it is produced asynchronously.
           */
          baseTexture: options.globeTexture,
          globeRadius: GLOBE_RADIUS,
          // `lambert` keeps the land/shadows legible; `color` ignored the texture.
          shading: 'lambert' as const,
          // The sphere's untextured base. The texture supplies every visible
          // surface detail, so this only matters behind it. In light mode a
          // pale blue-grey keeps the sphere from reading as a black hole.
          color: isLight ? '#dbe3ee' : isGlow ? '#0b2f66' : '#2a2d33',
          // `black` is the plain grey planet: a mid-grey texture needs enough
          // ambient to actually read as grey rather than collapsing to black
          // under `lambert`. `glow` wants its blue surface lit, so it lifts the
          // ambient further and drops the shadowing.
          light: isLight
            ? {
                // A light planet needs a flat, bright ambient so the pale
                // texture reads as a solid sphere rather than a shaded blob.
                ambient: { intensity: 1 },
                main: { intensity: 0.45, shadow: false, alpha: 35, beta: 150 },
              }
            : isGlow
              ? {
                  ambient: { intensity: 0.62 },
                  main: { intensity: 0.7, shadow: false, alpha: 35, beta: 150 },
                }
              : {
                  ambient: { intensity: 0.85 },
                  main: { intensity: 0.5, shadow: false, alpha: 35, beta: 150 },
                },
          // ATMOSPHERE OFF ON PURPOSE. echarts-gl's atmosphere paints
          // `glowColor * pow(1 - dot(normal, viewDir), glowPower)`, which peaks
          // EXACTLY on the silhouette — a hard cyan ring hugging the sphere.
          // `glowPower` only changes the ring's thickness, never the fact that
          // it is a ring. The aura is instead an EMISSION LAYER (see `layers`),
          // whose shader adds light from the surface itself.
          atmosphere: { show: false },
          /**
           * The glow. `blendTo: 'emission'` runs the layer through
           * `gl_FragColor.rgb += texel.rgb * texel.a * intensity` — additive
           * light, so the coastline genuinely emits rather than being stroked.
           * `emissiveTexture` is a coastlines-only map drawn from the same
           * GeoJSON, so the ocean stays dark and the glow traces the land.
           *
           * `black` disables the layer entirely: an aura over a flat terminal
           * planet defeats the point of the plain skin.
           */
          layers: isGlow && !isLight && options.globeGlowTexture
            ? [{
                type: 'blend' as const,
                blendTo: 'emission' as const,
                texture: options.globeGlowTexture,
                // Additive light compounds, so this stays modest — the texture's
                // own alpha does most of the shaping.
                intensity: 0.85,
              }]
            : [],
          // The glow/bloom is a dark-planet language; a light page wants the
          // plain matte sphere, so it is disabled in light mode.
          postEffect: {
            enable: isGlow && !isLight,
            bloom: {
              enable: isGlow && !isLight,
              bloomIntensity: 0.26,
              bloomRadius: 0.5,
              bloomThreshold: 0.25,
            },
            SSAO: { enable: false },
          },
          viewControl: {
            // Auto-rotation is deliberately OFF: the pins are click targets, and
            // a moving target is a broken interaction. Dragging rotates freely.
            autoRotate: false,
            rotateSensitivity: 4,
            zoomSensitivity: 2,
            panSensitivity: 0,
            // Both are surface-relative (echarts-gl adds the radius), so this is
            // not a magic pixel number: it is derived from the container box so
            // the globe fills the map on any screen.
            distance: globeDistance,
            minDistance: globeMinDistance,
            maxDistance: globeMaxDistance,
          },
        },
      }
    : {
        geo: {
          ...baseGeo(skin, scheme),
          selectedMode: false,
        },
      };

  return {
    backgroundColor: 'transparent',
    animation: true,
    animationDuration: 300,
    ...base,
    tooltip: {
      ...(isLight ? LIGHT_TOOLTIP : GLASS_TOOLTIP),
      trigger: 'item',
      appendTo: 'body',
      confine: false,
    },
    // Severity-weighted heat legend. A warm ramp (violet → magenta → rose →
    // orange → yellow) so hotspots visibly CONTRAST the blue/cyan map surface
    // instead of blending into it; yellow is the "hottest" end.
    //
    // `seriesId` is CRITICAL: a continuous visualMap defaults to
    // `seriesIndex: 'all'`, so without it ECharts recoloured EVERY series from
    // its `value` — the event pins (whose value is a severity weight) were
    // re-tinted to the low/violet end and stayed that way after the heatmap was
    // switched off. Scoping the mapping to the heatmap series leaves every other
    // layer's own colouring untouched.
    ...(heatmapMax > 0 && heatmapSeriesId
      ? {
          visualMap: {
            show: true,
            type: 'continuous',
            seriesId: heatmapSeriesId,
            min: 0,
            max: heatmapMax,
            calculable: false,
            orient: 'vertical',
            right: 14,
            bottom: 40,
            text: ['HIGH', 'LOW'],
            textStyle: { color: '#9ca3af', fontSize: 10 },
            inRange: {
              color: ['#7c3aed', '#c026d3', '#f43f5e', '#f97316', '#facc15'],
            },
          },
        }
      : {}),
    series: [
      ...series,
      ...(highlightPoints.length > 0
        ? [
            {
              id: 'highlight',
              name: 'Search match',
              type: isGlobe ? 'scatter3D' : 'effectScatter',
              coordinateSystem: coordSystem,
              z: 95,
              ...(isGlobe
                ? { symbolSize: 12, silent: true, itemStyle: { color: '#60a5fa', opacity: 0.9 } }
                : {
                    showEffectOn: 'render',
                    rippleEffect: { brushType: 'stroke', scale: 4, period: 6 },
                    symbolSize: 14,
                    silent: true,
                    itemStyle: { color: 'rgba(96,165,250,0.0)', borderColor: '#60a5fa', borderWidth: 2 },
                  }),
              data: highlightPoints.map((h) => ({
                name: h.name,
                // Same altitude rule as above: no third element on the globe.
                value: isGlobe ? [h.lon, h.lat] : [h.lon, h.lat, 1],
              })),
            },
          ]
        : []),
    ],
  } as EChartsOption;
}

/**
 * Attach layer event handlers to a live chart. Kept separate from option
 * building so click/hover wiring never leaks into the option shape.
 */
export function bindLayerEvents(
  chart: { on: (event: string, handler: (params: unknown) => void) => void; off: (event: string) => void },
  layers: MapLayer[],
  handlers: {
    onEventClick?: (datum: LayerDatum, layer: MapLayer) => void;
    onMarketClick?: (datum: LayerDatum, layer: MapLayer) => void;
    onCountryClick?: (name: string) => void;
    /**
     * Fired when the pointer enters or leaves a country region on the 2D geo
     * map (`name` is the region name; `undefined` means the pointer left all
     * countries). Used to isolate the Trade routes that touch the country.
     */
    onCountryHover?: (name: string | undefined) => void;
  },
): void {
  chart.off('click');
  chart.on('click', (params: unknown) => {
    const p = params as { seriesId?: string; data?: LayerDatum & { _datum?: LayerDatum }; name?: string; componentType?: string };
    if (p.seriesId) {
      const layer = layers.find((l) => l.id === p.seriesId);
      const datum = unwrapDatum(p);
      if (layer && datum) {
        layer.onClick?.(datum);
        if (layer.id === 'events') handlers.onEventClick?.(datum, layer);
        if (layer.id === 'markets') handlers.onMarketClick?.(datum, layer);
        return;
      }
    }
    // A click with no series hit is a geo feature click (country).
    if (p.componentType === 'geo' && p.name) handlers.onCountryClick?.(p.name);
  });

  // Country hover (2D only — the globe resolves its own pick by raycast). A
  // region's `mouseover` carries the feature name; leaving it (or moving to a
  // non-region target) clears the hover.
  chart.off('mouseover');
  chart.off('mouseout');
  if (handlers.onCountryHover) {
    chart.on('mouseover', (params: unknown) => {
      const p = params as { componentType?: string; name?: string };
      if (p.componentType === 'geo' && p.name) handlers.onCountryHover?.(p.name);
    });
    chart.on('mouseout', (params: unknown) => {
      const p = params as { componentType?: string };
      if (p.componentType === 'geo') handlers.onCountryHover?.(undefined);
    });
  }
}
