// ── Investor Eye — ECharts map adapter ───────────────────────────────────────
// Translates the provider-agnostic `MapLayer[]` into an ECharts option. This is
// the ONLY place that knows the map is drawn with ECharts; the layers, the
// component and the data layer stay visualization-agnostic (spec §44).
//
// Styling follows the BlackEclipse dark terminal language; tooltips follow the
// frosted-glass rules in `.opencode/skills/black-eclipse-ui/SKILL.md` (translucent
// tint ≤0.55, `appendTo: 'body'`, standard `backdrop-filter` only).

import type { EChartsOption } from 'echarts';
import { severityColor } from './layers';
import type { MapLayer, LayerDatum } from './types';

/** World map registration name — must match the GeoJSON `name` in app/geo.ts. */
export const WORLD_MAP_NAME = 'blackeclipse-world';

const GLASS_TOOLTIP = {
  backgroundColor: 'rgba(18,18,20,0.5)',
  borderColor: 'rgba(255,255,255,0.12)',
  borderWidth: 1,
  padding: [10, 12] as [number, number],
  textStyle: { color: '#e5e7eb', fontSize: 11 },
  extraCssText:
    'backdrop-filter: blur(18px) saturate(1.35); border-radius: 14px; ' +
    'box-shadow: 0 8px 30px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.06);',
};

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Build the tooltip HTML from a layer's structured `TooltipContent`. */
function tooltipFormatter(layer: MapLayer) {
  return (params: { data?: LayerDatum }): string => {
    const datum = params.data;
    if (!datum || !layer.tooltip) return '';
    const content = layer.tooltip(datum);
    const rows = content.rows
      .map(
        (r) =>
          `<div style="display:flex;justify-content:space-between;gap:16px;margin-top:3px">` +
          `<span style="color:#9ca3af">${escapeHtml(r.label)}</span>` +
          `<span style="color:#e5e7eb;font-weight:600;text-align:right">${escapeHtml(r.value)}</span>` +
          `</div>`,
      )
      .join('');
    const subtitle = content.subtitle
      ? `<div style="color:#9ca3af;margin-top:4px;max-width:280px;white-space:normal">${escapeHtml(content.subtitle)}</div>`
      : '';
    const note = content.note
      ? `<div style="color:#6b7280;font-size:10px;margin-top:6px;max-width:280px;white-space:normal;border-top:1px solid rgba(255,255,255,0.08);padding-top:5px">${escapeHtml(content.note)}</div>`
      : '';
    return (
      `<div style="min-width:180px;max-width:300px">` +
      `<div style="font-weight:700;font-size:12px;line-height:1.35;white-space:normal">${escapeHtml(content.title)}</div>` +
      subtitle + rows + note +
      `</div>`
    );
  };
}

const BASE_GEO = {
  map: WORLD_MAP_NAME,
  roam: true,
  zoom: 1.15,
  silent: false,
  itemStyle: {
    areaColor: '#141416',
    borderColor: 'rgba(255,255,255,0.10)',
    borderWidth: 0.5,
  },
  emphasis: {
    label: { show: false },
    itemStyle: { areaColor: '#1f2937', borderColor: 'rgba(255,255,255,0.25)' },
  },
  select: {
    label: { show: false },
    itemStyle: { areaColor: '#1e3a5f', borderColor: '#60a5fa' },
  },
  // The map is the hero: no competing labels until a country is hovered.
  label: { show: false },
};

export interface MapOptionOptions {
  layers: MapLayer[];
  /**
   * Countries highlighted by an NL search, with their centroids so the map can
   * visibly respond even when no event pins exist there.
   */
  highlightPoints?: Array<{ iso2: string; name: string; lon: number; lat: number }>;
}

/** Convert ISO2 → the ECharts map feature name is handled via `nameMap`. */
export function buildMapOption(options: MapOptionOptions): EChartsOption {
  const { layers } = options;
  const enabled = layers.filter((l) => l.enabled).sort((a, b) => a.zIndex - b.zIndex);

  const series: EChartsOption['series'] = [];

  // Country-fill layers first (they paint regions, not points).
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

  const pointSeriesTypes = new Set(['scatter', 'effect-scatter', 'symbol']);
  for (const layer of enabled) {
    if (!pointSeriesTypes.has(layer.type)) continue;
    const data = layer.data();
    const isEffect = layer.type === 'effect-scatter' && data.length <= 300;
    series.push({
      id: layer.id,
      name: layer.name,
      type: isEffect ? 'effectScatter' : 'scatter',
      coordinateSystem: 'geo',
      z: layer.zIndex,
      // Only animate when there is a small, curated set of points.
      ...(isEffect ? { showEffectOn: 'render', rippleEffect: { brushType: 'stroke', scale: 3, period: 5 } } : {}),
      symbolSize: (raw: unknown) => {
        const item = raw as { data?: { value?: number; severity?: string } };
        const sev = item.data?.severity ?? 'low';
        const base = { critical: 13, high: 10, medium: 8, low: 6 }[sev] ?? 6;
        return base;
      },
      itemStyle: {
        color: (raw: unknown) => {
          const item = raw as { data?: { severity?: string; value?: number } };
          if (item.data?.severity) return severityColor(item.data.severity as never);
          const v = item.data?.value ?? 0;
          return v >= 0 ? '#22c55e' : '#ef4444';
        },
        borderColor: 'rgba(0,0,0,0.5)',
        borderWidth: 0.5,
        opacity: 0.85,
      },
      emphasis: { scale: 1.4 },
      data: data.map((d) => ({
        name: d.label ?? d.id,
        value: [d.lon, d.lat, d.value ?? 1],
        severity: d.severity,
        _datum: d,
      })),
      tooltip: layer.tooltip ? { formatter: tooltipFormatter(layer) } : undefined,
    } as never);
  }

  // Directional lines (trade). `lines` needs explicit coords + data.
  for (const layer of enabled) {
    if (layer.type !== 'lines') continue;
    const data = layer.data();
    series.push({
      id: layer.id,
      name: layer.name,
      type: 'lines',
      coordinateSystem: 'geo',
      z: layer.zIndex,
      effect: { show: data.length <= 60, period: 4, trailLength: 0.2, symbol: 'arrow', symbolSize: 5 },
      lineStyle: { color: '#60a5fa', width: 1, opacity: 0.5, curveness: 0.2 },
      data: data.map((d) => {
        const payload = d.data as { from: [number, number]; to: [number, number] };
        return { coords: [payload.from, payload.to], _datum: d };
      }),
      tooltip: layer.tooltip ? { formatter: tooltipFormatter(layer) } : undefined,
    } as never);
  }

  // Highlighted countries from NL search render as a ring of markers at their
  // centroids so the map visibly responds to a query even with no pin data.
  const highlightPoints = options.highlightPoints ?? [];

  return {
    backgroundColor: 'transparent',
    animation: true,
    animationDuration: 300,
    geo: {
      ...BASE_GEO,
      selectedMode: false,
    },
    tooltip: {
      ...GLASS_TOOLTIP,
      trigger: 'item',
      appendTo: 'body',
      confine: false,
    },
    series: [
      ...series,
      ...(highlightPoints.length > 0
        ? [
            {
              id: 'highlight',
              name: 'Search match',
              type: 'effectScatter',
              coordinateSystem: 'geo',
              z: 95,
              showEffectOn: 'render',
              rippleEffect: { brushType: 'stroke', scale: 4, period: 6 },
              symbolSize: 14,
              silent: true,
              itemStyle: { color: 'rgba(96,165,250,0.0)', borderColor: '#60a5fa', borderWidth: 2 },
              data: highlightPoints.map((h) => ({
                name: h.name,
                value: [h.lon, h.lat, 1],
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
  },
): void {
  chart.off('click');
  chart.on('click', (params: unknown) => {
    const p = params as { seriesId?: string; data?: { _datum?: LayerDatum }; name?: string; componentType?: string };
    if (p.seriesId) {
      const layer = layers.find((l) => l.id === p.seriesId);
      const datum = p.data?._datum;
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
}
