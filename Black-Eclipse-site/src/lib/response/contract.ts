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
  maxStringLength: 20000,
} as const;

const boundedString = z.string().max(RESPONSE_LIMITS.maxStringLength);
const shortString = z.string().max(500);
const idString = z.string().min(1).max(120);

const numberOrNumericString = z.union([z.number().finite(), z.string().max(120)]);

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
  url: z.string().url().optional(),
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
]);

export const ResponseEnvelopeSchema = z.object({
  schemaVersion: z.string().max(20).optional(),
  responseId: idString.optional(),
  responseType: shortString.optional(),
  title: shortString.optional(),
  summary: boundedString.optional(),
  blocks: z.array(z.unknown()).max(RESPONSE_LIMITS.maxBlocks),
  metadata: z.record(z.string(), z.unknown()).optional(),
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
  const result = ResponseBlockSchema.safeParse(raw);
  if (!result.success) {
    const declaredType = declaredTypeOf(raw);
    const first = result.error.issues[0];
    return {
      block: asUnknownBlock(raw, declaredType),
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
    return block;
  });
}
