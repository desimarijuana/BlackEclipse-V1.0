// ── Chart block → the chart engine's SPEC ────────────────────────────────────
//
// The pure, deterministic translation from a validated `chart` block to the
// Python chart engine's spec (`src/lib/harness/charts.ts`). It replaces the
// ECharts option builder that used to live here.
//
// Two rules this file keeps:
//
//   1. It NEVER invents data. A missing point stays missing; a category that
//      was not supplied is not fabricated; a block with no data produces no
//      spec at all (the caller shows the empty state).
//   2. A lossy mapping is TOLD, not hidden. The engine draws a fixed set of
//      kinds, so a block type the engine cannot draw exactly (a treemap, a
//      sunburst, a funnel, a gauge) is drawn as the closest honest shape and
//      the difference is reported in `notes` — the UI shows it under the
//      picture. A chart that quietly became a different chart would be a lie
//      about what the user is looking at.
//
// Keeping this out of the React component means the mapping is unit-testable
// without a DOM and the chart component stays thin.

import type { ChartBlock } from './contract';
import type { ChartSpec, ChartTheme } from '@/lib/harness/charts';

// ── Point helpers ───────────────────────────────────────────────────────────

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

/** A scalar point, a [x, y] pair or an [x, y, v] triple → a number. */
function pointValue(p: unknown): number | null {
  if (typeof p === 'number') return Number.isFinite(p) ? p : null;
  if (isPair(p)) return Number.isFinite(p[1]) ? p[1] : null;
  if (isTriple(p)) return Number.isFinite(p[2]) ? p[2] : null;
  return null;
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

const TEMPORAL_LABEL = new RegExp(
  '^(?:' +
    '\\d{4}(?:[-/]\\d{1,2}){0,2}' +          // 2026, 2026-03, 2026-03-14
    '|Q[1-4][\\s-]?\\d{4}' +                  // Q3 2026
    '|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\\s-]?\\d{1,4}' +
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

// ── The visual director ─────────────────────────────────────────────────────

/**
 * Choose a chart type when the block says `auto`.
 *
 * It reads only the SHAPE of what was supplied (labels, pairs, triples), never
 * the subject matter, and never invents a series. An explicit type always
 * wins, so a caller that knows better is never overridden.
 */
export function directChartType(block: ChartBlock): Exclude<ChartBlock['chartType'], 'auto'> {
  const categories = block.categories ?? [];
  // OHLC points ARE candles: a series of quadruples is a price chart, not a
  // line through the closes.
  if (block.series.some((s) => s.data.some(isOhlc))) return 'candlestick';
  const series = block.series ?? [];
  if (categories.length > 0) {
    if (looksTemporal(categories)) return 'line';
    if (series.length > 1) return 'line';
    return (series[0]?.data.length ?? 0) <= 12 ? 'bar' : 'line';
  }
  if (series.some((s) => s.data.some(isTriple))) return 'bubble';
  if (series.every((s) => pairsIn(s).length > 0 && monotonic(pairsIn(s)))) {
    return 'line';
  }
  if (series.some((s) => s.data.some(isPair))) return 'scatter';
  return 'line';
}

/** The type to draw: an explicit choice, or the director's decision for `auto`. */
export function resolveChartType(block: ChartBlock): Exclude<ChartBlock['chartType'], 'auto'> {
  return block.chartType === 'auto' ? directChartType(block) : block.chartType;
}

/** True when the block has enough data to be worth drawing. */
export function chartHasData(block: ChartBlock): boolean {
  if (block.panels && block.panels.length > 0) return true;
  // A NAMED series is data too: the engine fetches it.
  if (block.dataSource) return true;
  return (block.series ?? []).some((s) => Array.isArray(s.data) && s.data.some((p) => p != null));
}

// ── The mapping ─────────────────────────────────────────────────────────────

/** The engine kind a block type is drawn as, and whether that is a shortcut. */
const KIND_BY_BLOCK_TYPE: Record<
  Exclude<ChartBlock['chartType'], 'auto'>,
  { kind: ChartSpec['kind']; note?: string }
> = {
  line: { kind: 'line' },
  area: { kind: 'area' },
  bar: { kind: 'bar' },
  stacked_bar: { kind: 'stackedBar' },
  grouped_bar: { kind: 'bar' },
  pie: { kind: 'pie' },
  scatter: { kind: 'scatter' },
  bubble: { kind: 'scatter' },
  histogram: { kind: 'histogram' },
  heatmap: { kind: 'heatmap' },
  treemap: {
    kind: 'bar',
    note: 'Shown as a bar chart: the chart engine draws no treemap.',
  },
  sunburst: {
    kind: 'pie',
    note: 'Shown as a pie chart: the chart engine draws no sunburst.',
  },
  funnel: {
    kind: 'bar',
    note: 'Shown as a bar chart: the chart engine draws no funnel.',
  },
  gauge: {
    kind: 'bar',
    note: 'Shown as a bar chart: the chart engine draws no gauge.',
  },
  radar: { kind: 'radar' },
  waterfall: { kind: 'waterfall' },
  candlestick: { kind: 'candlestick' },
  ohlc: { kind: 'candlestick' },
  // A regression is drawn as a SCENE (the points, the fitted line, the R²),
  // so it is handled before this record is consulted.
  regression: { kind: 'scatter' },
};

/**
 * The points of a regression, taken from the block's OWN data.
 *
 * A pair is a point as it was given (`[x, y]`). A series of plain values is a
 * series over its categories: the categories become the x axis when they are
 * numbers, and the series order becomes the x axis when they are labels -
 * which is then said out loud in the notes, because a fit against the order
 * is not the same claim as a fit against the variable.
 */
function regressionPoints(block: ChartBlock): {
  x: number[];
  y: number[];
  note?: string;
} {
  const pairs: Array<[number, number]> = [];
  for (const series of block.series ?? []) {
    for (const point of series.data) {
      if (isPair(point)) pairs.push([point[0], point[1]]);
    }
  }
  if (pairs.length) {
    return { x: pairs.map((p) => p[0]), y: pairs.map((p) => p[1]) };
  }

  const categories = block.categories ?? [];
  const first = (block.series ?? [])[0];
  if (!first) return { x: [], y: [] };

  const x: number[] = [];
  const y: number[] = [];
  let note: string | undefined;
  const numericCategories =
    categories.length > 0 && categories.every((c) => typeof c === 'number');
  first.data.forEach((point, index) => {
    const value = pointValue(point);
    if (value == null) return;
    if (numericCategories) {
      const category = categories[index];
      if (typeof category !== 'number') return;
      x.push(category);
    } else {
      x.push(index);
    }
    y.push(value);
  });
  if (!numericCategories && x.length) {
    note =
      'Fitted against the series order: the categories are labels, not numbers.';
  }
  return { x, y, note };
}

/**
 * The scene spec: the block's panels and marks, as the engine takes them.
 *
 * The only thing translated is the field NAMES (the block is camelCase, the
 * engine is too) and the theme. The marks go through untouched: what the model
 * composed is what gets drawn.
 */
function sceneSpec(block: ChartBlock, options: ChartPlanOptions): ChartSpec {
  const panels = (block.panels ?? []).map((panel) => ({
    title: panel.title,
    xLabel: panel.xLabel,
    yLabel: panel.yLabel,
    valueFormat: panel.valueFormat,
    logScale: panel.logScale,
    height: panel.height,
    marks: panel.marks.map((mark) => ({
      type: mark.type,
      name: mark.name,
      dataSource: mark.dataSource,
      y: mark.y,
      // `data` is the alias a SERIES uses for its values; a mark may use it
      // too, and a [x, y] pair carries its own x.
      data: mark.data,
      x: mark.x,
      values: mark.values,
      lower: mark.lower,
      upper: mark.upper,
      sizes: mark.sizes,
      z: mark.z,
      matrix: mark.matrix,
      parents: mark.parents,
      colors: mark.colors,
      sources: mark.sources,
      targets: mark.targets,
      weights: mark.weights,
      labels: mark.labels,
      rowLabels: mark.rowLabels,
      colLabels: mark.colLabels,
      color: mark.color,
      alpha: mark.alpha,
      width: mark.width,
      style: mark.style,
      fill: mark.fill,
      label: mark.label,
      yAxis: mark.yAxis,
      stack: mark.stack,
      bins: mark.bins,
    })),
  }));
  return {
    kind: 'scene',
    title: options.includeTitle ? (block.title ?? undefined) : undefined,
    subtitle: options.includeTitle ? (block.description ?? undefined) : undefined,
    source: block.source ?? undefined,
    panels,
    theme: options.theme ?? 'eclipse-dark',
    width: options.width ?? 960,
    height: options.height ?? 520,
  };
}

export interface ChartPlan {
  /** The spec to send to the chart engine. */
  spec: ChartSpec;
  /** The engine kind the block was drawn as. */
  kind: ChartSpec['kind'];
  /** Honest notes about a lossy mapping (empty when the mapping is exact). */
  notes: string[];
}

export interface ChartPlanOptions {
  theme?: ChartTheme;
  width?: number;
  height?: number;
  /**
   * Draw the block's title INSIDE the picture. Off by default: the chat
   * already shows the title above the chart and the description below it, and
   * a picture that repeats them looks like a mistake.
   */
  includeTitle?: boolean;
}

function categoryNames(block: ChartBlock, count: number): string[] {
  const categories = block.categories ?? [];
  const names: string[] = [];
  for (let i = 0; i < count; i += 1) {
    const raw = categories[i];
    names.push(raw != null ? String(raw) : `#${i + 1}`);
  }
  return names;
}

/**
 * Translate a validated chart block into the chart engine's spec.
 *
 * Returns `null` when the block carries no drawable data — the caller shows
 * the empty state rather than an empty picture.
 */
export function chartBlockToSpec(
  block: ChartBlock,
  options: ChartPlanOptions = {},
): ChartPlan | null {
  // The SCENE form: the model composed the chart out of panels and marks, so
  // the engine draws exactly that. Nothing is invented and nothing is mapped.
  if (block.panels && block.panels.length > 0) {
    return { spec: sceneSpec(block, options), kind: 'scene', notes: [] };
  }

  if (!chartHasData(block)) return null;

  const blockType = resolveChartType(block);

  // ── regression ─────────────────────────────────────────────────────────
  // The points, the least-squares line through them and its R-squared. The
  // fit is computed by the engine from the same numbers the reader sees.
  if (blockType === 'regression') {
    // A NAMED series: the engine fetches it and fits it. The model never
    // types the prices, so the chart cannot be lost to a long message.
    if (block.dataSource) {
      const spec: ChartSpec = {
        kind: 'scene',
        title: options.includeTitle ? (block.title ?? undefined) : undefined,
        subtitle: options.includeTitle ? (block.description ?? undefined) : undefined,
        source: block.source ?? undefined,
        xLabel: block.xLabel ?? undefined,
        yLabel: block.yLabel ?? undefined,
        theme: options.theme ?? 'eclipse-dark',
        width: options.width ?? 960,
        height: options.height ?? 420,
        panels: [
          {
            xLabel: block.xLabel ?? undefined,
            yLabel: block.yLabel ?? undefined,
            marks: [
              {
                type: 'regression',
                name: block.dataSource.name ?? (block.series ?? [])[0]?.name ?? 'Series',
                dataSource: block.dataSource,
              },
            ],
          },
        ],
      };
      return { spec, kind: 'scene', notes: [] };
    }
    const { x, y, note } = regressionPoints(block);
    if (x.length < 2 || y.length < 2) return null;
    const spec: ChartSpec = {
      kind: 'scene',
      title: options.includeTitle ? (block.title ?? undefined) : undefined,
      subtitle: options.includeTitle ? (block.description ?? undefined) : undefined,
      source: block.source ?? undefined,
      xLabel: block.xLabel ?? undefined,
      yLabel: block.yLabel ?? undefined,
      theme: options.theme ?? 'eclipse-dark',
      width: options.width ?? 960,
      height: options.height ?? 420,
      panels: [
        {
          xLabel: block.xLabel ?? undefined,
          yLabel: block.yLabel ?? undefined,
          marks: [
            {
              type: 'regression',
              name: (block.series ?? [])[0]?.name || 'Observations',
              x,
              y,
            },
          ],
        },
      ],
    };
    return {
      spec,
      kind: 'scene',
      notes: note ? [note] : [],
    };
  }

  const mapping = KIND_BY_BLOCK_TYPE[blockType] ?? { kind: 'line' as const };
  const notes = mapping.note ? [mapping.note] : [];
  const kind = mapping.kind;

  const spec: ChartSpec = {
    kind,
    title: options.includeTitle ? (block.title ?? undefined) : undefined,
    subtitle: options.includeTitle ? (block.description ?? undefined) : undefined,
    source: block.source ?? undefined,
    xLabel: block.xLabel ?? undefined,
    yLabel: block.yLabel ?? undefined,
    theme: options.theme ?? 'eclipse-dark',
    width: options.width ?? 960,
    height: options.height ?? 420,
  };

  const first = (block.series ?? [])[0];

  // ── pie / donut ───────────────────────────────────────────────────────────
  if (kind === 'pie') {
    const values = first.data.map(pointValue);
    const labels = categoryNames(block, values.length);
    spec.labels = labels;
    spec.values = values.map((v) => (v == null ? 0 : v));
    return { spec, kind, notes };
  }

  // ── radar ────────────────────────────────────────────────────────────────
  if (kind === 'radar') {
    if (!first) return null;
    const values = first.data.map(pointValue);
    spec.labels = categoryNames(block, values.length);
    spec.values = values.map((v) => (v == null ? 0 : v));
    return { spec, kind, notes };
  }

  // ── waterfall ────────────────────────────────────────────────────────────
  if (kind === 'waterfall') {
    if (!first) return null;
    const values = first.data.map(pointValue);
    spec.categories = categoryNames(block, values.length);
    spec.series = [
      {
        name: first.name || 'Change',
        data: values.map((v) => v ?? 0),
        color: first.color ?? undefined,
      },
    ];
    return { spec, kind, notes };
  }

  // ── candlestick / ohlc ───────────────────────────────────────────────────
  if (kind === 'candlestick') {
    if (!first) return null;
    const candles = first.data
      .map((p) => (isOhlc(p) ? { open: p[0], high: p[1], low: p[2], close: p[3] } : null))
      .filter((c): c is { open: number; high: number; low: number; close: number } => c !== null);
    if (!candles.length) return null;
    spec.candles = candles;
    spec.categories = categoryNames(block, candles.length);
    return { spec, kind, notes };
  }

  // ── heatmap ──────────────────────────────────────────────────────────────
  if (kind === 'heatmap') {
    const rows = block.series ?? [];
    const width = Math.max(...rows.map((s) => s.data.length), 0);
    if (!width) return null;
    const matrix = rows.map((s) =>
      Array.from({ length: width }, (_, i) => pointValue(s.data[i]) ?? 0),
    );
    spec.matrix = matrix;
    spec.rowLabels = rows.map((s) => s.name);
    spec.colLabels = categoryNames(block, width);
    return { spec, kind, notes };
  }

  // ── scatter / bubble ─────────────────────────────────────────────────────
  if (kind === 'scatter') {
    const points: Array<{ x: number; y: number; label?: string; size?: number }> = [];
    for (const series of block.series ?? []) {
      for (const p of series.data) {
        if (!isPair(p)) continue;
        const point: { x: number; y: number; label?: string; size?: number } = {
          x: p[0],
          y: p[1],
        };
        if (isTriple(p)) point.size = Math.abs(p[2]);
        points.push(point);
      }
    }
    if (!points.length) return null;
    spec.points = points;
    if (blockType === 'bubble') {
      notes.push('Bubble sizes are shown as point sizes on a scatter chart.');
    }
    return { spec, kind, notes };
  }

  // ── histogram ────────────────────────────────────────────────────────────
  if (kind === 'histogram') {
    if (!first) return null;
    const values = first.data.map(pointValue);
    spec.series = [{ name: first.name || 'Values', data: values }];
    return { spec, kind, notes };
  }

  // ── line / area / bar ────────────────────────────────────────────────────
  const hasCategories = (block.categories?.length ?? 0) > 0;
  if (!hasCategories && (block.series ?? []).some((s) => s.data.some(isPair))) {
    // Points without categories and without a category axis are a scatter.
    const points: Array<{ x: number; y: number }> = [];
    for (const series of block.series ?? []) {
      for (const p of series.data) {
        if (!isPair(p)) continue;
        points.push({ x: p[0], y: p[1] });
      }
    }
    if (!points.length) return null;
    spec.kind = 'scatter';
    spec.points = points;
    notes.push('Plotted as points: the values carry no category axis.');
    return { spec, kind: 'scatter', notes };
  }

  const longest = Math.max(...(block.series ?? []).map((s) => s.data.length), 0);
  spec.categories = categoryNames(block, longest);
  const series: NonNullable<ChartSpec['series']> = (block.series ?? []).map((s) => {
    const entry: NonNullable<ChartSpec['series']>[number] = {
      name: s.name || 'Series 1',
      data: s.data.map(pointValue),
      color: s.color ?? undefined,
    };
    if (s.band && (s.band.lower.length || s.band.upper.length)) {
      entry.band = {
        lower: s.band.lower.map((v) => (Number.isFinite(v) ? v : null)),
        upper: s.band.upper.map((v) => (Number.isFinite(v) ? v : null)),
      };
    }
    return entry;
  });
  spec.series = series;
  if (blockType === 'stacked_bar' || block.stacked) spec.stacked = true;
  if (block.smooth) spec.smooth = true;
  if (blockType === 'histogram') spec.smooth = false;
  if (block.zoom) {
    notes.push('Zoom is not available on a drawn chart — the whole series is shown.');
  }
  return { spec, kind, notes };
}
