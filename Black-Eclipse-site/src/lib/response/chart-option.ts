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

/** An OHLC candle point: [open, high, low, close]. */
function isOhlc(p: unknown): p is [number, number, number, number] {
  return (
    Array.isArray(p) &&
    p.length >= 4 &&
    p.every((v) => typeof v === 'number' && Number.isFinite(v))
  );
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

/** A scalar point, a [x, y] pair or an [x, y, v] triple → a number. */
function pointValue(p: unknown): number | null {
  if (typeof p === 'number') return p;
  if (isPair(p)) return p[1];
  if (isTriple(p)) return p[2];
  return null;
}

function categoryName(block: ChartBlock, index: number): string {
  const raw = block.categories?.[index];
  return raw != null ? String(raw) : `#${index + 1}`;
}

/** The smallest "nice" 1/2/5×10ⁿ value at or above `n` (gauge/radar maxima). */
function niceCeil(n: number): number {
  if (!Number.isFinite(n) || n <= 0) return 1;
  const magnitude = Math.pow(10, Math.floor(Math.log10(n)));
  const fraction = n / magnitude;
  const step = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
  return step * magnitude;
}

/** Chart types whose tooltip reads a single datum rather than an axis. */
const ITEM_TRIGGER_TYPES: ReadonlySet<ChartBlock['chartType']> = new Set([
  'pie', 'scatter', 'bubble', 'heatmap', 'treemap', 'sunburst', 'funnel', 'gauge', 'radar',
]);

const TEMPORAL_LABEL = new RegExp(
  '^(?:' +
    '\\d{4}(?:[-/]\\d{1,2}){0,2}' +          // 2026, 2026-03, 2026-03-14
    '|Q[1-4][\\s-]?\\d{4}' +                  // Q3 2026
    '|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\\.?[\\s-]\\d{1,4}' +
    '|\\d{1,2}:\\d{2}(?::\\d{2})?' +          // 09:30, 09:30:15
  ')$',
  'i',
);

function looksTemporal(values: ReadonlyArray<string | number>): boolean {
  let considered = 0;
  let matches = 0;
  for (const value of values) {
    const text = String(value).trim();
    if (!text) continue;
    considered += 1;
    if (typeof value === 'number') {
      // Epoch seconds/milliseconds and bare years both read as time on a chart.
      if (value >= 1_000 || Number.isInteger(value)) matches += 1;
    } else if (TEMPORAL_LABEL.test(text)) {
      matches += 1;
    }
  }
  return considered >= 2 && matches / considered >= 0.8;
}

function pairsIn(series: ChartBlock['series'][number]): Array<[number, number]> {
  return series.data.filter(isPair);
}

function monotonic(points: ReadonlyArray<[number, number]>): boolean {
  let direction = 0;
  for (let i = 1; i < points.length; i += 1) {
    const delta = points[i][0] - points[i - 1][0];
    if (delta === 0) continue;
    const next = delta > 0 ? 1 : -1;
    if (direction !== 0 && next !== direction) return false;
    direction = next;
  }
  return true;
}

/**
 * The visual director: choose a chart type when the planner says `auto`.
 *
 * It reads only the SHAPE of what was supplied (labels, pairs, triples), never
 * the subject matter, and never invents a series. An explicit type always wins,
 * so a caller that knows better is never overridden.
 */
export function directChartType(block: ChartBlock): Exclude<ChartBlock['chartType'], 'auto'> {
  const categories = block.categories ?? [];
  // OHLC points ARE candles: a series of quadruples is a price chart, not a
  // line through the closes.
  if (block.series.some((s) => s.data.some(isOhlc))) return 'candlestick';
  if (categories.length > 0) {
    if (looksTemporal(categories)) return 'line';
    if (block.series.length > 1) return 'line';
    return (block.series[0]?.data.length ?? 0) <= 12 ? 'bar' : 'line';
  }
  if (block.series.some((s) => s.data.some(isTriple))) return 'bubble';
  if (block.series.every((s) => pairsIn(s).length > 0 && monotonic(pairsIn(s)))) {
    return 'line';
  }
  if (block.series.some((s) => s.data.some(isPair))) return 'scatter';
  return 'line';
}

/** The type to draw: an explicit choice, or the director's decision for `auto`. */
export function resolveChartType(block: ChartBlock): Exclude<ChartBlock['chartType'], 'auto'> {
  return block.chartType === 'auto' ? directChartType(block) : block.chartType;
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
  const chartType = resolveChartType(block);

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
      trigger: ITEM_TRIGGER_TYPES.has(chartType) ? 'item' : 'axis',
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

  if (chartType === 'pie') {
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

  if (chartType === 'scatter') {
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

  if (chartType === 'heatmap') {
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

  if (chartType === 'bubble') {
    const magnitudes = block.series.flatMap((s) => s.data.filter(isTriple).map((p) => Math.abs(p[2])));
    const peak = Math.max(1, ...magnitudes);
    return {
      ...base,
      tooltip: { ...base.tooltip, trigger: 'item', axisPointer: undefined },
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
          data: s.data.filter(isTriple).map((p) => ({
            value: p,
            symbolSize: 8 + 34 * Math.sqrt(Math.abs(p[2]) / peak),
          })),
          itemStyle: { color, opacity: 0.72, borderColor: withAlpha(color, 0.5), borderWidth: 1 },
          emphasis: { focus: 'series' as const },
        };
      }),
    } as EChartsOption;
  }

  if (chartType === 'treemap' || chartType === 'sunburst') {
    const leaves = (s: ChartBlock['series'][number]) =>
      s.data.map((p, i) => ({ name: categoryName(block, i), value: pointValue(p) ?? 0 }));
    const treeData =
      block.series.length === 1
        ? leaves(block.series[0])
        : block.series.map((s, i) => ({ name: seriesName(block, i), children: leaves(s) }));
    const common = { tooltip: { ...base.tooltip, trigger: 'item' as const, axisPointer: undefined } };
    if (chartType === 'treemap') {
      return {
        ...base,
        ...common,
        series: [
          {
            type: 'treemap',
            data: treeData,
            roam: false,
            nodeClick: false,
            breadcrumb: { show: false },
            label: { color: '#0b0b0b', fontSize: 10 },
            upperLabel: { show: false },
            itemStyle: { borderColor: 'transparent', borderWidth: 1, gapWidth: 1 },
            emphasis: { focus: 'ancestor' as const },
          },
        ],
      } as EChartsOption;
    }
    return {
      ...base,
      ...common,
      series: [
        {
          type: 'sunburst',
          data: treeData,
          radius: [0, '92%'],
          center: ['50%', '50%'],
          nodeClick: false,
          label: { color: ink.axis, fontSize: 10, rotate: 'radial' },
          itemStyle: { borderColor: 'transparent', borderWidth: 1 },
          emphasis: { focus: 'ancestor' as const },
        },
      ],
    } as EChartsOption;
  }

  if (chartType === 'funnel') {
    const first = block.series[0];
    return {
      ...base,
      tooltip: { ...base.tooltip, trigger: 'item', axisPointer: undefined },
      series: [
        {
          type: 'funnel',
          left: '10%',
          right: '10%',
          top: 14,
          bottom: 14,
          width: '80%',
          minSize: '0%',
          maxSize: '100%',
          sort: 'none',
          gap: 2,
          label: { show: true, position: 'inside', color: '#0b0b0b', fontSize: 10 },
          labelLine: { show: false },
          itemStyle: { borderWidth: 0, borderRadius: 3 },
          emphasis: { label: { fontWeight: 'bold' as const } },
          data: first.data.map((p, i) => ({ name: categoryName(block, i), value: pointValue(p) ?? 0 })),
        },
      ],
    } as EChartsOption;
  }

  if (chartType === 'gauge') {
    const first = block.series[0];
    const values = block.series.flatMap((s) => s.data.map(pointValue)).filter((v): v is number => v != null);
    const value = first?.data.map(pointValue).find((v) => v != null) ?? 0;
    const max = values.length > 0 && values.every((v) => Math.abs(v) <= 1)
      ? 1
      : niceCeil(Math.max(...values.map(Math.abs), 0));
    return {
      ...base,
      tooltip: { ...base.tooltip, trigger: 'item', axisPointer: undefined },
      legend: undefined,
      series: [
        {
          type: 'gauge',
          min: 0,
          max,
          startAngle: 210,
          endAngle: -30,
          radius: '82%',
          center: ['50%', '58%'],
          progress: { show: true, width: 10, itemStyle: { color: palette.primary } },
          axisLine: { lineStyle: { width: 10, color: [[1, withAlpha(palette.primary, 0.16)]] } },
          axisTick: { show: false },
          splitLine: { length: 8, lineStyle: { color: ink.split } },
          axisLabel: { color: ink.label, fontSize: 9, distance: 12 },
          pointer: { width: 3, itemStyle: { color: palette.primary } },
          anchor: { show: true, size: 8, itemStyle: { color: palette.primary } },
          title: { color: ink.label, fontSize: 11, offsetCenter: [0, '30%'] },
          detail: {
            valueAnimation: true,
            formatter: (v: number) => valueFormatter(block)(v),
            color: ink.axis,
            fontSize: 20,
            offsetCenter: [0, '2%'],
          },
          data: [{ value, name: first?.name || block.title || '' }],
        },
      ],
    } as EChartsOption;
  }

  if (chartType === 'radar') {
    const categories = block.categories ?? [];
    const width = Math.max(...block.series.map((s) => s.data.length), categories.length, 1);
    const names = Array.from({ length: width }, (_, i) => categories[i] != null ? String(categories[i]) : `#${i + 1}`);
    const indicator = names.map((name, i) => {
      const peak = Math.max(...block.series.map((s) => Math.abs(pointValue(s.data[i]) ?? 0)), 0);
      return { name, max: niceCeil(peak) };
    });
    return {
      ...base,
      tooltip: { ...base.tooltip, trigger: 'item', axisPointer: undefined },
      radar: {
        indicator,
        radius: '64%',
        center: ['50%', '54%'],
        axisName: { color: ink.label, fontSize: 10 },
        axisLine: { lineStyle: { color: ink.split } },
        splitLine: { lineStyle: { color: ink.split } },
        splitArea: { show: false },
      },
      series: [
        {
          type: 'radar',
          symbolSize: 5,
          data: block.series.map((s, i) => {
            const color = s.color ?? colorAt(palette, i);
            return {
              name: s.name,
              value: s.data.map((p) => pointValue(p) ?? 0),
              itemStyle: { color },
              lineStyle: { color, width: 2 },
              areaStyle: { color, opacity: 0.12 },
            };
          }),
        },
      ],
    } as EChartsOption;
  }

  if (chartType === 'waterfall') {
    const first = block.series[0];
    const rise = palette.primary;
    const fall = palette.series[0] ?? '#ef4444';
    const values = first.data.map(pointValue);
    const bases: number[] = [];
    const bars: Array<{ value: number; itemStyle: { color: string } }> = [];
    let running = 0;
    for (const raw of values) {
      const value = raw ?? 0;
      if (value >= 0) {
        bases.push(running);
        bars.push({ value, itemStyle: { color: rise } });
      } else {
        bases.push(running + value);
        bars.push({ value: -value, itemStyle: { color: fall } });
      }
      running += value;
    }
    return {
      ...base,
      xAxis: {
        type: 'category',
        data: (block.categories ?? first.data.map((_, i) => String(i + 1))).map(String),
        boundaryGap: true,
        axisLabel: { color: ink.label, fontSize: 10, hideOverlap: true },
        axisLine: { show: true, lineStyle: { color: ink.split } },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        scale: true,
        name: block.yLabel,
        nameTextStyle: { color: ink.label, fontSize: 10 },
        axisLabel: { color: ink.label, fontSize: 10 },
        axisLine: { show: false },
        splitLine: { show: true, lineStyle: { color: ink.split, type: 'dashed' } },
      },
      series: [
        {
          name: '__base',
          type: 'bar',
          stack: 'waterfall',
          silent: true,
          itemStyle: { color: 'transparent' },
          emphasis: { itemStyle: { color: 'transparent' } },
          data: bases,
        },
        {
          name: first.name || 'Change',
          type: 'bar',
          stack: 'waterfall',
          barMaxWidth: 34,
          itemStyle: { borderRadius: [3, 3, 0, 0] },
          data: bars,
        },
      ],
    } as EChartsOption;
  }

  // candlestick / ohlc — the point is [open, high, low, close]; ECharts wants
  // [open, close, lowest, highest]. A point that is not a quadruple is a gap,
  // never a fabricated candle.
  if (chartType === 'candlestick' || chartType === 'ohlc') {
    const cats = (block.categories ?? []).map(String);
    return {
      ...base,
      tooltip: { ...base.tooltip, trigger: 'item', axisPointer: undefined },
      xAxis: {
        type: 'category',
        data: cats,
        axisLabel: { color: ink.label, fontSize: 10 },
        axisLine: { lineStyle: { color: ink.split } },
        splitLine: { show: false },
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
          name: seriesName(block, i),
          type: 'candlestick',
          data: s.data.map((p) => (isOhlc(p) ? [p[0], p[3], p[2], p[1]] : null)),
          itemStyle: {
            color,
            color0: withAlpha(color, 0.45),
            borderColor: color,
            borderColor0: withAlpha(color, 0.45),
          },
          emphasis: { focus: 'series' as const },
        };
      }),
    } as EChartsOption;
  }

  // line / area / bar / stacked_bar / grouped_bar / histogram
  const isBar = chartType === 'bar' || chartType === 'stacked_bar' || chartType === 'grouped_bar' || chartType === 'histogram';
  const stacked = chartType === 'stacked_bar' || block.stacked;
  const categories = block.categories ?? undefined;
  const hasCategoryAxis = !!categories;
  const xType = hasCategoryAxis ? 'category' : block.series.some((s) => s.data.some(isPair)) ? 'value' : 'category';

  const series: Array<Record<string, unknown>> = block.series.map((s, i) => {
    const color = s.color ?? colorAt(palette, i);
    const data = hasCategoryAxis || xType === 'category'
      ? s.data.map((p) => (typeof p === 'number' ? p : isPair(p) ? p[1] : p != null && isTriple(p) ? p[2] : null))
      : s.data;
    // Weight is presentation emphasis, not data: absent preserves the original
    // 2.4px line and full opacity.
    const opacity = s.weight == null ? 1 : 0.45 + 0.55 * s.weight;
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
        opacity: s.weight == null ? undefined : opacity,
      },
      lineStyle: {
        width: s.weight == null ? 2.4 : Math.round((1.2 + 2.4 * s.weight) * 100) / 100,
        cap: 'round' as const,
        join: 'round' as const,
        opacity,
      },
      areaStyle:
        chartType === 'area'
          ? {
              color: {
                type: 'linear' as const,
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
                colorStops: [
                  { offset: 0, color: withAlpha(color, 0.34 * opacity) },
                  { offset: 1, color: withAlpha(color, 0.02 * opacity) },
                ],
              },
            }
          : undefined,
      barMaxWidth: 34,
    };
  });

  // Weighted bands are drawn as a hidden stacked pair: `lower` (transparent)
  // plus `upper - lower` (tinted). Only category axes use the stack trick, so a
  // chart with [x, y] pairs simply omits the band rather than drawing it wrong.
  if (xType === 'category') {
    block.series.forEach((s, i) => {
      const band = s.band;
      if (!band) return;
      const color = s.color ?? colorAt(palette, i);
      const alpha = 0.08 + 0.22 * (band.weight ?? 0.5);
      const count = Math.min(band.lower.length, band.upper.length, s.data.length);
      const lower: Array<number | null> = [];
      const delta: Array<number | null> = [];
      for (let j = 0; j < count; j += 1) {
        const lo = band.lower[j];
        const hi = band.upper[j];
        if (!Number.isFinite(lo) || !Number.isFinite(hi) || hi < lo) {
          lower.push(null);
          delta.push(null);
        } else {
          lower.push(lo);
          delta.push(hi - lo);
        }
      }
      const stack = `eclipse-band-${i}`;
      const hidden = {
        type: 'line' as const,
        stack,
        silent: true,
        symbol: 'none',
        showSymbol: false,
        lineStyle: { opacity: 0 },
        emphasis: { disabled: true },
        tooltip: { show: false },
      };
      series.push(
        { ...hidden, name: `__band_lower_${i}`, data: lower, areaStyle: { opacity: 0 } },
        { ...hidden, name: `__band_${i}`, data: delta, areaStyle: { color: withAlpha(color, alpha) } },
      );
    });
  }

  const legendNames = block.series.map((_, i) => seriesName(block, i));
  const legend = base.legend
    ? { ...(base.legend as Record<string, unknown>), data: legendNames }
    : undefined;

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
    legend,
    series,
  } as EChartsOption;
}
