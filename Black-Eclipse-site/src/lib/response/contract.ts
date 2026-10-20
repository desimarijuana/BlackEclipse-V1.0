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
import { anatomyBlock } from './blocks/anatomy';
import { model3dBlock } from './blocks/model3d';

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
  maxFlowSteps: 24,
  maxFlowPaths: 8,
  maxStats: 4,
  maxGauges: 24,
  maxCompareColumns: 6,
  maxCompareRows: 60,
  maxRankedItems: 50,
  maxBadges: 60,
  maxSlides: 12,
  maxSimulationInputs: 12,
  maxSimulationOutputs: 12,
  maxStateVars: 12,
  maxComputedVars: 12,
  maxLearningNodes: 120,
  maxLearningResources: 200,
  maxMetadataKeys: 40,
  maxStringLength: 20000,
} as const;

// Block normalization (type aliases + field synonyms) lives in ./normalize so
// this module stays within its size ratchet. Re-exported for existing callers.
import { normalizeBlockAlias } from './normalize';
export { normalizeBlockAlias };

const boundedString = z.string().max(RESPONSE_LIMITS.maxStringLength);
const shortString = z.string().max(500);
const idString = z.string().min(1).max(120);

const numberOrNumericString = z.union([z.number().finite(), z.string().max(120)]);

// ── Source-referenced figures ─────────────────────────────────────────────────
// A figure whose value is resolved from a REAL surface (this run's computed
// results, tool results, JDdS, artifact metadata) rather than typed by the model.
// Resolution happens before render (`lib/response/refs.ts`); an unresolvable
// reference renders UNAVAILABLE and NEVER falls back to the raw string, so a
// number on screen is always the source's value or an explicit miss.
export const FigureRefSchema = z.object({ $ref: z.string().min(1).max(300) });
export type FigureRef = z.infer<typeof FigureRefSchema>;

// A figure bound to an envelope-level COMPUTED value (see the envelope `computed`
// below). Resolved locally from the shared `state`, so a slider change updates
// every bound figure with 0 model calls.
export const ComputedRefSchema = z.object({ $computed: z.string().min(1).max(120) });
export type ComputedRef = z.infer<typeof ComputedRefSchema>;

const figureNumber = z.union([z.number().finite(), FigureRefSchema, ComputedRefSchema]);
const figureOrText = z.union([z.number().finite(), z.string().max(120), FigureRefSchema, ComputedRefSchema]);

// The provenance attached to a RESOLVED figure: reuses the existing vocabulary
// (computed provenance / JDdS freshness). Never produced by the model.
const figureProvenanceSchema = z.object({
  source: shortString.optional(),
  asOf: shortString.optional(),
  freshness: shortString.optional(),
  method: shortString.optional(),
  // The FORMULA the value was computed with. A derived number without its
  // formula is an assertion; with it, it is auditable.
  formula: shortString.optional(),
});
export type FigureProvenance = z.infer<typeof figureProvenanceSchema>;

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
  // A candlestick/OHLC point is [open, high, low, close] — the order people
  // read a candle in. The renderer maps it to ECharts' [open, close, low, high].
  z.tuple([
    z.number().finite(),
    z.number().finite(),
    z.number().finite(),
    z.number().finite(),
  ]),
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

// A key/value row is a display line, not a schema fragment: producers attach a
// short source/citation to the value, which routinely exceeds the 120-char
// generic numeric-string bound (observed 5x in live runs). Allow a wrapping line
// instead of failing the whole block.
const keyValueValue = z.union([z.number().finite(), z.string().max(500)]);

const keyValueBlock = z.object({
  type: z.literal('key_value'),
  id: idString.optional(),
  title: shortString.optional(),
  items: z
    .array(
      z.object({
        label: shortString,
        value: keyValueValue,
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
  value: figureOrText,
  unit: shortString.optional(),
  prefix: shortString.optional(),
  delta: numberOrNumericString.optional(),
  deltaTone: z.enum(['up', 'down', 'flat', 'neutral']).optional(),
  hint: shortString.optional(),
  unavailable: z.boolean().optional(),
  // Populated when `value` is a resolved `$ref`; renderer shows a source chip.
  provenance: figureProvenanceSchema.optional(),
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
  'auto',
  'line',
  'area',
  'bar',
  'stacked_bar',
  'grouped_bar',
  'pie',
  'scatter',
  'bubble',
  'histogram',
  'heatmap',
  'treemap',
  'sunburst',
  'funnel',
  'gauge',
  'radar',
  'waterfall',
  'candlestick',
  'ohlc',
] as const;

const chartBandSchema = z.object({
  lower: z.array(z.number().finite()).max(RESPONSE_LIMITS.maxPointsPerSeries),
  upper: z.array(z.number().finite()).max(RESPONSE_LIMITS.maxPointsPerSeries),
  // 0 = a whisper, 1 = a strong range. The renderer maps this to opacity; it is
  // presentation weight, never a probability or a claim about the data.
  weight: z.number().min(0).max(1).optional(),
});

const chartSeriesSchema = z.object({
  name: shortString,
  data: z.array(pointSchema).max(RESPONSE_LIMITS.maxPointsPerSeries),
  color: z
    .string()
    .regex(/^#[0-9a-fA-F]{3,8}$/)
    .optional(),
  // Optional visual emphasis (0..1). Absent preserves the original look.
  weight: z.number().min(0).max(1).optional(),
  // An optional range around the series (a confidence cone, a forecast band).
  band: chartBandSchema.optional(),
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

const flowPathSchema = z.object({
  id: idString.optional(),
  label: shortString,
  description: boundedString.optional(),
  icon: shortString.optional(),
  tone: z.enum(['neutral', 'info', 'success', 'warning', 'danger']).default('neutral'),
  status: z.enum(['pending', 'active', 'done', 'error']).optional(),
});

const flowStepSchema = z.object({
  id: idString.optional(),
  label: shortString,
  description: boundedString.optional(),
  icon: shortString.optional(),
  tone: z.enum(['neutral', 'info', 'success', 'warning', 'danger']).default('neutral'),
  // A step's outgoing paths. Empty means a single step card (a plain linear
  // flow); two or more mean a branch rendered as stacked parallel cards.
  paths: z.array(flowPathSchema).max(RESPONSE_LIMITS.maxFlowPaths).default([]),
});

// A dependency-free HTML/CSS process flow: ordered steps, each branching into
// one or more parallel `paths` rendered as cards. Distinct from `workflow`
// (a strictly LINEAR sequence of icon stages) by supporting parallel/branching
// paths, and from `diagram`/`node_graph` (absolute-positioned SVG node/edge
// graphs, not responsive cards). Producer returns structured data only — never
// an image, SVG, HTML or code.
const flowBlock = z.object({
  type: z.literal('flow'),
  id: idString.optional(),
  title: shortString.optional(),
  description: shortString.optional(),
  direction: z.enum(['LR', 'TB']).default('LR'),
  steps: z.array(flowStepSchema).min(1).max(RESPONSE_LIMITS.maxFlowSteps),
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
  value: figureOrText,
  unit: shortString.optional(),
  prefix: shortString.optional(),
  delta: numberOrNumericString.optional(),
  deltaTone: z.enum(['up', 'down', 'flat', 'neutral']).optional(),
  icon: shortString.optional(),
  hint: shortString.optional(),
  unavailable: z.boolean().optional(),
  provenance: figureProvenanceSchema.optional(),
});

const statHeroBlock = z.object({
  type: z.literal('stat_hero'),
  id: idString.optional(),
  title: shortString.optional(),
  source: shortString.optional(),
  asOf: shortString.optional(),
  description: shortString.optional(),
  caption: shortString.optional(),
  // A producer that has no data for the figure marks the WHOLE block unavailable
  // (the prompt's `"unavailable": true` contract) rather than inventing numbers.
  // The array may then be absent/empty; the renderer shows the UNAVAILABLE state,
  // never an empty figure.
  unavailable: z.boolean().optional(),
  stats: z.array(statHeroStatSchema).max(RESPONSE_LIMITS.maxStats).default([]),
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
  caption: shortString.optional(),
  unavailable: z.boolean().optional(),
  gauges: z.array(gaugeSchema).max(RESPONSE_LIMITS.maxGauges).default([]),
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
  unavailable: z.boolean().optional(),
  // An unavailable matrix may arrive with only the flag + caption; the renderer
  // shows the UNAVAILABLE state rather than failing validation.
  columns: z.array(comparisonColumnSchema).max(RESPONSE_LIMITS.maxCompareColumns).default([]),
  rows: z.array(comparisonRowSchema).max(RESPONSE_LIMITS.maxCompareRows).default([]),
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
  caption: shortString.optional(),
  unavailable: z.boolean().optional(),
  items: z.array(rankedItemSchema).max(RESPONSE_LIMITS.maxRankedItems).default([]),
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
  caption: shortString.optional(),
  unavailable: z.boolean().optional(),
  badges: z.array(badgeSchema).max(RESPONSE_LIMITS.maxBadges).default([]),
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

// An interactive, DETERMINISTIC calculator rendered in chat. Unlike `controls`
// (which composes a follow-up prompt and re-enters the agent loop), a
// `simulation` computes a result LOCALLY from a small, registered, trusted
// formula — no model call and no backend, no arbitrary code. It is explicitly
// labelled illustrative and is never a source of market data. An unknown
// `calculator` kind fails the enum and the block degrades to readable content,
// so a fabricated figure is impossible.
const simulationInputSchema = z.object({
  id: idString,
  label: shortString,
  kind: z.enum(['number', 'select', 'toggle']).default('number'),
  value: z.number().finite().optional(),
  min: z.number().finite().optional(),
  max: z.number().finite().optional(),
  step: z.number().finite().positive().optional(),
  options: z.array(z.object({ value: shortString, label: shortString })).max(24).optional(),
});

const simulationOutputSchema = z.object({
  id: idString,
  label: shortString,
  /** A safe expression over the input ids (see `lib/response/evaluate.ts`).
   *  No JS: a fixed operator set + a whitelisted function set. */
  expression: shortString,
  unit: shortString.optional(),
  precision: z.number().int().min(0).max(8).optional(),
  format: z.enum(['number', 'currency', 'percent']).optional(),
  tone: z.enum(['neutral', 'info', 'success', 'warning', 'danger']).optional(),
});

// ── Layout primitives ─────────────────────────────────────────────────────────
// A container a producer composes structure with, styled ONLY by closed token
// vocabularies (spacing / radius / tone) resolved in `lib/response/tokens.ts` —
// never raw CSS. Nested `blocks` are validated recursively like tabs/report.
const spaceToken = z.enum(['none', 'xs', 'sm', 'md', 'lg', 'xl']);
const toneToken = z.enum(['neutral', 'info', 'success', 'warning', 'danger']);

const layoutBlock = z.object({
  type: z.literal('layout'),
  id: idString.optional(),
  title: shortString.optional(),
  layout: z.enum(['box', 'row', 'column', 'grid']).default('column'),
  columns: z.number().int().min(1).max(4).optional(),
  gap: spaceToken.default('md'),
  pad: spaceToken.optional(),
  radius: z.enum(['none', 'sm', 'md', 'lg', 'xl']).optional(),
  align: z.enum(['start', 'center', 'end', 'stretch']).optional(),
  wrap: z.boolean().optional(),
  tone: toneToken.default('neutral'),
  blocks: z.array(z.unknown()).default([]),
});

const dividerBlock = z.object({
  type: z.literal('divider'),
  id: idString.optional(),
  label: shortString.optional(),
  tone: toneToken.default('neutral'),
});

// The `inputs` block renders envelope `state` controls; `vars` selects a subset
// (all state vars when absent). See the envelope's `state`/`computed` below.
const inputsBlock = z.object({
  type: z.literal('inputs'),
  id: idString.optional(),
  title: shortString.optional(),
  vars: z.array(idString).max(RESPONSE_LIMITS.maxStateVars).optional(),
});

const simulationBlock = z.object({
  type: z.literal('simulation'),
  id: idString.optional(),
  title: shortString.optional(),
  description: shortString.optional(),
  /** A canonical input/output set the producer can opt into; explicit
   *  `inputs`/`outputs` override it. */
  preset: z.enum(['risk_reward']).optional(),
  inputs: z.array(simulationInputSchema).max(RESPONSE_LIMITS.maxSimulationInputs).default([]),
  outputs: z.array(simulationOutputSchema).max(RESPONSE_LIMITS.maxSimulationOutputs).default([]),
  disclaimer: shortString.optional(),
  caption: shortString.optional(),
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
  flowBlock,
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
  simulationBlock,
  layoutBlock,
  dividerBlock,
  inputsBlock,
  anatomyBlock,
  model3dBlock,
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

// Envelope-level shared state + computed values (v1.1, additive — v1.0 payloads
// keep working). An `inputs` block mutates `state`; each `computed` entry is a
// safe expression over state (`lib/response/evaluate.ts`); any figure in any block
// may bind to one with `{ "$computed": "<id>" }`. Entirely client-side — no model
// call, no arbitrary code.
const stateVarSchema = z.object({
  id: idString,
  label: shortString.optional(),
  kind: z.enum(['number', 'select', 'toggle']).default('number'),
  value: z.number().finite().default(0),
  min: z.number().finite().optional(),
  max: z.number().finite().optional(),
  step: z.number().finite().positive().optional(),
  options: z.array(z.object({ value: shortString, label: shortString })).max(24).optional(),
});
export type StateVar = z.infer<typeof stateVarSchema>;

const computedVarSchema = z.object({
  id: idString,
  expression: shortString,
  precision: z.number().int().min(0).max(8).optional(),
  format: z.enum(['number', 'currency', 'percent']).optional(),
  unit: shortString.optional(),
});
export type ComputedVar = z.infer<typeof computedVarSchema>;

export const ResponseEnvelopeSchema = z.object({
  schemaVersion: z.string().max(20).optional(),
  responseId: idString.optional(),
  responseType: shortString.optional(),
  title: shortString.optional(),
  summary: boundedString.optional(),
  state: z.array(stateVarSchema).max(RESPONSE_LIMITS.maxStateVars).default([]),
  computed: z.array(computedVarSchema).max(RESPONSE_LIMITS.maxComputedVars).default([]),
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
export type FlowBlock = z.infer<typeof flowBlock>;
export type FlowStep = z.infer<typeof flowStepSchema>;
export type FlowPath = z.infer<typeof flowPathSchema>;
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
export type SimulationBlock = z.infer<typeof simulationBlock>;
export type AnatomyBlock = z.infer<typeof anatomyBlock>;
export type Model3dBlock = z.infer<typeof model3dBlock>;
export type LayoutBlock = z.infer<typeof layoutBlock>;
export type DividerBlock = z.infer<typeof dividerBlock>;
export type InputsBlock = z.infer<typeof inputsBlock>;
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
  /** Envelope-level shared state (v1.1); empty for older payloads. */
  state: StateVar[];
  /** Envelope-level computed values (v1.1); empty for older payloads. */
  computed: ComputedVar[];
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
      state: [],
      computed: [],
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
    if (block.type === 'layout') {
      const nested = block as z.infer<typeof layoutBlock>;
      nested.blocks = parseNestedBlocks(nested.blocks, 1, diagnostics);
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
    state: envelope.state,
    computed: envelope.computed,
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
    if (block.type === 'layout') {
      const nested = block as z.infer<typeof layoutBlock>;
      nested.blocks = parseNestedBlocks(nested.blocks, depth + 1, out);
    }
    return block;
  });
}
