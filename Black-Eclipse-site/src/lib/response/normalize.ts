// ── Eclipse response block normalization ──────────────────────────────────────
//
// Pure, total rewrite of a raw producer block into the canonical contract shape
// BEFORE validation: documented `type` aliases (`text`, `table`, `source_list`,
// …), field-level synonyms (`content`/`text`/`body`→`markdown`, `variant`→`tone`,
// `items`→`sources`, string table columns / positional rows, interval aliases)
// and icon values (`TrendUp`/`trend_up`/emoji → the canonical `trend-up` key).
// A non-object block is returned unchanged; nothing here throws, executes or
// reads the network.

import { canonicalIconKey } from './icon-vocabulary';

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
  // Flow vocabulary. A producer reaching for the plain word "process" means the
  // ordered icon-stage block; "pipeline"/"process_flow" mean the branching card
  // flow; a raw "flow_graph" is a node/edge graph. Routing them to a NATIVE block
  // keeps flows off Mermaid (which is reserved for sequence/ER/class/gantt).
  process: 'workflow',
  process_flow: 'flow',
  pipeline: 'flow',
  flow_graph: 'diagram',
  // An interactive local calculator / what-if explorer.
  calculator: 'simulation',
  simulator: 'simulation',
  // A 3D/isometric mechanism illustration (the Anatomy-derived engine).
  isometric: 'anatomy',
  mechanism: 'anatomy',
  anatomy_diagram: 'anatomy',
  // The true-3D scene block (orbitable model, GLB export).
  model_3d: 'model3d',
  '3d': 'model3d',
  three_d: 'model3d',
  scene3d: 'model3d',
  // A self-contained interactive app (HTML/CSS/JS/SVG) in a sandbox.
  interactive_app: 'interactive',
  html_app: 'interactive',
  mini_app: 'interactive',
  widget: 'interactive',
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

// The renderer's `tone` is a five-value STATUS enum on every tone-bearing block
// EXCEPT `callout` (which also permits `note`). A producer that correctly uses
// the semantic vocabulary for `icon` (`trend-up`, `positive`, `bearish`, …)
// reaches for the same words for `tone` — but they are invalid there, and because
// `tone` carries a schema default, a PRESENT-but-invalid value DEFEATS that
// default and hard-fails the whole block (the exact bug that dropped the gold
// `flow`). Map the known semantic synonyms onto the status enum, and DROP an
// unrecognized value so the schema default applies: a wrong tone costs the
// accent colour, never the block.
const STATUS_TONES = new Set(['neutral', 'info', 'success', 'warning', 'danger']);
const TONE_ALIASES: Record<string, string> = {
  positive: 'success', good: 'success', up: 'success', rise: 'success', rising: 'success',
  'trend-up': 'success', bullish: 'success', gain: 'success', gains: 'success', green: 'success',
  ok: 'success', done: 'success', complete: 'success', completed: 'success', valid: 'success',
  confirmed: 'success', active: 'success',
  negative: 'danger', bad: 'danger', down: 'danger', fall: 'danger', falling: 'danger',
  'trend-down': 'danger', bearish: 'danger', loss: 'danger', losses: 'danger', red: 'danger',
  error: 'danger', critical: 'danger', fail: 'danger', failed: 'danger',
  warn: 'warning', caution: 'warning', alert: 'warning', risk: 'warning',
  information: 'info', normal: 'neutral', flat: 'neutral', side: 'neutral',
  'trend-flat': 'neutral', pending: 'neutral',
};

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

// The same synonyms for a plain `chart` block: "candlestick" is a chart type
// there too, so a producer that says "candle" must not be rejected.
const CHART_TYPE_ALIASES: Record<string, string> = {
  candle: 'candlestick',
  candles: 'candlestick',
  candlesticks: 'candlestick',
  ohlc_bar: 'candlestick',
  ohlc_bars: 'candlestick',
  price_bar: 'candlestick',
  price_bars: 'candlestick',
  // A regression is a real kind: the points, the least-squares line and its
  // R-squared. A producer that says "linear regression" must not be refused.
  regression: 'regression',
  linear_regression: 'regression',
  linear_regressions: 'regression',
  'linear regression': 'regression',
  'linear-regression': 'regression',
  regress: 'regression',
  regression_line: 'regression',
  trend: 'regression',
  trendline: 'regression',
  trend_line: 'regression',
  ols: 'regression',
  fit: 'regression',
  best_fit: 'regression',
  scatter_fit: 'regression',
};

// A MARK primitive has the same synonyms as a chart kind (a candle mark is a
// candlestick), plus the 3D spellings a producer reaches for. An unknown mark
// primitive is NOT aliased away here: validation reports it by name.
const CHART_MARK_TYPE_ALIASES: Record<string, string> = {
  candles: 'candlestick',
  candle: 'candlestick',
  ohlc: 'candlestick',
  bars: 'bar',
  columns: 'bar',
  points: 'scatter',
  boxplot: 'box',
  violinplot: 'violin',
  linear: 'regression',
  linear_regression: 'regression',
  'linear regression': 'regression',
  trend: 'regression',
  trendline: 'regression',
  trend_line: 'regression',
  ols: 'regression',
  fit: 'regression',
  best_fit: 'regression',
  scatter_fit: 'regression',
  // The 3D family, under the spellings a person writes.
  scatter_3d: 'scatter3d',
  'scatter 3d': 'scatter3d',
  scatter3_d: 'scatter3d',
  points3d: 'scatter3d',
  '3d_scatter': 'scatter3d',
  surface3d: 'surface',
  surface_3d: 'surface',
  'surface 3d': 'surface',
  '3d_surface': 'surface',
  grid3d: 'surface',
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

/** The status enum value for a producer `tone`, or `undefined` to drop it. */
function normalizeToneValue(raw: unknown, callout: boolean): string | undefined {
  if (typeof raw !== 'string') return undefined;
  const lower = raw.trim().toLowerCase();
  if (!lower) return undefined;
  const allowed = callout ? CALLOUT_TONES : STATUS_TONES;
  if (allowed.has(lower)) return lower;
  const mapped = TONE_ALIASES[lower];
  return mapped && allowed.has(mapped) ? mapped : undefined;
}

/**
 * Rewrite every `tone` in a block to the status enum (or drop it, letting the
 * schema default apply). Recurses into nested arrays/objects so `steps[].tone`,
 * `paths[].tone`, `nodes[].tone`, `edges[].tone` are all covered; a nested object
 * carrying its own `type` selects its own vocabulary (so a `callout` inside a
 * `tabs` tab keeps its `note` tone).
 */
function normalizeTonesDeep(node: unknown, callout: boolean): unknown {
  if (Array.isArray(node)) return node.map((n) => normalizeTonesDeep(n, callout));
  if (!isRecord(node)) return node;
  const scoped = typeof node.type === 'string' ? node.type === 'callout' : callout;
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(node)) {
    if (key === 'tone') {
      const tone = normalizeToneValue(value, scoped);
      if (tone !== undefined) out[key] = tone;
      continue;
    }
    out[key] = normalizeTonesDeep(value, scoped);
  }
  return out;
}

/** `sources` entries may spell the label `name` or `label`; the contract wants `title`. */
function normalizeCitationSources(value: unknown): unknown {
  if (!Array.isArray(value)) return value;
  return value.map((item) => {
    if (!isRecord(item)) return item;
    if (item.title !== undefined) return item;
    const title = item.name ?? item.label;
    return typeof title === 'string' ? { ...item, title } : item;
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
/** The field names a producer uses for the x of a point. */
const X_FIELD_NAMES = ['x', 'i', 'index', 'n', 't', 'time', 'date', 'day', 'period', 'timestamp'];
/** The field names a producer uses for the y of a point. */
const Y_FIELD_NAMES = ['y', 'close', 'value', 'v', 'price', 'amount', 'level', 'result', 'score'];

/** A number a point can carry - a numeric string counts (a model may quote it). */
function asNumber(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

/**
 * One point written as an OBJECT: `{i: 1, close: 188.7}`.
 *
 * A named field that reads like an x is the x; a named field that reads like
 * a y is the y; when the names say nothing, the first two numeric fields are
 * the point in the order they were written. A point with no numbers at all
 * is dropped - one odd point never costs the whole chart.
 */
function pointFromObject(point: Record<string, unknown>): number | [number, number] | null {
  const keys = Object.keys(point);
  let x: number | null = null;
  let y: number | null = null;

  for (const key of keys) {
    if (x !== null) break;
    if (!X_FIELD_NAMES.includes(key.toLowerCase())) continue;
    x = asNumber(point[key]);
  }
  for (const key of keys) {
    if (y !== null) break;
    if (!Y_FIELD_NAMES.includes(key.toLowerCase())) continue;
    const value = asNumber(point[key]);
    if (value === null) continue;
    // A field that is BOTH (x) and a y-name is the y only when it is not
    // already the x.
    if (x !== null && key.toLowerCase() === 'x') continue;
    y = value;
  }
  if (x === null || y === null) {
    // No named fields said what is what: take the first two numbers, in order.
    const numbers: number[] = [];
    for (const key of keys) {
      const value = asNumber(point[key]);
      if (value !== null) numbers.push(value);
      if (numbers.length === 2) break;
    }
    if (numbers.length < 2) {
      // One number on its own is a labelled scalar.
      return numbers.length === 1 ? numbers[0] : null;
    }
    x = numbers[0];
    y = numbers[1];
  }
  return [x as number, y as number];
}

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
    // A point written with OTHER names (`{i, close}`) is still a point.
    return pointFromObject(p);
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

// Array fields whose items carry the optional semantic `icon` key, per block
// type (see `icons.ts`). One place to extend when a new icon-bearing block lands.
const ICON_ITEM_FIELDS: Record<string, string> = {
  infographic: 'cards',
  workflow: 'stages',
  action_group: 'actions',
  stat_hero: 'stats',
  ranked_list: 'items',
  badge_row: 'badges',
};

/**
 * Canonicalize each item's `icon` (aliases, case/separator spellings, common
 * emoji → the allowlisted key). A NON-STRING icon is dropped so the block still
 * validates and renders — a misspelled icon may cost the glyph, never the card.
 */
function normalizeIconItems(value: unknown): unknown {
  if (!Array.isArray(value)) return value;
  return value.map((item) => {
    if (!isRecord(item) || item.icon === undefined) return item;
    const key = canonicalIconKey(item.icon);
    if (key === undefined) {
      const next: Record<string, unknown> = { ...item };
      delete next.icon;
      return next;
    }
    return key === item.icon ? item : { ...item, icon: key };
  });
}

/** Normalize the field-level synonyms of an already-canonically-typed block. */
function normalizeBlockFields(raw: Record<string, unknown>): Record<string, unknown> {
  const type = typeof raw.type === 'string' ? raw.type : '';
  const out: Record<string, unknown> = { ...raw };

  if (PROSE_FIELD_TYPES.has(type) && out.markdown === undefined) {
    // Producers name the body `content`, `text` (the same word as the
    // `text`→`markdown` type alias) or `body`. None is the canonical field; all
    // three are accepted so the block is not lost. `heading` legitimately owns a
    // `text` field, so this rewrite is scoped to the prose body types only.
    if (out.content !== undefined) out.markdown = out.content;
    else if (typeof out.text === 'string') out.markdown = out.text;
    else if (typeof out.body === 'string') out.markdown = out.body;
  }

  if (type === 'mermaid' && out.diagram === undefined) {
    if (out.content !== undefined) out.diagram = out.content;
    else if (out.code !== undefined) out.diagram = out.code;
    else if (out.source !== undefined) out.diagram = out.source;
    else if (out.definition !== undefined) out.diagram = out.definition;
    else if (typeof out.body === 'string') out.diagram = out.body;
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
    if (out.chartType === undefined) {
      const ct = out.chart_type ?? out.charttype;
      if (typeof ct === 'string') out.chartType = ct;
    }
    if (typeof out.chartType === 'string') {
      const mapped = CHART_TYPE_ALIASES[out.chartType.trim().toLowerCase()];
      if (mapped) out.chartType = mapped;
    }
    if (out.categories === undefined && out.labels !== undefined) out.categories = out.labels;
    // Chart.js-style producers spell the series array `datasets`; the contract
    // wants `series`. Without this the block fails with "series: expected array".
    if (out.series === undefined && Array.isArray(out.datasets)) out.series = out.datasets;

    // ── Candle rows ────────────────────────────────────────────────────────
    // A model writes a candle the way a person does: `[date, o, h, l, c]` or
    // `{date, open, high, low, close}`. The contract takes the four numbers and
    // the date belongs on the category axis. Without this pass a dated tuple is
    // an invalid point (the whole block degrades to prose) and an object row is
    // flattened to [open, high] (a candlestick with no candles).
    const candleCategories: string[] = [];
    const labelOf = (point: Record<string, unknown>): string | null => {
      for (const key of ['date', 'time', 'label', 'period', 'day', 'timestamp']) {
        const value = point[key];
        if (typeof value === 'string' && value) return value;
        if (typeof value === 'number' && Number.isFinite(value)) return String(value);
      }
      return null;
    };
    const asCandle = (point: unknown): number[] | null => {
      if (Array.isArray(point) && point.length >= 5 && typeof point[0] !== 'number') {
        const ohlc = point.slice(1, 5);
        if (ohlc.every((v) => typeof v === 'number' && Number.isFinite(v))) {
          candleCategories.push(String(point[0]));
          return ohlc as number[];
        }
      }
      if (isRecord(point)) {
        const { open, high, low, close } = point;
        if ([open, high, low, close].every((v) => typeof v === 'number' && Number.isFinite(v))) {
          const label = labelOf(point);
          if (label !== null) candleCategories.push(label);
          return [open as number, high as number, low as number, close as number];
        }
      }
      return null;
    };
    if (Array.isArray(out.series)) {
      out.series = out.series.map((entry) => {
        if (!isRecord(entry) || !Array.isArray(entry.data)) return entry;
        let changed = false;
        const data = entry.data.map((point) => {
          const candle = asCandle(point);
          if (candle) {
            changed = true;
            return candle;
          }
          return point;
        });
        return changed ? { ...entry, data } : entry;
      });
    }
    if ((out.categories === undefined || (Array.isArray(out.categories) && out.categories.length === 0))
      && candleCategories.length > 0) {
      out.categories = candleCategories;
    }
    // ROW style: a producer may spell the data as labelled rows —
    // `data: [{label, values: [o,h,l,c]}]` (what a model writes for a candle
    // chart). The contract wants `categories` + `series[].data`; without this
    // conversion the whole block is rejected and degrades to prose.
    if (out.series === undefined && Array.isArray(out.data) && out.data.every(isRecord)) {
      const rows = out.data as Array<Record<string, unknown>>;
      const labelled = rows.every((r) => r.label !== undefined || r.values !== undefined);
      if (labelled) {
        const categories = rows.map((r) => (r.label === undefined ? '' : String(r.label)));
        const values = rows.map((r) => (Array.isArray(r.values) ? r.values : []));
        out.categories = categories;
        out.series = [
          {
            name: typeof out.title === 'string' && out.title ? out.title : 'value',
            data: values.map((v) => (v.length === 1 ? v[0] : v)),
          },
        ];
        delete out.data;
      }
    }
    // The MARKS carry their own data, and a mark writes its points the way a
    // person does: `[1, 258.45]` or `{i: 1, close: 258.45}`. Both are
    // normalised here, so a mark is never refused over its data format.
    if (Array.isArray(out.panels)) {
      out.panels = (out.panels as unknown[]).map((panel) => {
        if (!isRecord(panel) || !Array.isArray(panel.marks)) return panel;
        const next: Record<string, unknown> = { ...panel };
        next.marks = (panel.marks as unknown[]).map((mark) => {
          if (!isRecord(mark)) return mark;
          const m: Record<string, unknown> = { ...mark };
          // A mark's primitive is `type`; a producer may spell it `kind` or
          // `markType`. Recover the mark rather than losing it to the fallback.
          if (m.type === undefined) {
            const primitive = m.kind ?? m.markType ?? m.mark_type;
            if (typeof primitive === 'string') m.type = primitive;
          }
          if (typeof m.type === 'string') {
            const mapped = CHART_MARK_TYPE_ALIASES[m.type.trim().toLowerCase()];
            if (mapped) m.type = mapped;
          }
          // A surface's grid may arrive as a 2D `z` (what a person writes)
          // instead of `matrix`. Both mean the same grid.
          if (
            Array.isArray(m.z) &&
            m.z.length > 0 &&
            Array.isArray(m.z[0]) &&
            m.matrix === undefined
          ) {
            m.matrix = m.z;
            delete m.z;
          }
          if (m.y !== undefined) m.y = normalizeChartPoints(m.y);
          if (m.data !== undefined) m.data = normalizeChartPoints(m.data);
          return m;
        });
        return next;
      });
    }
    // The axis labels have two spellings in the wild.
    if (out.xLabel === undefined && typeof out.xAxisLabel === 'string') out.xLabel = out.xAxisLabel;
    if (out.yLabel === undefined && typeof out.yAxisLabel === 'string') out.yLabel = out.yAxisLabel;
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

  if (type === 'flow') {
    // The natural word for a flow's steps is `stages`; accept it. A step may be a
    // bare string (`steps: ["Fetch", "Validate"]`) — its only content is its
    // label, so the string is complete: coerce rather than fail the block.
    if (out.steps === undefined && Array.isArray(out.stages)) out.steps = out.stages;
    if (Array.isArray(out.steps)) {
      out.steps = out.steps.map((step) => {
        if (typeof step === 'string') return { label: step };
        if (!isRecord(step)) return step;
        const next: Record<string, unknown> = { ...step };
        if (next.icon !== undefined) {
          const key = canonicalIconKey(next.icon);
          if (key === undefined) delete next.icon;
          else next.icon = key;
        }
        // A step's outgoing options may be spelled `branches`/`options`.
        if (next.paths === undefined) {
          if (Array.isArray(next.branches)) next.paths = next.branches;
          else if (Array.isArray(next.options)) next.paths = next.options;
        }
        if (Array.isArray(next.paths)) next.paths = normalizeIconItems(next.paths);
        return next;
      });
    }
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
    // A badge may arrive as a bare string (`badges: ["AI", "Semis"]` — observed
    // in a live probe run). A badge's only content is its label, so the string
    // is COMPLETE information: coerce it rather than fail the block.
    if (Array.isArray(out.badges)) {
      out.badges = out.badges.map((b) => (typeof b === 'string' ? { label: b } : b));
    }
  }

  if (type === 'carousel' && out.slides === undefined) {
    const alt = out.items ?? out.tabs;
    if (alt !== undefined) out.slides = alt;
  }

  // Icon-bearing item arrays: canonicalize spellings/aliases and drop values
  // that are not strings at all, so an odd icon never invalidates the block.
  const iconField = ICON_ITEM_FIELDS[type];
  if (iconField && out[iconField] !== undefined) {
    out[iconField] = normalizeIconItems(out[iconField]);
  }

  // Tone is the last rewrite: every `tone` (including nested steps/paths/nodes/
  // edges, and an `anatomy` part/wire) is mapped to the status enum or dropped
  // so its schema default applies.
  return normalizeTonesDeep(out, type === 'callout') as Record<string, unknown>;
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
