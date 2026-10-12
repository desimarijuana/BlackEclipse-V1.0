// ── Chart block → ECharts option ─────────────────────────────────────────────
//
// Pure, deterministic translation from a validated `chart` block to an
// Apache ECharts option. Keeping this out of the React component means the
// mapping is unit-testable without a DOM and the chart component stays thin.
//
// It never invents data: missing categories/series render an empty-state, and
// a malformed point set is surfaced by the caller's empty() check.
//
// Presentation follows the Eclipse frosted-glass system: transparent canvas,
// theme-aware ink, soft dashed gridlines, rounded bars, smooth lines and a
// translucent gradient under area series. The tooltip is intentionally left
// minimal here — the glass recipe (blur, `appendTo: 'body'`, shadow) lives in
// `baseChartOption()` and is merged by the caller, so it is never clobbered.

import type { EChartsOption } from 'echarts';
import type { ChartBlock } from './contract';

export interface ChartPaletteColors {
  primary: string;
  series: string[];
}

/**
 * Merge a block's built option over the shared base option, keeping the base's
 * frosted-glass tooltip chrome (translucent tint, `appendTo: 'body'`, blur,
 * rounded shadow) while honoring the block's own `trigger`/`valueFormatter`.
 * A plain `{ ...base, ...built }` spread would let the built (bare) tooltip
 * clobber the glass recipe — this is the bug this helper exists to prevent.
 */
export function mergeChartOption(base: EChartsOption, built: EChartsOption): EChartsOption {
  const baseTooltip = (base as { tooltip?: Record<string, unknown> }).tooltip ?? {};
  const builtTooltip = (built as { tooltip?: Record<string, unknown> }).tooltip ?? {};
  return { ...base, ...built, tooltip: { ...baseTooltip, ...builtTooltip } };
}

/** Theme-aware chart ink. ECharts/zrender cannot parse CSS `oklch`, so these
 *  are concrete rgba strings chosen to match the app's light/dark tokens. */
interface ChartInk {
  axis: string;
  label: string;
  split: string;
  pointer: string;
}

function chartInk(isDark: boolean): ChartInk {
  return isDark
    ? {
        axis: 'rgba(226,232,240,0.9)',
        label: 'rgba(148,163,184,0.85)',
        split: 'rgba(255,255,255,0.07)',
        pointer: 'rgba(148,163,184,0.45)',
      }
    : {
        axis: 'rgba(63,63,70,0.85)',
        label: 'rgba(82,82,91,0.8)',
        split: 'rgba(0,0,0,0.07)',
        pointer: 'rgba(82,82,91,0.4)',
      };
}

/** True when the block has enough data to be worth drawing. */
export function chartHasData(block: ChartBlock): boolean {
  return block.series.some((s) => Array.isArray(s.data) && s.data.some((p) => p != null));
}

function isPair(p: unknown): p is [number, number] {
  return Array.isArray(p) && p.length >= 2 && typeof p[0] === 'number';
}

function isTriple(p: unknown): p is [number, number, number] {
  return Array.isArray(p) && p.length >= 3;
}

function colorAt(palette: ChartPaletteColors, index: number): string {
  if (index === 0) return palette.primary;
  return palette.series[(index - 1) % palette.series.length] ?? palette.primary;
}

/** `#rrggbb` → `rgba(r,g,b,a)`. Anything unexpected is returned unchanged. */
function withAlpha(color: string, alpha: number): string {
  const hex = color.trim().replace(/^#/, '');
  const full = hex.length === 3 ? hex.split('').map((c) => c + c).join('') : hex;
  if (!/^[0-9a-fA-F]{6}$/.test(full)) return color;
  const r = parseInt(full.slice(0, 2), 16);
  const g = parseInt(full.slice(2, 4), 16);
  const b = parseInt(full.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function valueFormatter(block: ChartBlock): (value: unknown) => string {
  const currency = block.currency ? `${block.currency} ` : '';
  const unit = block.unit ? ` ${block.unit}` : '';
  return (value: unknown) => {
    if (typeof value !== 'number') return String(value ?? '');
    const abs = Math.abs(value);
    const body =
      abs >= 1e9
        ? `${(value / 1e9).toFixed(2)}B`
        : abs >= 1e6
          ? `${(value / 1e6).toFixed(2)}M`
          : abs >= 1e3
            ? `${(value / 1e3).toFixed(2)}K`
            : value.toLocaleString(undefined, { maximumFractionDigits: 4 });
    return `${currency}${body}${unit}`;
  };
}

function seriesName(block: ChartBlock, index: number): string {
  return block.series[index]?.name || `Series ${index + 1}`;
}

/**
 * Build the ECharts option for a chart block. `isDark` only affects grid/axis
 * ink; colours come from the caller so the terminal palette is the single source
 * of truth. The caller merges the frosted tooltip from `baseChartOption()`.
 */
export function buildChartOption(
  block: ChartBlock,
  palette: ChartPaletteColors,
  isDark = true,
): EChartsOption {
  const ink = chartInk(isDark);

  const axisPointer = {
    type: 'line' as const,
    lineStyle: { color: ink.pointer, width: 1, type: 'dashed' as const },
  };

  const base: EChartsOption = {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'var(--font-sans, sans-serif)' },
    color: [palette.primary, ...palette.series],
    animation: true,
    animationDuration: 620,
    animationEasing: 'cubicOut',
    tooltip: {
      trigger: block.chartType === 'pie' || block.chartType === 'scatter' || block.chartType === 'heatmap' ? 'item' : 'axis',
      valueFormatter: valueFormatter(block),
      axisPointer,
    },
    legend:
      block.legend && block.series.length > 1
        ? {
            bottom: 0,
            icon: 'circle',
            itemWidth: 8,
            itemHeight: 8,
            itemGap: 16,
            textStyle: { color: ink.label, fontSize: 11 },
          }
        : undefined,
    grid: {
      left: 8,
      right: 12,
      top: block.series.length > 1 && block.legend ? 26 : 14,
      bottom: block.legend && block.series.length > 1 ? 30 : 10,
      containLabel: true,
    },
  };

  if (block.chartType === 'pie') {
    const first = block.series[0];
    const categories = block.categories ?? first.data.map((_, i) => String(i + 1));
    return {
      ...base,
      tooltip: { ...base.tooltip, trigger: 'item', axisPointer: undefined },
      series: [
        {
          type: 'pie',
          radius: ['42%', '68%'],
          center: ['50%', '46%'],
          padAngle: 1.5,
          itemStyle: { borderColor: 'transparent', borderWidth: 2, borderRadius: 6 },
          data: first.data.map((value, i) => ({
            name: String(categories[i] ?? i + 1),
            value: typeof value === 'number' ? value : Array.isArray(value) ? value[value.length - 1] : 0,
          })),
          label: { color: ink.label, fontSize: 10 },
          labelLine: { lineStyle: { color: ink.split } },
          emphasis: { scale: true, scaleSize: 6 },
        },
      ],
    } as EChartsOption;
  }

  if (block.chartType === 'scatter') {
    return {
      ...base,
      xAxis: {
        type: 'value',
        name: block.xLabel,
        nameTextStyle: { color: ink.label, fontSize: 10 },
        axisLabel: { color: ink.label, fontSize: 10 },
        axisLine: { lineStyle: { color: ink.split } },
        splitLine: { show: true, lineStyle: { color: ink.split, type: 'dashed' } },
      },
      yAxis: {
        type: 'value',
        name: block.yLabel,
        scale: true,
        nameTextStyle: { color: ink.label, fontSize: 10 },
        axisLabel: { color: ink.label, fontSize: 10 },
        axisLine: { show: false },
        splitLine: { show: true, lineStyle: { color: ink.split, type: 'dashed' } },
      },
      series: block.series.map((s, i) => {
        const color = s.color ?? colorAt(palette, i);
        return {
          type: 'scatter',
          name: s.name,
          data: s.data.filter(isPair),
          symbolSize: 9,
          itemStyle: { color, opacity: 0.8, borderColor: withAlpha(color, 0.5), borderWidth: 1 },
          emphasis: { focus: 'series' as const },
        };
      }),
    } as EChartsOption;
  }

  if (block.chartType === 'heatmap') {
    const xCats = (block.categories ?? []).map(String);
    const yCats = block.series.map((s) => s.name);
    const data = block.series.flatMap((s, y) =>
      s.data.map((p, x) => (isTriple(p) ? [p[0], y, p[2]] : [x, y, typeof p === 'number' ? p : 0])),
    );
    return {
      ...base,
      tooltip: { ...base.tooltip, trigger: 'item', axisPointer: undefined },
      grid: { left: 6, right: 10, top: 12, bottom: 44, containLabel: true },
      xAxis: {
        type: 'category',
        data: xCats,
        axisLabel: { color: ink.label, fontSize: 10 },
        axisLine: { lineStyle: { color: ink.split } },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'category',
        data: yCats,
        axisLabel: { color: ink.label, fontSize: 10 },
        axisLine: { show: false },
        splitLine: { show: false },
      },
      visualMap: {
        min: Math.min(...data.map((d) => d[2] ?? 0)),
        max: Math.max(...data.map((d) => d[2] ?? 0)),
        calculable: true,
        orient: 'horizontal',
        left: 'center',
        bottom: 0,
        itemWidth: 12,
        itemHeight: 120,
        textStyle: { color: ink.label, fontSize: 10 },
        inRange: { color: [withAlpha(palette.primary, 0.12), palette.primary] },
      },
      series: [{ type: 'heatmap', data, itemStyle: { borderRadius: 3, borderColor: 'transparent', borderWidth: 2 }, label: { show: false } }],
    } as EChartsOption;
  }

  // line / area / bar / stacked_bar / grouped_bar / histogram
  const isBar = block.chartType === 'bar' || block.chartType === 'stacked_bar' || block.chartType === 'grouped_bar' || block.chartType === 'histogram';
  const stacked = block.chartType === 'stacked_bar' || block.stacked;
  const categories = block.categories ?? undefined;
  const hasCategoryAxis = !!categories;
  const xType = hasCategoryAxis ? 'category' : block.series.some((s) => s.data.some(isPair)) ? 'value' : 'category';

  const series = block.series.map((s, i) => {
    const color = s.color ?? colorAt(palette, i);
    const data = hasCategoryAxis || xType === 'category'
      ? s.data.map((p) => (typeof p === 'number' ? p : isPair(p) ? p[1] : p != null && isTriple(p) ? p[2] : null))
      : s.data;
    return {
      name: seriesName(block, i),
      type: isBar ? 'bar' : 'line',
      data,
      stack: stacked ? 'total' : undefined,
      smooth: !isBar,
      symbol: 'circle',
      showSymbol: false,
      symbolSize: 6,
      emphasis: { focus: 'series' as const },
      itemStyle: {
        color,
        borderRadius: isBar ? [5, 5, 0, 0] : undefined,
      },
      lineStyle: { width: 2.4, cap: 'round' as const, join: 'round' as const },
      areaStyle:
        block.chartType === 'area'
          ? {
              color: {
                type: 'linear' as const,
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
                colorStops: [
                  { offset: 0, color: withAlpha(color, 0.34) },
                  { offset: 1, color: withAlpha(color, 0.02) },
                ],
              },
            }
          : undefined,
      barMaxWidth: 34,
    };
  });

  const zoom = block.zoom
    ? [
        { type: 'inside' as const },
        { type: 'slider' as const, height: 16, bottom: 2, textStyle: { color: ink.label, fontSize: 9 } },
      ]
    : undefined;

  return {
    ...base,
    xAxis: {
      type: xType as 'category' | 'value',
      data: hasCategoryAxis ? categories!.map(String) : undefined,
      name: block.xLabel,
      nameTextStyle: { color: ink.label, fontSize: 10 },
      boundaryGap: isBar,
      axisLabel: { color: ink.label, fontSize: 10, hideOverlap: true },
      axisLine: { show: true, lineStyle: { color: ink.split } },
      axisTick: { show: false },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      name: block.yLabel,
      scale: true,
      nameTextStyle: { color: ink.label, fontSize: 10 },
      axisLabel: { color: ink.label, fontSize: 10 },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: true, lineStyle: { color: ink.split, type: 'dashed' } },
    },
    dataZoom: zoom,
    series,
  } as EChartsOption;
}
