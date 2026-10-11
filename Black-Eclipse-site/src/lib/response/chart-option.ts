// ── Chart block → ECharts option ─────────────────────────────────────────────
//
// Pure, deterministic translation from a validated `chart` block to an
// Apache ECharts option. Keeping this out of the React component means the
// mapping is unit-testable without a DOM and the chart component stays thin.
//
// It never invents data: missing categories/series render an empty-state, and
// a malformed point set is surfaced by the caller's empty() check.

import type { EChartsOption } from 'echarts';
import type { ChartBlock } from './contract';

export interface ChartPaletteColors {
  primary: string;
  series: string[];
}

const GRID_AXIS_COLOR = '#7a7a7a';

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
 * of truth.
 */
export function buildChartOption(
  block: ChartBlock,
  palette: ChartPaletteColors,
  _isDark = true,
): EChartsOption {
  const base: EChartsOption = {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'var(--font-sans, sans-serif)' },
    color: [palette.primary, ...palette.series],
    tooltip: {
      trigger: block.chartType === 'pie' || block.chartType === 'scatter' || block.chartType === 'heatmap' ? 'item' : 'axis',
      valueFormatter: valueFormatter(block),
      confine: true,
    },
    legend:
      block.legend && block.series.length > 1
        ? { bottom: 0, textStyle: { color: GRID_AXIS_COLOR, fontSize: 11 }, icon: 'roundRect' }
        : undefined,
    grid: { left: 6, right: 10, top: block.series.length > 1 && block.legend ? 24 : 12, bottom: block.legend && block.series.length > 1 ? 28 : 8, containLabel: true },
  };

  if (block.chartType === 'pie') {
    const first = block.series[0];
    const categories = block.categories ?? first.data.map((_, i) => String(i + 1));
    return {
      ...base,
      tooltip: { ...base.tooltip, trigger: 'item' },
      series: [
        {
          type: 'pie',
          radius: ['38%', '66%'],
          center: ['50%', '46%'],
          data: first.data.map((value, i) => ({
            name: String(categories[i] ?? i + 1),
            value: typeof value === 'number' ? value : Array.isArray(value) ? value[value.length - 1] : 0,
          })),
          label: { color: GRID_AXIS_COLOR, fontSize: 10 },
        },
      ],
    } as EChartsOption;
  }

  if (block.chartType === 'scatter') {
    return {
      ...base,
      xAxis: { type: 'value', name: block.xLabel, axisLabel: { color: GRID_AXIS_COLOR, fontSize: 10 }, splitLine: { show: false } },
      yAxis: { type: 'value', name: block.yLabel, scale: true, axisLabel: { color: GRID_AXIS_COLOR, fontSize: 10 }, splitLine: { show: false } },
      series: block.series.map((s, i) => ({
        type: 'scatter',
        name: s.name,
        data: s.data.filter(isPair),
        symbolSize: 8,
        itemStyle: { color: s.color ?? colorAt(palette, i), opacity: 0.75 },
      })),
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
      tooltip: { ...base.tooltip, trigger: 'item' },
      grid: { left: 6, right: 10, top: 12, bottom: 40, containLabel: true },
      xAxis: { type: 'category', data: xCats, axisLabel: { color: GRID_AXIS_COLOR, fontSize: 10 }, splitLine: { show: false } },
      yAxis: { type: 'category', data: yCats, axisLabel: { color: GRID_AXIS_COLOR, fontSize: 10 }, splitLine: { show: false } },
      visualMap: {
        min: Math.min(...data.map((d) => d[2] ?? 0)),
        max: Math.max(...data.map((d) => d[2] ?? 0)),
        calculable: true,
        orient: 'horizontal',
        left: 'center',
        bottom: 0,
        textStyle: { color: GRID_AXIS_COLOR, fontSize: 10 },
        inRange: { color: ['#1e293b', palette.primary] },
      },
      series: [{ type: 'heatmap', data, label: { show: false } }],
    } as EChartsOption;
  }

  // line / area / bar / stacked_bar / grouped_bar / histogram
  const isBar = block.chartType === 'bar' || block.chartType === 'stacked_bar' || block.chartType === 'grouped_bar' || block.chartType === 'histogram';
  const stacked = block.chartType === 'stacked_bar' || block.stacked;
  const categories = block.categories ?? undefined;
  const hasCategoryAxis = !!categories;
  const xType = hasCategoryAxis ? 'category' : block.series.some((s) => s.data.some(isPair)) ? 'value' : 'category';

  const series = block.series.map((s, i) => {
    const data = hasCategoryAxis || xType === 'category'
      ? s.data.map((p) => (typeof p === 'number' ? p : isPair(p) ? p[1] : p != null && isTriple(p) ? p[2] : null))
      : s.data;
    return {
      name: seriesName(block, i),
      type: isBar ? 'bar' : 'line',
      data,
      stack: stacked ? 'total' : undefined,
      smooth: block.smooth && !isBar,
      areaStyle: block.chartType === 'area' ? { opacity: 0.18 } : undefined,
      showSymbol: false,
      itemStyle: { color: s.color ?? colorAt(palette, i) },
      lineStyle: { width: 2 },
      barMaxWidth: 36,
    };
  });

  const zoom = block.zoom
    ? [{ type: 'inside' as const }, { type: 'slider' as const, height: 16, bottom: 2, textStyle: { color: GRID_AXIS_COLOR, fontSize: 9 } }]
    : undefined;

  return {
    ...base,
    xAxis: {
      type: xType as 'category' | 'value',
      data: hasCategoryAxis ? categories!.map(String) : undefined,
      name: block.xLabel,
      boundaryGap: isBar,
      axisLabel: { color: GRID_AXIS_COLOR, fontSize: 10 },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      name: block.yLabel,
      scale: true,
      axisLabel: { color: GRID_AXIS_COLOR, fontSize: 10 },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: false },
    },
    dataZoom: zoom,
    series,
  } as EChartsOption;
}
