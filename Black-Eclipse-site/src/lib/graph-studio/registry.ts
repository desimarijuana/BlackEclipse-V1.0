// ── Node registry & SDK ───────────────────────────────────────────────────────
// Every executable node declares itself here ONCE. The canvas, the inspector,
// validation and (Phase 3+) the compiler all read from this registry, so
// registering a new node never requires editing the editor.
//
// A definition is a CONTRACT: stable `type`, a `version`, typed ports, a config
// schema, a side-effect class, the capabilities it needs, and the modes it may
// run in. The editor uses it to render and to validate; the runtime re-checks
// it before execution. The registry is intentionally data-only (no executor
// functions yet) so it is safe to import from client and server alike.

import { z } from 'zod';
import type { ExecutionMode, NodeDefinition, PortDef } from './types';

/** All operating modes — the default allowance for a pure/read node. */
const ALL_MODES: ExecutionMode[] = ['research', 'backtest', 'paper', 'live'];
/** Modes allowed for nodes that read market data (no money moves). */
const READ_MODES: ExecutionMode[] = ['research', 'backtest', 'paper', 'live'];

function port(p: PortDef): PortDef {
  return { kind: 'data', ...p };
}

const DEFINITIONS: NodeDefinition[] = [
  {
    type: 'trigger.manual',
    version: '1.0.0',
    category: 'trigger',
    label: 'Manual trigger',
    description: 'Starts a run when a user executes the workflow by hand.',
    icon: 'play',
    inputs: [],
    outputs: [port({ id: 'start', name: 'Start', type: 'any' })],
    configSchema: z.object({ seed: z.string().max(4_000).default('') }),
    defaultConfig: () => ({ seed: '' }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
    docs: 'The entry point of every runnable graph. Emits an optional seed value (e.g. a symbol).',
  },
  {
    type: 'trigger.schedule',
    version: '1.0.0',
    category: 'trigger',
    label: 'Schedule',
    description: 'Starts a run on a timezone-aware cron schedule.',
    icon: 'clock',
    inputs: [],
    outputs: [port({ id: 'start', name: 'Start', type: 'any' })],
    configSchema: z.object({
      cron: z.string().min(1).max(120).default('0 9 * * 1-5'),
      timezone: z.string().max(60).default('UTC'),
    }),
    defaultConfig: () => ({ cron: '0 9 * * 1-5', timezone: 'UTC' }),
    capabilities: ['schedule.manage'],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
    docs: 'Scheduling is executed by the runtime scheduler, not the editor.',
  },
  {
    type: 'data.value',
    version: '1.0.0',
    category: 'data',
    label: 'Constant / input',
    description: 'Emits a literal value, or the value arriving on its input.',
    icon: 'variable',
    inputs: [port({ id: 'in', name: 'In', type: 'any', optional: true })],
    outputs: [port({ id: 'value', name: 'Value', type: 'any' })],
    configSchema: z.object({
      value: z.string().max(8_000).default(''),
      dataType: z
        .enum(['string', 'number', 'boolean', 'object', 'array'])
        .default('string'),
    }),
    defaultConfig: () => ({ value: '', dataType: 'string' }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
  },
  {
    type: 'data.json.parse',
    version: '1.0.0',
    category: 'data',
    label: 'Parse JSON',
    description: 'Parses a JSON string into a structured object.',
    icon: 'braces',
    inputs: [port({ id: 'text', name: 'Text', type: 'string' })],
    // JSON.parse may yield an object, an array, a number, a string or a boolean
    // — declaring `object` would be wrong (and would block arrays).
    outputs: [port({ id: 'value', name: 'Value', type: 'any' })],
    configSchema: z.object({ strict: z.boolean().default(true) }),
    defaultConfig: () => ({ strict: true }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
  },
  {
    type: 'transform.template',
    version: '1.0.0',
    category: 'transform',
    label: 'Template',
    description: 'Renders a string template from its inputs.',
    icon: 'text',
    inputs: [
      port({ id: 'a', name: 'A', type: 'any', optional: true }),
      port({ id: 'b', name: 'B', type: 'any', optional: true }),
    ],
    outputs: [port({ id: 'text', name: 'Text', type: 'string' })],
    configSchema: z.object({ template: z.string().max(4_000).default('{{a}}') }),
    defaultConfig: () => ({ template: '{{a}}' }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
  },
  {
    type: 'transform.formula',
    version: '1.0.0',
    category: 'transform',
    label: 'Formula',
    description: 'Evaluates a bounded arithmetic expression over numeric inputs.',
    icon: 'sigma',
    inputs: [
      port({ id: 'x', name: 'X', type: 'number' }),
      port({ id: 'y', name: 'Y', type: 'number', optional: true }),
    ],
    outputs: [port({ id: 'result', name: 'Result', type: 'number' })],
    configSchema: z.object({ expression: z.string().max(400).default('x') }),
    defaultConfig: () => ({ expression: 'x' }),
    capabilities: ['compute.safe'],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
    docs: 'The expression language is the runtime\'s safe evaluator — never eval().',
  },
  {
    type: 'logic.condition',
    version: '1.0.0',
    category: 'logic',
    label: 'If / else',
    description: 'Routes control flow on a declared comparison.',
    icon: 'branch',
    inputs: [port({ id: 'value', name: 'Value', type: 'any' })],
    outputs: [
      { id: 'true', name: 'True', type: 'any', kind: 'control' },
      { id: 'false', name: 'False', type: 'any', kind: 'control' },
      port({ id: 'result', name: 'Result', type: 'boolean', optional: true }),
    ],
    configSchema: z.object({
      operator: z
        .enum(['eq', 'neq', 'gt', 'gte', 'lt', 'lte', 'truthy'])
        .default('truthy'),
      compareTo: z.string().max(400).default(''),
    }),
    defaultConfig: () => ({ operator: 'truthy', compareTo: '' }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
  },
  {
    type: 'logic.merge',
    version: '1.0.0',
    category: 'logic',
    label: 'Merge',
    description: 'Joins two branches back into one value.',
    icon: 'merge',
    inputs: [
      port({ id: 'a', name: 'A', type: 'any' }),
      port({ id: 'b', name: 'B', type: 'any', optional: true }),
    ],
    outputs: [port({ id: 'value', name: 'Value', type: 'any' })],
    configSchema: z.object({ strategy: z.enum(['first', 'object']).default('first') }),
    defaultConfig: () => ({ strategy: 'first' }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
  },
  {
    type: 'integration.http',
    version: '1.0.0',
    category: 'integration',
    label: 'HTTP request',
    description: 'Calls an external HTTP endpoint. Egress is default-deny.',
    icon: 'globe',
    inputs: [port({ id: 'body', name: 'Body', type: 'object', optional: true })],
    outputs: [
      port({ id: 'status', name: 'Status', type: 'number' }),
      port({ id: 'body', name: 'Body', type: 'object' }),
    ],
    configSchema: z.object({
      url: z.string().max(2_000).default(''),
      method: z.enum(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']).default('GET'),
    }),
    defaultConfig: () => ({ url: '', method: 'GET' }),
    capabilities: ['network.egress'],
    sideEffects: 'network',
    allowedModes: ALL_MODES,
  },
  {
    type: 'finance.market_data',
    version: '1.0.0',
    category: 'finance',
    label: 'Market data',
    description: 'Reads a price series via the existing data gateway + JDDS.',
    icon: 'chart',
    inputs: [port({ id: 'symbol', name: 'Symbol', type: 'string', optional: true })],
    outputs: [
      port({ id: 'series', name: 'OHLCV', type: 'ohlcv' }),
      port({ id: 'provenance', name: 'Provenance', type: 'evidence' }),
    ],
    configSchema: z.object({
      symbol: z.string().max(40).default(''),
      interval: z.enum(['1m', '5m', '15m', '1h', '1d']).default('1d'),
      lookback: z.number().int().min(1).max(5_000).default(200),
    }),
    defaultConfig: () => ({ symbol: '', interval: '1d', lookback: 200 }),
    capabilities: ['market.read'],
    sideEffects: 'read',
    allowedModes: READ_MODES,
    docs: 'Reuses the FinancialDataRouter / JDDS — no second ingestion path.',
  },
  {
    type: 'video.render',
    version: '1.0.0',
    category: 'finance',
    label: 'Video render',
    description:
      'Builds a data-bound market-recap storyboard and queues the native video render.',
    icon: 'chart',
    inputs: [port({ id: 'symbols', name: 'Symbols', type: 'array' })],
    outputs: [
      port({ id: 'project', name: 'Project', type: 'object' }),
      port({ id: 'job', name: 'Job', type: 'object' }),
    ],
    configSchema: z.object({
      title: z.string().max(80).default('Market recap'),
      mode: z.enum(['draft', 'final']).default('draft'),
    }),
    defaultConfig: () => ({ title: 'Market recap', mode: 'draft' }),
    capabilities: ['video.render'],
    sideEffects: 'write',
    allowedModes: ALL_MODES,
    // Declared in lockstep with Python, executor-less on purpose: a render is
    // an async Fabric job and test-run envelopes refuse effectful nodes. The
    // compiler reports `executor_unavailable` with the exact missing phase.
    docs: 'Executor pending async graph execution + an operator-run envelope for effectful nodes. Until then use the video tools or POST /video/projects/{id}/render.',
  },
  {
    type: 'finance.indicator',
    version: '1.0.0',
    category: 'quant',
    label: 'Indicator',
    description: 'Computes a deterministic technical indicator.',
    icon: 'activity',
    inputs: [port({ id: 'series', name: 'OHLCV', type: 'ohlcv' })],
    outputs: [port({ id: 'values', name: 'Values', type: 'indicator' })],
    configSchema: z.object({
      kind: z
        .enum(['sma', 'ema', 'rsi', 'macd', 'atr', 'adx', 'vwap', 'bollinger'])
        .default('sma'),
      period: z.number().int().min(1).max(500).default(20),
    }),
    defaultConfig: () => ({ kind: 'sma', period: 20 }),
    capabilities: ['quant.compute'],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
    docs: 'Indicator math lives in the quant engine and is independently tested.',
  },
  {
    type: 'agent.research',
    version: '1.0.0',
    category: 'agent',
    label: 'Research agent',
    description: 'Runs a bounded agent turn and returns a structured finding.',
    icon: 'bot',
    inputs: [port({ id: 'query', name: 'Query', type: 'string' })],
    outputs: [
      port({ id: 'finding', name: 'Finding', type: 'research_finding' }),
      port({ id: 'evidence', name: 'Evidence', type: 'evidence' }),
    ],
    configSchema: z.object({
      agent: z.string().max(80).default('eclipse-agent'),
      objective: z.string().max(2_000).default(''),
      maxSteps: z.number().int().min(1).max(32).default(8),
    }),
    defaultConfig: () => ({ agent: 'eclipse-agent', objective: '', maxSteps: 8 }),
    capabilities: ['agent.run'],
    sideEffects: 'network',
    allowedModes: ALL_MODES,
    docs: 'Invokes the existing Python agent runtime — not a second agent loop.',
  },
  // ── Control flow (Phase 4) ──────────────────────────────────────────────
  // Control ports gate EXECUTION, not values: a node that declares control
  // inputs runs only when an upstream fired one of them.
  {
    type: 'flow.gate',
    version: '1.0.0',
    category: 'logic',
    label: 'Gate',
    description: 'Runs only when its control input fires — the if/else branch primitive.',
    icon: 'branch',
    inputs: [
      { id: 'in', name: 'In', type: 'any', kind: 'control' },
      port({ id: 'value', name: 'Value', type: 'any', optional: true }),
    ],
    outputs: [port({ id: 'value', name: 'Value', type: 'any' })],
    configSchema: z.object({}),
    defaultConfig: () => ({}),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
  },
  {
    type: 'logic.switch',
    version: '1.0.0',
    category: 'logic',
    label: 'Switch',
    description: 'Fires `matched` or `default` and reports the case index.',
    icon: 'branch',
    inputs: [port({ id: 'value', name: 'Value', type: 'any' })],
    outputs: [
      { id: 'matched', name: 'Matched', type: 'any', kind: 'control' },
      { id: 'default', name: 'Default', type: 'any', kind: 'control' },
      port({ id: 'caseIndex', name: 'Case index', type: 'number' }),
    ],
    configSchema: z.object({ cases: z.string().max(400).default('') }),
    defaultConfig: () => ({ cases: '' }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
  },
  {
    type: 'logic.map',
    version: '1.0.0',
    category: 'logic',
    label: 'Map',
    description: 'Evaluates a formula for each numeric item (vars: value, index).',
    icon: 'sigma',
    inputs: [port({ id: 'items', name: 'Items', type: 'array' })],
    outputs: [port({ id: 'items', name: 'Items', type: 'array' })],
    configSchema: z.object({ expression: z.string().max(400).default('value') }),
    defaultConfig: () => ({ expression: 'value' }),
    capabilities: ['compute.safe'],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
  },
  {
    type: 'logic.filter',
    version: '1.0.0',
    category: 'logic',
    label: 'Filter',
    description: 'Keeps numeric items whose formula result is non-zero.',
    icon: 'sigma',
    inputs: [port({ id: 'items', name: 'Items', type: 'array' })],
    outputs: [
      port({ id: 'items', name: 'Items', type: 'array' }),
      port({ id: 'dropped', name: 'Dropped', type: 'number' }),
    ],
    configSchema: z.object({ expression: z.string().max(400).default('value != 0') }),
    defaultConfig: () => ({ expression: 'value != 0' }),
    capabilities: ['compute.safe'],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
  },
  {
    type: 'logic.reduce',
    version: '1.0.0',
    category: 'logic',
    label: 'Reduce',
    description: 'Accumulates numeric items (vars: acc, value, index).',
    icon: 'sigma',
    inputs: [port({ id: 'items', name: 'Items', type: 'array' })],
    outputs: [port({ id: 'value', name: 'Value', type: 'number' })],
    configSchema: z.object({
      expression: z.string().max(400).default('acc + value'),
      initial: z.number().default(0),
    }),
    defaultConfig: () => ({ expression: 'acc + value', initial: 0 }),
    capabilities: ['compute.safe'],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
  },
  {
    type: 'logic.wait',
    version: '1.0.0',
    category: 'logic',
    label: 'Wait',
    description: 'Pauses for a bounded time (a test run allows at most 5 s).',
    icon: 'clock',
    inputs: [{ id: 'in', name: 'In', type: 'any', kind: 'control', optional: true }],
    outputs: [port({ id: 'waitedMs', name: 'Waited', type: 'number' })],
    configSchema: z.object({ ms: z.number().int().min(0).max(30_000).default(0) }),
    defaultConfig: () => ({ ms: 0 }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
  },
  {
    type: 'logic.stop',
    version: '1.0.0',
    category: 'logic',
    label: 'Stop',
    description: 'Ends the run here; downstream nodes are skipped.',
    icon: 'check',
    inputs: [{ id: 'in', name: 'In', type: 'any', kind: 'control', optional: true }],
    outputs: [port({ id: 'stopped', name: 'Stopped', type: 'boolean' })],
    configSchema: z.object({
      message: z.string().max(400).default(''),
      status: z.enum(['succeeded', 'failed']).default('succeeded'),
    }),
    defaultConfig: () => ({ message: '', status: 'succeeded' }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
    terminal: true,
  },
  // ── Quant (Phase 5) ─────────────────────────────────────────────────────
  // Executors live in the Python runtime (`graph_runtime/finance_nodes.py`) and
  // reuse the tested quant engine; these contracts are mirrored exactly.
  {
    type: 'quant.returns',
    version: '1.0.0',
    category: 'quant',
    label: 'Returns',
    description: 'Simple or log returns of a series over a period.',
    icon: 'activity',
    inputs: [port({ id: 'values', name: 'Values', type: 'indicator' })],
    outputs: [port({ id: 'values', name: 'Values', type: 'indicator' })],
    configSchema: z.object({
      kind: z.enum(['simple', 'log']).default('simple'),
      period: z.number().int().min(1).max(500).default(1),
    }),
    defaultConfig: () => ({ kind: 'simple', period: 1 }),
    capabilities: ['quant.compute'],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
  },
  {
    type: 'quant.zscore',
    version: '1.0.0',
    category: 'quant',
    label: 'Z-score',
    description: 'Rolling standard score of a series.',
    icon: 'activity',
    inputs: [port({ id: 'values', name: 'Values', type: 'indicator' })],
    outputs: [port({ id: 'values', name: 'Values', type: 'indicator' })],
    configSchema: z.object({ period: z.number().int().min(2).max(500).default(20) }),
    defaultConfig: () => ({ period: 20 }),
    capabilities: ['quant.compute'],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
  },
  {
    type: 'quant.volatility',
    version: '1.0.0',
    category: 'quant',
    label: 'Volatility',
    description: 'Rolling standard deviation of log returns, optionally annualized.',
    icon: 'activity',
    inputs: [port({ id: 'values', name: 'Values', type: 'indicator' })],
    outputs: [port({ id: 'values', name: 'Values', type: 'indicator' })],
    configSchema: z.object({
      period: z.number().int().min(2).max(500).default(20),
      annualize: z.boolean().default(false),
      periodsPerYear: z.number().int().min(1).max(1_000).default(252),
    }),
    defaultConfig: () => ({ period: 20, annualize: false, periodsPerYear: 252 }),
    capabilities: ['quant.compute'],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
  },
  {
    type: 'output.result',
    version: '1.0.0',
    category: 'output',
    label: 'Result',
    description: 'Terminal node — captures the workflow result.',
    icon: 'check',
    inputs: [port({ id: 'value', name: 'Value', type: 'any' })],
    outputs: [],
    configSchema: z.object({ label: z.string().max(120).default('Result') }),
    defaultConfig: () => ({ label: 'Result' }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
    terminal: true,
  },
];

function key(type: string, version: string): string {
  return `${type}@${version}`;
}

const REGISTRY = new Map<string, NodeDefinition>();
for (const def of DEFINITIONS) REGISTRY.set(key(def.type, def.version), def);

/** The latest definition for a type, or undefined if unregistered. */
export function getNodeDefinition(type: string, version?: string): NodeDefinition | undefined {
  if (version) return REGISTRY.get(key(type, version));
  // No version requested: return the highest by node-type version ordering.
  const matches = DEFINITIONS.filter((d) => d.type === type);
  if (matches.length === 0) return undefined;
  return matches.sort((a, b) => b.version.localeCompare(a.version, undefined, { numeric: true }))[0];
}

export function listNodeDefinitions(): NodeDefinition[] {
  return [...DEFINITIONS];
}

/** Every node type in a category, for the palette. */
export function nodesByCategory(): Record<string, NodeDefinition[]> {
  const out: Record<string, NodeDefinition[]> = {};
  for (const def of DEFINITIONS) {
    (out[def.category] ??= []).push(def);
  }
  return out;
}

/** True when `version` is a registered version of `type`. */
export function isKnownNodeVersion(type: string, version: string): boolean {
  return REGISTRY.has(key(type, version));
}
