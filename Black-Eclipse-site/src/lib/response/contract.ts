// ── Eclipse Interactive Response Contract (v1.0) ─────────────────────────────
//
// The versioned boundary between the agent/model and the UI. An assistant turn
// may carry a fenced ```eclipse-response JSON block (see ./parse.ts); this module
// owns the allowed shape, the strict per-block validation and the resource
// limits. It is deliberately presentation-only: no field here triggers code
// execution, a tool call, or a network request.
//
// Design rules (see docs/interactive-response-engine.md):
//  1. The envelope is validated loosely (unknown fields are stripped) so a newer
//     producer never bricks an older renderer.
//  2. Every block is validated INDIVIDUALLY. One malformed block degrades to a
//     diagnostic fallback; it never discards the rest of the answer.
//  3. Unknown block types are preserved as an `unknown` block with a diagnostic.
//  4. Hard limits (blocks, series, points, rows, nodes) are enforced at parse.
//  5. Numbers here are display values supplied by a deterministic producer
//     (the quant/finance engines) or the model's prose — never invented here.

import { z } from 'zod';

export const RESPONSE_SCHEMA_VERSION = '1.0';
export const RESPONSE_FENCE_LANGUAGE = 'eclipse-response';

/** Resource ceilings. Chosen to protect the renderer without breaking real
 *  research artifacts (see docs/security-and-limits in the engine doc). */
export const RESPONSE_LIMITS = {
  maxBlocks: 80,
  maxNestedDepth: 4,
  maxSeries: 24,
  maxPointsPerSeries: 5000,
  maxCategories: 5000,
  maxTableRows: 2000,
  maxTableColumns: 40,
  maxMetrics: 60,
  maxSources: 100,
  maxDiagramNodes: 120,
  maxDiagramEdges: 300,
  maxTimelineEvents: 200,
  maxTabs: 12,
  maxSteps: 100,
  maxCards: 40,
  maxSections: 40,
  maxActions: 12,
  maxArtifacts: 24,
  maxImages: 24,
  maxWorkflowStages: 40,
  maxStats: 4,
  maxGauges: 24,
  maxCompareColumns: 6,
  maxCompareRows: 60,
  maxRankedItems: 50,
  maxBadges: 60,
  maxSlides: 12,
  maxLearningNodes: 120,
  maxLearningResources: 200,
  maxMetadataKeys: 40,
  maxStringLength: 20000,
} as const;

/**
 * Spec-name → canonical-type aliases. The producer contract (see prompts.py)
 * documents one vocabulary, but the wider ecosystem names some blocks slightly
 * differently (`text`, `table`, `source_list`, `interactive_form`,
 * `execution_timeline`). Those names are normalized to their canonical block here
 * so a producer is never punished for a synonym; the renderer only ever sees the
 * canonical type.
 */
const BLOCK_TYPE_ALIASES: Record<string, string> = {
  text: 'markdown',
  table: 'data_table',
  source_list: 'citations',
  interactive_form: 'controls',
  execution_timeline: 'timeline',
  stat: 'stat_hero',
  stats: 'stat_hero',
  progress: 'gauge',
  meter: 'gauge',
  comparison: 'comparison_grid',
  leaderboard: 'ranked_list',
  ranking: 'ranked_list',
  badges: 'badge_row',
  slides: 'carousel',
};

/**
 * Field-name synonyms a producer may plausibly use for the same canonical
 * field. Like the type aliases above, these are normalized before validation so
 * a model is never punished for naming a body `content` instead of `markdown`.
 * Values that are not themselves valid are left untouched, so an unknown tone
 * still falls back to the schema default rather than hard-failing.
 */
const PROSE_FIELD_TYPES = new Set(['markdown', 'callout', 'details']);
const CALLOUT_TONES = new Set(['info', 'note', 'success', 'warning', 'danger']);

// Non-ambiguous interval synonyms (lower-cased). A model often writes `1Y` for a
// yearly view or `90d` for a three-month window, neither of which the
// `financial_chart` timeframe enum accepts; map the long/aliased forms onto the
// closest supported timeframe. Lower-case `m` is minutes and upper-case `M` is
// months in this app, so day-count forms map to the daily/weekly bars that span
// them rather than to a minute interval.
const TIMEFRAME_ALIASES: Record<string, string> = {
  '1y': '1M', '2y': '1M', '3y': '1M', '5y': '1M', '10y': '1M',
  ytd: '1M', max: '1M', all: '1M',
  '1d': '1D', day: '1D', daily: '1D',
  '7d': '1D', '14d': '1D', '30d': '1D', '60d': '1D', '90d': '1D', '180d': '1D', '365d': '1M',
  '1mo': '1M', month: '1M', monthly: '1M',
  '3mo': '1D', '6mo': '1D', '12mo': '1M',
  '1w': '1W', '1wk': '1W', week: '1W', weekly: '1W',
  '1h': '1H', hour: '1H',
};

// Financial-chart style synonyms a producer may use for the render style.
const FINANCIAL_CHART_TYPE_ALIASES: Record<string, string> = {
  candle: 'candlestick',
  candles: 'candlestick',
  candlesticks: 'candlestick',
  bar: 'ohlc',
  bars: 'ohlc',
  heikin_ashi: 'heikin-ashi',
  heikinashi: 'heikin-ashi',
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

/** `items`/`sources` entries may spell the label `name`; the contract wants `title`. */
function normalizeCitationSources(value: unknown): unknown {
  if (!Array.isArray(value)) return value;
  return value.map((item) => {
    if (!isRecord(item)) return item;
    if (item.title === undefined && typeof item.name === 'string') return { ...item, title: item.name };
    return item;
  });
}

/** A table may supply `columns` as bare strings; the contract wants `{ key, label }`. */
function normalizeTableColumns(value: unknown): unknown {
  if (!Array.isArray(value)) return value;
  return value.map((col, i) => {
    if (typeof col === 'string') return { key: `c${i}`, label: col || `Column ${i + 1}` };
    if (isRecord(col)) {
      const key = typeof col.key === 'string' && col.key ? col.key : `c${i}`;
      const label =
        typeof col.label === 'string' && col.label
          ? col.label
          : typeof col.key === 'string' && col.key
            ? col.key
            : `Column ${i + 1}`;
      return { ...col, key, label };
    }
    return col;
  });
}

/** A table may supply `rows` as positional arrays; the contract wants records keyed by column. */
function normalizeTableRows(value: unknown, columns: unknown): unknown {
  if (!Array.isArray(value)) return value;
  const keys = Array.isArray(columns)
    ? columns.map((c) => (isRecord(c) && typeof c.key === 'string' ? c.key : undefined))
    : [];
  return value.map((row) => {
    if (!Array.isArray(row)) return row;
    const record: Record<string, unknown> = {};
    row.forEach((cell, i) => {
      record[keys[i] ?? `c${i}`] = cell;
    });
    return record;
  });
}

/**
 * Chart points may arrive as objects rather than the contract's scalar / `[x, y]`
 * / `[x, y, v]` forms: `{x, y}` (a scatter point), `{x, y, value}` (an extra
 * dimension) or `{label, value}` / `{y}` (a labelled scalar on a category axis).
 * Coerce the recognised shapes and drop an unrecognised object to `null` so one
 * odd point never costs the whole chart (ECharts renders a gap; it is honest).
 */
function normalizeChartPoints(value: unknown): unknown {
  if (!Array.isArray(value)) return value;
  return value.map((p) => {
    if (!isRecord(p)) return p;
    const x = p.x;
    const y = p.y;
    if (typeof x === 'number' && typeof y === 'number') {
      const extra = p.v ?? p.z ?? p.value ?? p.r;
      return typeof extra === 'number' ? [x, y, extra] : [x, y];
    }
    const scalar = p.value ?? p.y ?? p.count;
    if (typeof scalar === 'number') return scalar;
    return null;
  });
}

/** A comparison grid may supply `columns` as bare strings or `{name}`; the contract wants `{ label }`. */
function normalizeComparisonColumns(value: unknown): unknown {
  if (!Array.isArray(value)) return value;
  return value.map((col, i) => {
    if (typeof col === 'string') return { label: col || `Option ${i + 1}` };
    if (isRecord(col)) {
      const label =
        typeof col.label === 'string' && col.label
          ? col.label
          : typeof col.name === 'string' && col.name
            ? col.name
            : typeof col.title === 'string' && col.title
              ? col.title
              : `Option ${i + 1}`;
      return { ...col, label };
    }
    return col;
  });
}

/** Map an item's `key`/`name`/`title` onto the contract's `label` when absent. */
function normalizeLabeledItems(value: unknown): unknown {
  if (!Array.isArray(value)) return value;
  return value.map((item) => {
    if (!isRecord(item) || item.label !== undefined) return item;
    const label = item.key ?? item.name ?? item.title;
    return typeof label === 'string' ? { ...item, label } : item;
  });
}

/** Normalize the field-level synonyms of an already-canonically-typed block. */
function normalizeBlockFields(raw: Record<string, unknown>): Record<string, unknown> {
  const type = typeof raw.type === 'string' ? raw.type : '';
  const out: Record<string, unknown> = { ...raw };

  if (PROSE_FIELD_TYPES.has(type) && out.markdown === undefined) {
    // Producers name the body `content` or, as often observed, `text` (the same
    // word as the `text`→`markdown` type alias). Neither is the canonical field;
    // both are accepted so the block is not lost. `heading` legitimately owns a
    // `text` field, so this rewrite is scoped to the prose body types only.
    if (out.content !== undefined) out.markdown = out.content;
    else if (typeof out.text === 'string') out.markdown = out.text;
  }

  if (type === 'mermaid' && out.diagram === undefined) {
    if (out.content !== undefined) out.diagram = out.content;
    else if (out.code !== undefined) out.diagram = out.code;
    else if (out.source !== undefined) out.diagram = out.source;
    else if (out.definition !== undefined) out.diagram = out.definition;
  }

  if (
    type === 'callout' &&
    out.tone === undefined &&
    typeof out.variant === 'string' &&
    CALLOUT_TONES.has(out.variant)
  ) {
    out.tone = out.variant;
  }

  if (type === 'citations') {
    if (out.sources === undefined && out.items !== undefined) out.sources = out.items;
    out.sources = normalizeCitationSources(out.sources);
  }

  if (type === 'data_table') {
    out.columns = normalizeTableColumns(out.columns);
    out.rows = normalizeTableRows(out.rows, out.columns);
  }

  if (type === 'key_value') {
    out.items = normalizeLabeledItems(out.items);
  }

  if (type === 'chart') {
    if (out.categories === undefined && out.labels !== undefined) out.categories = out.labels;
    if (Array.isArray(out.series)) {
      out.series = out.series.map((s) => {
        if (!isRecord(s)) return s;
        const next: Record<string, unknown> = { ...s };
        if (next.data === undefined) {
          if (next.points !== undefined) next.data = next.points;
          else if (next.values !== undefined) next.data = next.values;
        }
        next.data = normalizeChartPoints(next.data);
        if (next.name === undefined && typeof next.label === 'string') next.name = next.label;
        return next;
      });
    }
  }

  if (type === 'diagram' || type === 'node_graph') {
    out.nodes = normalizeLabeledItems(out.nodes);
    if (Array.isArray(out.edges)) {
      out.edges = out.edges.map((e) => {
        if (!isRecord(e)) return e;
        const next: Record<string, unknown> = { ...e };
        if (next.from === undefined && next.source !== undefined) next.from = next.source;
        if (next.to === undefined && next.target !== undefined) next.to = next.target;
        return next;
      });
    }
  }

  if (type === 'financial_chart') {
    if (out.symbol === undefined) {
      const sym = out.ticker ?? out.instrument ?? out.tickers;
      if (typeof sym === 'string') out.symbol = sym;
      else if (Array.isArray(sym) && typeof sym[0] === 'string') out.symbol = sym[0];
    }
    if (out.timeframe === undefined) {
      const tf = out.interval ?? out.range ?? out.period;
      if (typeof tf === 'string') out.timeframe = tf;
    }
    if (out.chartType === undefined) {
      const ct = out.style ?? out.chart_type;
      if (typeof ct === 'string') out.chartType = ct;
    }
    if (typeof out.timeframe === 'string') {
      const mapped = TIMEFRAME_ALIASES[out.timeframe.trim().toLowerCase()];
      if (mapped) out.timeframe = mapped;
    }
    if (typeof out.chartType === 'string') {
      const mapped = FINANCIAL_CHART_TYPE_ALIASES[out.chartType.trim().toLowerCase()];
      if (mapped) out.chartType = mapped;
    }
  }

  if (type === 'workflow' && out.stages === undefined && Array.isArray(out.steps)) {
    // The natural word for a workflow's stages is `steps`; accept it.
    out.stages = out.steps;
  }

  if (type === 'metric_grid' && Array.isArray(out.metrics)) {
    out.metrics = out.metrics.map((m) => {
      if (isRecord(m) && m.hint === undefined && m.note !== undefined) return { ...m, hint: m.note };
      return m;
    });
  }

  if (type === 'gallery' && Array.isArray(out.images)) {
    out.images = out.images.map((img) => {
      if (!isRecord(img)) return img;
      const next: Record<string, unknown> = { ...img };
      if (next.url === undefined && next.imageUrl !== undefined) next.url = next.imageUrl;
      if (next.alt === undefined && next.altText !== undefined) next.alt = next.altText;
      if (next.sourceUrl === undefined && next.sourcePage !== undefined) next.sourceUrl = next.sourcePage;
      if (next.sourceDomain === undefined && typeof next.domain === 'string') next.sourceDomain = next.domain;
      return next;
    });
  }

  if (type === 'stat_hero') {
    if (out.stats === undefined) {
      const alt = out.metrics ?? out.items ?? out.stats;
      if (alt !== undefined) out.stats = alt;
    }
    out.stats = normalizeLabeledItems(out.stats);
  }

  if (type === 'gauge') {
    if (out.gauges === undefined) {
      const alt = out.items ?? out.bars ?? out.gauges;
      if (alt !== undefined) out.gauges = alt;
    }
    out.gauges = normalizeLabeledItems(out.gauges);
  }

  if (type === 'comparison_grid') {
    out.columns = normalizeComparisonColumns(out.columns);
  }

  if (type === 'ranked_list') {
    if (out.items === undefined) {
      const alt = out.entries ?? out.items;
      if (alt !== undefined) out.items = alt;
    }
    out.items = normalizeLabeledItems(out.items);
  }

  if (type === 'badge_row') {
    if (out.badges === undefined) {
      const alt = out.items ?? out.badges;
      if (alt !== undefined) out.badges = alt;
    }
    out.badges = normalizeLabeledItems(out.badges);
  }

  if (type === 'carousel' && out.slides === undefined) {
    const alt = out.items ?? out.tabs;
    if (alt !== undefined) out.slides = alt;
  }

  return out;
}

/**
 * Rewrite a raw block into its canonical shape before validation: first the
 * documented `type` aliases (`text`, `table`, `source_list`, …), then the
 * field-level synonyms (`content`→`markdown`, `variant`→`tone`,
 * `items`→`sources`, string table columns / positional rows, interval aliases).
 * Pure and total: a non-object block is returned unchanged.
 */
export function normalizeBlockAlias(raw: unknown): unknown {
  if (!isRecord(raw)) return raw;
  const declared = raw.type;
  if (typeof declared !== 'string') return raw;
  const canonical = BLOCK_TYPE_ALIASES[declared];
  const renamed = canonical ? { ...raw, type: canonical } : raw;
  return normalizeBlockFields(renamed);
}

const boundedString = z.string().max(RESPONSE_LIMITS.maxStringLength);
const shortString = z.string().max(500);
const idString = z.string().min(1).max(120);

const numberOrNumericString = z.union([z.number().finite(), z.string().max(120)]);

// Only absolute http(s) URLs may become links. `z.string().url()` alone accepts
// `javascript:`/`data:` schemes, which would be an XSS vector once rendered as an
// anchor href — so every model-supplied link is scheme-restricted here.
const httpUrl = z
  .string()
  .url()
  .refine(
    (value) => {
      try {
        const protocol = new URL(value).protocol;
        return protocol === 'http:' || protocol === 'https:';
      } catch {
        return false;
      }
    },
    { message: 'Only http(s) URLs are allowed' },
  );

// A chart/timeline point may be a scalar, an [x, y] pair or a [x, y, v] triple.
const pointSchema = z.union([
  z.number().finite(),
  z.tuple([z.number().finite(), z.number().finite()]),
  z.tuple([z.number().finite(), z.number().finite(), z.number().finite()]),
  z.null(),
]);

// ── Content blocks ────────────────────────────────────────────────────────────

const markdownBlock = z.object({
  type: z.literal('markdown'),
  id: idString.optional(),
  markdown: boundedString,
});

const headingBlock = z.object({
  type: z.literal('heading'),
  id: idString.optional(),
  text: shortString,
  level: z.number().int().min(1).max(4).default(2),
});

const calloutBlock = z.object({
  type: z.literal('callout'),
  id: idString.optional(),
  tone: z.enum(['info', 'note', 'success', 'warning', 'danger']).default('info'),
  title: shortString.optional(),
  markdown: boundedString,
});

const keyValueBlock = z.object({
  type: z.literal('key_value'),
  id: idString.optional(),
  title: shortString.optional(),
  items: z
    .array(
      z.object({
        label: shortString,
        value: numberOrNumericString,
        hint: shortString.optional(),
      }),
    )
    .max(RESPONSE_LIMITS.maxMetrics),
});

const detailsBlock = z.object({
  type: z.literal('details'),
  id: idString.optional(),
  summary: shortString,
  markdown: boundedString,
  open: z.boolean().default(false),
});

// ── Data blocks ───────────────────────────────────────────────────────────────

const metricSchema = z.object({
  label: shortString,
  value: numberOrNumericString,
  unit: shortString.optional(),
  prefix: shortString.optional(),
  delta: numberOrNumericString.optional(),
  deltaTone: z.enum(['up', 'down', 'flat', 'neutral']).optional(),
  hint: shortString.optional(),
  unavailable: z.boolean().optional(),
});

const metricGridBlock = z.object({
  type: z.literal('metric_grid'),
  id: idString.optional(),
  title: shortString.optional(),
  source: shortString.optional(),
  asOf: shortString.optional(),
  columns: z.number().int().min(1).max(6).optional(),
  metrics: z.array(metricSchema).min(1).max(RESPONSE_LIMITS.maxMetrics),
});

const tableColumnSchema = z.object({
  key: idString,
  label: shortString,
  align: z.enum(['left', 'center', 'right']).optional(),
  hint: shortString.optional(),
});

const tableCellSchema = z.union([z.string().max(2000), z.number().finite(), z.boolean(), z.null()]);

const dataTableBlock = z.object({
  type: z.literal('data_table'),
  id: idString.optional(),
  title: shortString.optional(),
  caption: shortString.optional(),
  source: shortString.optional(),
  asOf: shortString.optional(),
  columns: z.array(tableColumnSchema).min(1).max(RESPONSE_LIMITS.maxTableColumns),
  rows: z.array(z.record(z.string(), tableCellSchema)).max(RESPONSE_LIMITS.maxTableRows),
  filterable: z.boolean().default(true),
  sortable: z.boolean().default(true),
  pageSize: z.number().int().min(5).max(200).default(25),
});

// ── Visualization blocks ──────────────────────────────────────────────────────

export const CHART_TYPES = [
  'line',
  'area',
  'bar',
  'stacked_bar',
  'grouped_bar',
  'pie',
  'scatter',
  'histogram',
  'heatmap',
] as const;

const chartSeriesSchema = z.object({
  name: shortString,
  data: z.array(pointSchema).max(RESPONSE_LIMITS.maxPointsPerSeries),
  color: z
    .string()
    .regex(/^#[0-9a-fA-F]{3,8}$/)
    .optional(),
});

const chartBlock = z.object({
  type: z.literal('chart'),
  id: idString.optional(),
  chartType: z.enum(CHART_TYPES),
  title: shortString.optional(),
  description: shortString.optional(),
  source: shortString.optional(),
  asOf: shortString.optional(),
  unit: shortString.optional(),
  currency: z.string().max(8).optional(),
  xLabel: shortString.optional(),
  yLabel: shortString.optional(),
  categories: z.array(z.union([z.string().max(80), z.number()])).max(RESPONSE_LIMITS.maxCategories).optional(),
  series: z.array(chartSeriesSchema).min(1).max(RESPONSE_LIMITS.maxSeries),
  legend: z.boolean().default(true),
  zoom: z.boolean().default(false),
  smooth: z.boolean().default(false),
  stacked: z.boolean().default(false),
});

const diagramNodeSchema = z.object({
  id: idString,
  label: shortString,
  tone: z.enum(['neutral', 'info', 'success', 'warning', 'danger']).default('neutral'),
  group: shortString.optional(),
});

const diagramEdgeSchema = z.object({
  from: idString,
  to: idString,
  label: shortString.optional(),
  tone: z.enum(['neutral', 'info', 'success', 'warning', 'danger']).default('neutral'),
  dashed: z.boolean().optional(),
});

const diagramBlock = z.object({
  type: z.literal('diagram'),
  id: idString.optional(),
  title: shortString.optional(),
  description: shortString.optional(),
  diagramType: z.enum(['flowchart', 'dependency', 'state']).default('flowchart'),
  direction: z.enum(['TB', 'LR']).default('TB'),
  nodes: z.array(diagramNodeSchema).min(1).max(RESPONSE_LIMITS.maxDiagramNodes),
  edges: z.array(diagramEdgeSchema).max(RESPONSE_LIMITS.maxDiagramEdges).default([]),
});

const timelineEventSchema = z.object({
  time: shortString,
  title: shortString,
  description: boundedString.optional(),
  tone: z.enum(['neutral', 'info', 'success', 'warning', 'danger']).default('neutral'),
});

const timelineBlock = z.object({
  type: z.literal('timeline'),
  id: idString.optional(),
  title: shortString.optional(),
  events: z.array(timelineEventSchema).min(1).max(RESPONSE_LIMITS.maxTimelineEvents),
});

const citationSourceSchema = z.object({
  title: shortString,
  url: httpUrl.optional(),
  source: shortString.optional(),
  snippet: boundedString.optional(),
  retrievedAt: shortString.optional(),
  publishedAt: shortString.optional(),
});

const citationsBlock = z.object({
  type: z.literal('citations'),
  id: idString.optional(),
  title: shortString.optional(),
  sources: z.array(citationSourceSchema).max(RESPONSE_LIMITS.maxSources),
});

// ── Interaction / layout blocks ───────────────────────────────────────────────

// `tabs` nests raw child block arrays; they are validated recursively by the
// parser (depth-bounded) rather than by this schema, which keeps the union
// non-recursive and cheap to build.
const tabsBlock = z.object({
  type: z.literal('tabs'),
  id: idString.optional(),
  tabs: z
    .array(
      z.object({
        label: shortString,
        blocks: z.array(z.unknown()),
      }),
    )
    .min(1)
    .max(RESPONSE_LIMITS.maxTabs),
});

// ── Financial chart / Mermaid / Controls ─────────────────────────────────────

export const FINANCIAL_TIMEFRAMES = ['1m', '3m', '5m', '15m', '30m', '1H', '2H', '4H', '1D', '1W', '1M'] as const;
export const FINANCIAL_CHART_TYPES = ['candlestick', 'ohlc', 'line', 'area', 'baseline', 'heikin-ashi', 'histogram'] as const;

// A reference to the EXISTING terminal chart (ChartWidget). The block carries a
// symbol + optional view state; it does NOT carry raw OHLCV data (the chart
// fetches from the live data layer, so it is never stale or fabricated).
const financialChartBlock = z.object({
  type: z.literal('financial_chart'),
  id: idString.optional(),
  symbol: shortString,
  market: z.string().max(16).optional(),
  timeframe: z.enum(FINANCIAL_TIMEFRAMES).optional(),
  chartType: z.enum(FINANCIAL_CHART_TYPES).optional(),
  title: shortString.optional(),
  source: shortString.optional(),
  asOf: shortString.optional(),
});

// Declarative technical diagram (Mermaid syntax). Rendered with Mermaid's strict
// security level in a sandboxed, lazily-loaded client component.
const mermaidBlock = z.object({
  type: z.literal('mermaid'),
  id: idString.optional(),
  title: shortString.optional(),
  description: shortString.optional(),
  diagram: boundedString,
});

const controlSchema = z.discriminatedUnion('kind', [
  z.object({
    kind: z.literal('select'),
    id: idString,
    label: shortString,
    options: z.array(z.object({ value: shortString, label: shortString })).min(1).max(50),
    default: shortString.optional(),
  }),
  z.object({
    kind: z.literal('date_range'),
    id: idString,
    label: shortString,
    default: z.object({ from: shortString, to: shortString }).optional(),
  }),
  z.object({
    kind: z.literal('slider'),
    id: idString,
    label: shortString,
    min: z.number().finite(),
    max: z.number().finite(),
    step: z.number().positive().optional(),
    default: z.number().optional(),
  }),
  z.object({
    kind: z.literal('text'),
    id: idString,
    label: shortString,
    placeholder: shortString.optional(),
    default: shortString.optional(),
  }),
]);

// Interactive parameters. Submitting composes a follow-up prompt and re-enters
// the EXISTING agent loop (no new backend contract) — every value is validated
// before it is interpolated into `promptTemplate`.
const controlsBlock = z.object({
  type: z.literal('controls'),
  id: idString.optional(),
  title: shortString.optional(),
  description: boundedString.optional(),
  controls: z.array(controlSchema).min(1).max(12),
  submitLabel: shortString.optional(),
  promptTemplate: boundedString.optional(),
});

// ── Process / report / action blocks ───────────────────────────────────────────

const stepSchema = z.object({
  title: shortString,
  description: boundedString.optional(),
  status: z.enum(['pending', 'active', 'done', 'error']).default('pending'),
  hint: shortString.optional(),
});

// A numbered process: ordered, each step carry a status. Distinct from
// `timeline` (which is time-stamped events); a stepper is procedural.
const stepperBlock = z.object({
  type: z.literal('stepper'),
  id: idString.optional(),
  title: shortString.optional(),
  description: shortString.optional(),
  steps: z.array(stepSchema).min(1).max(RESPONSE_LIMITS.maxSteps),
});

const infographicCardSchema = z.object({
  icon: shortString.optional(),
  label: shortString,
  value: numberOrNumericString.optional(),
  unit: shortString.optional(),
  description: boundedString.optional(),
  tone: z.enum(['neutral', 'info', 'success', 'warning', 'danger']).default('neutral'),
  unavailable: z.boolean().optional(),
});

// Icon-based cards composed of native components (never a generated image). The
// `icon` key is resolved against an allowlist at render; an unknown key degrades
// to a neutral default — the model never names a component or import path.
const infographicBlock = z.object({
  type: z.literal('infographic'),
  id: idString.optional(),
  title: shortString.optional(),
  description: shortString.optional(),
  columns: z.number().int().min(1).max(4).optional(),
  cards: z.array(infographicCardSchema).min(1).max(RESPONSE_LIMITS.maxCards),
});

const workflowStageSchema = z.object({
  id: idString.optional(),
  icon: shortString.optional(),
  title: shortString,
  description: boundedString.optional(),
  detail: boundedString.optional(),
  tone: z.enum(['neutral', 'info', 'success', 'warning', 'danger']).default('neutral'),
  status: z.enum(['pending', 'active', 'done', 'error']).optional(),
  inputs: z.array(shortString).max(12).optional(),
  outputs: z.array(shortString).max(12).optional(),
});

// An icon-driven, CONNECTED process flow: ordered stages joined by directional
// connectors, each expandable to reveal `detail` / inputs / outputs. Distinct
// from `stepper` (a numbered status list with no icons or connectors) and from
// `diagram`/`node_graph` (free-form node/edge graphs). The producer returns
// structured stages only — never an image, SVG, HTML or code.
const workflowBlock = z.object({
  type: z.literal('workflow'),
  id: idString.optional(),
  title: shortString.optional(),
  summary: boundedString.optional(),
  layout: z.enum(['vertical', 'horizontal', 'auto']).default('auto'),
  stages: z.array(workflowStageSchema).min(1).max(RESPONSE_LIMITS.maxWorkflowStages),
});

const reportSectionSchema = z.object({
  heading: shortString.optional(),
  markdown: boundedString.optional(),
  tone: z.enum(['neutral', 'info', 'success', 'warning', 'danger']).default('neutral'),
  // Nested blocks are validated recursively by the parser (depth-bounded), like
  // `tabs`, so a section may contain its own table/chart/diagram.
  blocks: z.array(z.unknown()).optional(),
});

// A readable multi-section report: the natural container for a long
// evidence-backed answer that mixes prose, tables and charts.
const reportBlock = z.object({
  type: z.literal('report'),
  id: idString.optional(),
  title: shortString.optional(),
  summary: boundedString.optional(),
  sections: z.array(reportSectionSchema).min(1).max(RESPONSE_LIMITS.maxSections),
});

const nodeGraphNodeSchema = z.object({
  id: idString,
  label: shortString,
  tone: z.enum(['neutral', 'info', 'success', 'warning', 'danger']).default('neutral'),
  group: shortString.optional(),
  detail: boundedString.optional(),
});

// Unlike `diagram` (a static picture of relationships), a `node_graph` is a
// SELECTABLE graph: clicking a node reveals its `detail`. The same layered
// layout engine drives both.
const nodeGraphBlock = z.object({
  type: z.literal('node_graph'),
  id: idString.optional(),
  title: shortString.optional(),
  description: shortString.optional(),
  direction: z.enum(['TB', 'LR']).default('LR'),
  height: z.number().int().min(200).max(800).optional(),
  nodes: z.array(nodeGraphNodeSchema).min(1).max(RESPONSE_LIMITS.maxDiagramNodes),
  edges: z.array(diagramEdgeSchema).max(RESPONSE_LIMITS.maxDiagramEdges).default([]),
});

const learningResourceSchema = z.object({
  resourceId: idString,
  title: shortString,
  url: httpUrl,
  // The resource's own source type (video, course, documentation, repository…).
  type: shortString.optional(),
  author: shortString.optional(),
  durationSeconds: z.number().int().nonnegative().optional(),
  thumbnail: httpUrl.optional(),
  cost: z.enum(['free', 'paid', 'unknown']).optional(),
  // WHY this resource is recommended for the node (one short, honest sentence).
  reason: boundedString.optional(),
});

const learningNodeSchema = z.object({
  id: idString,
  label: shortString,
  level: z.enum(['beginner', 'intermediate', 'advanced', 'unspecified']).default('unspecified'),
  group: shortString.optional(),
  detail: boundedString.optional(),
  objectives: z.array(shortString).max(20).default([]),
  // Prerequisite skill ids (the edges of the curriculum DAG).
  requires: z.array(idString).max(40).default([]),
  resourceIds: z.array(idString).max(20).default([]),
  exercises: z.array(shortString).max(20).default([]),
  project: shortString.optional(),
  assessment: boundedString.optional(),
  milestone: shortString.optional(),
  estimatedHours: z.number().nonnegative().optional(),
  status: z.enum(['pending', 'in_progress', 'completed', 'skipped']).default('pending'),
});

// An interactive, prerequisite-aware learning roadmap rendered directly in the
// chat. Unlike `node_graph` (read-only selectable nodes), each skill node carries
// completion controls that PERSIST through `/api/learning/progress` when a
// `pathId` is present, plus resource links, exercises and assessments. The
// underlying curriculum is real data (built by the learning engine), never a
// generated image.
const learningMapBlock = z.object({
  type: z.literal('learning_map'),
  id: idString.optional(),
  title: shortString.optional(),
  goal: shortString.optional(),
  startLevel: z.enum(['beginner', 'intermediate', 'advanced', 'unspecified']).optional(),
  targetCompetency: shortString.optional(),
  // The persisted path id (enables real completion persistence).
  pathId: idString.optional(),
  nodes: z.array(learningNodeSchema).min(1).max(RESPONSE_LIMITS.maxLearningNodes),
  resources: z.array(learningResourceSchema).max(RESPONSE_LIMITS.maxLearningResources).default([]),
  // Non-fatal validation issues from the curriculum engine (gaps, missing
  // assessments) — surfaced honestly rather than hidden.
  issues: z.array(shortString).max(40).default([]),
});

const actionSchema = z.object({
  id: idString,
  label: shortString,
  description: shortString.optional(),
  icon: shortString.optional(),
  tone: z.enum(['neutral', 'info', 'success', 'warning', 'danger']).default('neutral'),
  // The follow-up prompt this action sends. It re-enters the EXISTING agent loop
  // and is exactly as capable as the user typing it — no privileged backend call.
  prompt: boundedString,
});

// Proposed next steps. These are PROPOSALS, not executions: clicking one sends
// its `prompt` as a new user turn (and the card says so), so the model can never
// trigger an unauthorized backend action through this block.
const actionGroupBlock = z.object({
  type: z.literal('action_group'),
  id: idString.optional(),
  title: shortString.optional(),
  description: boundedString.optional(),
  actions: z.array(actionSchema).min(1).max(RESPONSE_LIMITS.maxActions),
});

const artifactRefSchema = z.object({
  artifactId: idString.optional(),
  name: shortString,
  description: boundedString.optional(),
  category: shortString.optional(),
  mimeType: shortString.optional(),
  sizeBytes: z.number().int().nonnegative().optional(),
  version: z.number().int().positive().optional(),
  url: httpUrl.optional(),
});

// A reference to a real record in the existing Artifact Center. It links to the
// artifact's own download route; it never inlines large content into the message.
const artifactBlock = z.object({
  type: z.literal('artifact'),
  id: idString.optional(),
  title: shortString.optional(),
  artifacts: z.array(artifactRefSchema).min(1).max(RESPONSE_LIMITS.maxArtifacts),
});

// ── Media: inline image gallery ────────────────────────────────────────────────
// One image in the gallery. `url` is the direct, renderable image URL and MUST
// be http(s) (the `httpUrl` refinement rejects `javascript:`/`data:` so an image
// source can never become an XSS vector). `sourceUrl` is the attribution link.
const galleryImageSchema = z.object({
  url: httpUrl,
  thumbnailUrl: httpUrl.optional(),
  alt: shortString.optional(),
  title: shortString.optional(),
  caption: shortString.optional(),
  sourceUrl: httpUrl.optional(),
  sourceDomain: shortString.optional(),
  width: z.number().int().positive().optional(),
  height: z.number().int().positive().optional(),
  attribution: shortString.optional(),
});

const galleryBlock = z.object({
  type: z.literal('gallery'),
  id: idString.optional(),
  title: shortString.optional(),
  caption: shortString.optional(),
  source: shortString.optional(),
  columns: z.number().int().min(1).max(4).optional(),
  images: z.array(galleryImageSchema).min(1).max(RESPONSE_LIMITS.maxImages),
});

// ── Website-style visual blocks ────────────────────────────────────────────────
// A family of presentational "figure" blocks that give an answer the rhythm of a
// data website: a hero number, meters, a comparison matrix, a ranked bar list, a
// badge cluster and a slide carousel. All are pure validation + rendering — no
// field triggers code, a tool call, or a network request.

// A large, emphasized headline number (with optional delta) — the "hero" statistic
// of an answer. Distinct from `metric_grid` (a compact KPI card grid): a stat hero
// is deliberately one to four oversized numbers with supporting context.
const statHeroStatSchema = z.object({
  label: shortString,
  value: numberOrNumericString,
  unit: shortString.optional(),
  prefix: shortString.optional(),
  delta: numberOrNumericString.optional(),
  deltaTone: z.enum(['up', 'down', 'flat', 'neutral']).optional(),
  icon: shortString.optional(),
  hint: shortString.optional(),
  unavailable: z.boolean().optional(),
});

const statHeroBlock = z.object({
  type: z.literal('stat_hero'),
  id: idString.optional(),
  title: shortString.optional(),
  source: shortString.optional(),
  asOf: shortString.optional(),
  stats: z.array(statHeroStatSchema).min(1).max(RESPONSE_LIMITS.maxStats),
});

// A progress meter / gauge: a value rendered against a `max` as a filled bar.
// The renderer clamps the fill to [0, max] rather than inventing a value; the
// numeric value is always displayed, so a clipped bar never lies.
const gaugeSchema = z.object({
  label: shortString,
  value: z.number().finite(),
  max: z.number().finite().positive().default(100),
  unit: shortString.optional(),
  tone: z.enum(['neutral', 'info', 'success', 'warning', 'danger']).default('neutral'),
  hint: shortString.optional(),
});

const gaugeBlock = z.object({
  type: z.literal('gauge'),
  id: idString.optional(),
  title: shortString.optional(),
  description: shortString.optional(),
  gauges: z.array(gaugeSchema).min(1).max(RESPONSE_LIMITS.maxGauges),
});

// A comparison matrix (pricing-table shape): options become columns, attributes
// become rows. A cell is a check/cross when boolean, otherwise its text value.
const comparisonColumnSchema = z.object({
  label: shortString,
  highlight: z.boolean().optional(),
});

const comparisonCellSchema = z.union([
  z.boolean(),
  z.string().max(500),
  z.number().finite(),
  z.null(),
]);

const comparisonRowSchema = z.object({
  label: shortString,
  values: z.array(comparisonCellSchema).max(RESPONSE_LIMITS.maxCompareColumns),
  hint: shortString.optional(),
});

const comparisonGridBlock = z.object({
  type: z.literal('comparison_grid'),
  id: idString.optional(),
  title: shortString.optional(),
  caption: shortString.optional(),
  columns: z.array(comparisonColumnSchema).min(1).max(RESPONSE_LIMITS.maxCompareColumns),
  rows: z.array(comparisonRowSchema).min(1).max(RESPONSE_LIMITS.maxCompareRows),
});

// A leaderboard / ranked bar list. Bars are scaled to the largest absolute value
// in the list (never to a fabricated ceiling). Order is the producer's rank order.
const rankedItemSchema = z.object({
  label: shortString,
  value: z.number().finite(),
  display: shortString.optional(),
  unit: shortString.optional(),
  icon: shortString.optional(),
  tone: z.enum(['neutral', 'info', 'success', 'warning', 'danger']).default('neutral'),
});

const rankedListBlock = z.object({
  type: z.literal('ranked_list'),
  id: idString.optional(),
  title: shortString.optional(),
  description: shortString.optional(),
  valueLabel: shortString.optional(),
  items: z.array(rankedItemSchema).min(1).max(RESPONSE_LIMITS.maxRankedItems),
});

// A cluster of tag/pill badges — sectors, themes, labels. Tone maps to the shared
// tone palette; an optional icon is resolved against the semantic allowlist.
const badgeSchema = z.object({
  label: shortString,
  tone: z.enum(['neutral', 'info', 'success', 'warning', 'danger']).default('neutral'),
  icon: shortString.optional(),
});

const badgeRowBlock = z.object({
  type: z.literal('badge_row'),
  id: idString.optional(),
  title: shortString.optional(),
  description: shortString.optional(),
  badges: z.array(badgeSchema).min(1).max(RESPONSE_LIMITS.maxBadges),
});

// A slide carousel: each slide is a labelled panel of nested blocks (validated
// recursively by the parser, like `tabs`/`report`). One slide is visible at a
// time with prev/next + dot navigation; a single-slide carousel renders plain.
const carouselSlideSchema = z.object({
  label: shortString.optional(),
  title: shortString.optional(),
  blocks: z.array(z.unknown()),
});

const carouselBlock = z.object({
  type: z.literal('carousel'),
  id: idString.optional(),
  title: shortString.optional(),
  description: shortString.optional(),
  slides: z.array(carouselSlideSchema).min(1).max(RESPONSE_LIMITS.maxSlides),
});

/**
 * The discriminated union of every registered block type. Unknown `type` values
 * do NOT parse; the parser catches that and emits an `unknown` diagnostic block.
 */
export const ResponseBlockSchema = z.discriminatedUnion('type', [
  markdownBlock,
  headingBlock,
  calloutBlock,
  keyValueBlock,
  detailsBlock,
  metricGridBlock,
  dataTableBlock,
  chartBlock,
  diagramBlock,
  timelineBlock,
  citationsBlock,
  tabsBlock,
  financialChartBlock,
  mermaidBlock,
  controlsBlock,
  stepperBlock,
  infographicBlock,
  workflowBlock,
  reportBlock,
  nodeGraphBlock,
  actionGroupBlock,
  artifactBlock,
  galleryBlock,
  learningMapBlock,
  statHeroBlock,
  gaugeBlock,
  comparisonGridBlock,
  rankedListBlock,
  badgeRowBlock,
  carouselBlock,
]);

/**
 * `metadata` is free-form producer bookkeeping. It is bounded here (key count +
 * serialized size) so it can never become an unbounded payload. A metadata value
 * that exceeds the bound is dropped via `.catch`, NOT allowed to fail the whole
 * envelope — losing bookkeeping must never cost the user their answer.
 */
const metadataSchema = z
  .record(z.string(), z.unknown())
  .refine((value) => Object.keys(value).length <= RESPONSE_LIMITS.maxMetadataKeys, {
    message: `metadata has too many keys (max ${RESPONSE_LIMITS.maxMetadataKeys})`,
  })
  .refine(
    (value) => {
      try {
        return JSON.stringify(value).length <= RESPONSE_LIMITS.maxStringLength;
      } catch {
        return false;
      }
    },
    { message: `metadata is too large (max ${RESPONSE_LIMITS.maxStringLength} chars)` },
  );

export const ResponseEnvelopeSchema = z.object({
  schemaVersion: z.string().max(20).optional(),
  responseId: idString.optional(),
  responseType: shortString.optional(),
  title: shortString.optional(),
  summary: boundedString.optional(),
  blocks: z.array(z.unknown()).max(RESPONSE_LIMITS.maxBlocks),
  metadata: metadataSchema.optional().catch(undefined),
});

export type ResponseBlock = z.infer<typeof ResponseBlockSchema>;
export type ValidatedBlock = ResponseBlock | UnknownBlock;
export type ResponseEnvelope = z.infer<typeof ResponseEnvelopeSchema>;
export type Metric = z.infer<typeof metricSchema>;
export type TableColumn = z.infer<typeof tableColumnSchema>;
export type TableCell = z.infer<typeof tableCellSchema>;
export type ChartSeries = z.infer<typeof chartSeriesSchema>;
export type ChartBlock = z.infer<typeof chartBlock>;
export type DiagramBlock = z.infer<typeof diagramBlock>;
export type DiagramNode = z.infer<typeof diagramNodeSchema>;
export type DiagramEdge = z.infer<typeof diagramEdgeSchema>;
export type CitationSource = z.infer<typeof citationSourceSchema>;
export type FinancialChartBlock = z.infer<typeof financialChartBlock>;
export type MermaidBlock = z.infer<typeof mermaidBlock>;
export type ControlsBlock = z.infer<typeof controlsBlock>;
export type Control = z.infer<typeof controlSchema>;
export type StepperBlock = z.infer<typeof stepperBlock>;
export type InfographicBlock = z.infer<typeof infographicBlock>;
export type InfographicCard = z.infer<typeof infographicCardSchema>;
export type WorkflowBlock = z.infer<typeof workflowBlock>;
export type WorkflowStage = z.infer<typeof workflowStageSchema>;
export type ReportBlock = z.infer<typeof reportBlock>;
export type ReportSection = z.infer<typeof reportSectionSchema>;
export type NodeGraphBlock = z.infer<typeof nodeGraphBlock>;
export type NodeGraphNode = z.infer<typeof nodeGraphNodeSchema>;
export type LearningMapBlock = z.infer<typeof learningMapBlock>;
export type LearningNode = z.infer<typeof learningNodeSchema>;
export type LearningResourceRef = z.infer<typeof learningResourceSchema>;
export type ActionGroupBlock = z.infer<typeof actionGroupBlock>;
export type ResponseAction = z.infer<typeof actionSchema>;
export type ArtifactBlock = z.infer<typeof artifactBlock>;
export type ArtifactRef = z.infer<typeof artifactRefSchema>;
export type GalleryBlock = z.infer<typeof galleryBlock>;
export type GalleryImage = z.infer<typeof galleryImageSchema>;
export type StatHeroBlock = z.infer<typeof statHeroBlock>;
export type StatHeroStat = z.infer<typeof statHeroStatSchema>;
export type GaugeBlock = z.infer<typeof gaugeBlock>;
export type Gauge = z.infer<typeof gaugeSchema>;
export type ComparisonGridBlock = z.infer<typeof comparisonGridBlock>;
export type ComparisonColumn = z.infer<typeof comparisonColumnSchema>;
export type ComparisonRow = z.infer<typeof comparisonRowSchema>;
export type RankedListBlock = z.infer<typeof rankedListBlock>;
export type RankedItem = z.infer<typeof rankedItemSchema>;
export type BadgeRowBlock = z.infer<typeof badgeRowBlock>;
export type Badge = z.infer<typeof badgeSchema>;
export type CarouselBlock = z.infer<typeof carouselBlock>;
export type CarouselSlide = z.infer<typeof carouselSlideSchema>;

/** A block whose type is not registered. Rendered as a readable diagnostic —
 *  never executed, never discarded silently. */
export interface UnknownBlock {
  type: 'unknown';
  declaredType: string;
  raw: unknown;
}

export type DiagnosticSeverity = 'error' | 'warning';

export interface ResponseDiagnostic {
  severity: DiagnosticSeverity;
  code: string;
  message: string;
  /** Index of the offending block in the envelope, when applicable. */
  blockIndex?: number;
  declaredType?: string;
}

export interface ParsedResponse {
  schemaVersion: string;
  responseId?: string;
  responseType?: string;
  title?: string;
  summary?: string;
  blocks: ValidatedBlock[];
  diagnostics: ResponseDiagnostic[];
  metadata?: Record<string, unknown>;
}

function asUnknownBlock(raw: unknown, declaredType: string): UnknownBlock {
  return { type: 'unknown', declaredType, raw };
}

function declaredTypeOf(raw: unknown): string {
  if (raw && typeof raw === 'object' && 'type' in raw && typeof (raw as { type: unknown }).type === 'string') {
    return (raw as { type: string }).type;
  }
  return '(missing)';
}

/**
 * Validate one block. Returns the validated block or an `unknown` fallback plus
 * a diagnostic. Never throws.
 */
export function validateBlock(raw: unknown): { block: ValidatedBlock; diagnostic?: ResponseDiagnostic } {
  const candidate = normalizeBlockAlias(raw);
  const result = ResponseBlockSchema.safeParse(candidate);
  if (!result.success) {
    const declaredType = declaredTypeOf(raw);
    const first = result.error.issues[0];
    return {
      block: asUnknownBlock(candidate, declaredType),
      diagnostic: {
        severity: 'error',
        code: 'BLOCK_INVALID',
        message: first ? `${first.path.join('.') || '(root)'}: ${first.message}` : 'Block failed validation',
        declaredType,
      },
    };
  }
  return { block: result.data };
}

/**
 * Normalize a schema version string. Missing → current. A newer major version is
 * accepted best-effort with a warning so a forward-compatible producer still
 * renders; an older minor is treated as v1.
 */
function normalizeVersion(raw: string | undefined): { version: string; diagnostic?: ResponseDiagnostic } {
  if (!raw) return { version: RESPONSE_SCHEMA_VERSION };
  const major = Number.parseInt(raw.split('.')[0] ?? '', 10);
  if (!Number.isFinite(major)) {
    return {
      version: RESPONSE_SCHEMA_VERSION,
      diagnostic: {
        severity: 'warning',
        code: 'SCHEMA_VERSION_UNPARSABLE',
        message: `Unrecognized schemaVersion "${raw}"; rendering as ${RESPONSE_SCHEMA_VERSION}.`,
      },
    };
  }
  if (major > Number.parseInt(RESPONSE_SCHEMA_VERSION.split('.')[0], 10)) {
    return {
      version: raw,
      diagnostic: {
        severity: 'warning',
        code: 'SCHEMA_VERSION_FUTURE',
        message: `Response uses schemaVersion ${raw}, newer than supported ${RESPONSE_SCHEMA_VERSION}; unsupported blocks are shown as diagnostics.`,
      },
    };
  }
  return { version: raw };
}

/**
 * Parse and validate a decoded JSON value into a `ParsedResponse`. This is the
 * single entry point used by the renderer. It is total: malformed input yields
 * a diagnostic-backed empty response rather than a throw.
 */
export function parseResponsePayload(input: unknown): ParsedResponse {
  const diagnostics: ResponseDiagnostic[] = [];
  const envelopeResult = ResponseEnvelopeSchema.safeParse(input);
  if (!envelopeResult.success) {
    const first = envelopeResult.error.issues[0];
    return {
      schemaVersion: RESPONSE_SCHEMA_VERSION,
      blocks: [],
      diagnostics: [
        {
          severity: 'error',
          code: 'ENVELOPE_INVALID',
          message: first ? `${first.path.join('.') || '(root)'}: ${first.message}` : 'Invalid response envelope',
        },
      ],
    };
  }

  const envelope = envelopeResult.data;
  const version = normalizeVersion(envelope.schemaVersion);
  if (version.diagnostic) diagnostics.push(version.diagnostic);

  const blocks: ValidatedBlock[] = [];
  envelope.blocks.forEach((raw, index) => {
    const { block, diagnostic } = validateBlock(raw);
    if (diagnostic) diagnostics.push({ ...diagnostic, blockIndex: index });
    if (block.type === 'tabs') {
      const nested = block as z.infer<typeof tabsBlock>;
      nested.tabs = nested.tabs.map((tab) => ({
        ...tab,
        blocks: parseNestedBlocks(tab.blocks, 1, diagnostics),
      }));
    }
    if (block.type === 'report') {
      block.sections = block.sections.map((section) => ({
        ...section,
        blocks: section.blocks ? parseNestedBlocks(section.blocks, 1, diagnostics) : undefined,
      }));
    }
    if (block.type === 'carousel') {
      const nested = block as z.infer<typeof carouselBlock>;
      nested.slides = nested.slides.map((slide) => ({
        ...slide,
        blocks: parseNestedBlocks(slide.blocks, 1, diagnostics),
      }));
    }
    blocks.push(block);
  });

  if (envelope.blocks.length === 0) {
    diagnostics.push({
      severity: 'warning',
      code: 'NO_BLOCKS',
      message: 'Response envelope contained no blocks.',
    });
  }

  return {
    schemaVersion: version.version,
    responseId: envelope.responseId,
    responseType: envelope.responseType,
    title: envelope.title,
    summary: envelope.summary,
    blocks,
    diagnostics,
    metadata: envelope.metadata,
  };
}

/** Recursively validate a nested block list (used by `tabs`). Depth-bounded. */
export function parseNestedBlocks(
  rawBlocks: unknown[],
  depth: number,
  out: ResponseDiagnostic[],
): ValidatedBlock[] {
  if (depth > RESPONSE_LIMITS.maxNestedDepth) {
    out.push({
      severity: 'error',
      code: 'NESTING_TOO_DEEP',
      message: `Nested blocks exceed the maximum depth of ${RESPONSE_LIMITS.maxNestedDepth}.`,
    });
    return [];
  }
  return rawBlocks.slice(0, RESPONSE_LIMITS.maxBlocks).map((raw, index) => {
    const { block, diagnostic } = validateBlock(raw);
    if (diagnostic) out.push({ ...diagnostic, blockIndex: index });
    if (block.type === 'tabs') {
      // Re-validate nested tabs children with an incremented depth.
      const nested = block as z.infer<typeof tabsBlock>;
      nested.tabs = nested.tabs.map((tab) => ({
        ...tab,
        blocks: parseNestedBlocks(tab.blocks, depth + 1, out),
      }));
    }
    if (block.type === 'report') {
      block.sections = block.sections.map((section) => ({
        ...section,
        blocks: section.blocks ? parseNestedBlocks(section.blocks, depth + 1, out) : undefined,
      }));
    }
    if (block.type === 'carousel') {
      const nested = block as z.infer<typeof carouselBlock>;
      nested.slides = nested.slides.map((slide) => ({
        ...slide,
        blocks: parseNestedBlocks(slide.blocks, depth + 1, out),
      }));
    }
    return block;
  });
}
