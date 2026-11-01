// Transform-node contracts (template, formula, tabular rows). Split out of
// `registry.ts` to keep the main registry under the size budget; the
// definitions still live in ONE flat array via the spread in `registry.ts`.
//
// Every node here is pure: no clock, no network, no store. The escape hatches
// (dotted paths, formats, join modes) are all bounded and fail honestly.

import { z } from 'zod';
import type { ExecutionMode, NodeDefinition, PortDef } from './types';

const ALL_MODES: ExecutionMode[] = ['research', 'backtest', 'paper', 'live'];

function port(p: PortDef): PortDef {
  return { kind: 'data', ...p };
}

export const TRANSFORM_DEFINITIONS: NodeDefinition[] = [
  {
    type: 'transform.template',
    version: '1.0.0',
    category: 'transform',
    label: 'Template',
    description: 'Renders a string template from its inputs.',
    icon: 'text',
    inputs: [
      port({ id: 'in', name: 'Run', type: 'any', kind: 'control', optional: true }),
      port({ id: 'a', name: 'A', type: 'any', optional: true }),
      port({ id: 'b', name: 'B', type: 'any', optional: true }),
    ],
    outputs: [
      port({ id: 'text', name: 'Text', type: 'string' }),
      port({ id: 'done', name: 'Done', type: 'any', kind: 'control' }),
    ],
    configSchema: z.object({ template: z.string().max(4_000).default('{{a}}') }),
    defaultConfig: () => ({ template: '{{a}}' }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
    docs: 'Placeholders: {{a}}, {{a.price}} (dotted path), {{a.price:.2f}} (number format), {{a.ts:date:%Y-%m-%d}} and {{a?}} (blank when null). A bare {{a}} with a null value is an error, never a silent blank. {{#each a}}…{{/each}} renders one block per row ({{this}} and {{index}} inside); \\{{ is a literal brace.',
  },
  {
    type: 'transform.formula',
    version: '1.0.0',
    category: 'transform',
    label: 'Formula',
    description: 'Evaluates a bounded arithmetic expression over numeric inputs.',
    icon: 'sigma',
    inputs: [
      port({ id: 'in', name: 'Run', type: 'any', kind: 'control', optional: true }),
      port({ id: 'x', name: 'X', type: 'any' }),
      port({ id: 'y', name: 'Y', type: 'any', optional: true }),
    ],
    outputs: [
      port({ id: 'result', name: 'Result', type: 'number' }),
      port({ id: 'done', name: 'Done', type: 'any', kind: 'control' }),
    ],
    configSchema: z.object({ expression: z.string().max(400).default('x') }),
    defaultConfig: () => ({ expression: 'x' }),
    capabilities: ['compute.safe'],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
    docs: 'Safe evaluator over x/y (numbers or series payloads), pi, e. Functions: if(cond,a,b), div(a,b[,fallback]), nz(x[,fallback]), clamp(x,lo,hi), min, max, abs, round(x[,digits]) half-up, floor, ceil, sqrt, log, log10, exp, pow, sign. Never eval().',
  },
  {
    type: 'transform.select',
    version: '1.0.0',
    category: 'transform',
    label: 'Select fields',
    description: 'Selects and renames columns in an array of objects.',
    icon: 'text',
    inputs: [
      port({ id: 'in', name: 'Run', type: 'any', kind: 'control', optional: true }),
      port({ id: 'rows', name: 'Rows', type: 'array' }),
    ],
    outputs: [
      port({ id: 'rows', name: 'Rows', type: 'array' }),
      port({ id: 'dropped', name: 'Dropped', type: 'number' }),
      port({ id: 'done', name: 'Done', type: 'any', kind: 'control' }),
    ],
    configSchema: z.object({
      fields: z.string().max(4_000).default(''),
      rename: z.string().max(4_000).default(''),
      onMissing: z.enum(['null', 'drop', 'error']).default('null'),
    }),
    defaultConfig: () => ({ fields: '', rename: '', onMissing: 'null' }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
    docs: 'fields is comma-separated and resolves dotted paths; `pe=fundamentals.pe` aliases a column. Empty fields keeps every column. onMissing decides what a missing path does: null column, drop the row, or fail.',
  },
  {
    type: 'transform.sort_limit',
    version: '1.0.0',
    category: 'transform',
    label: 'Sort / limit',
    description: 'Sorts rows by dotted keys (or the whole row) and optionally limits them.',
    icon: 'text',
    inputs: [
      port({ id: 'in', name: 'Run', type: 'any', kind: 'control', optional: true }),
      port({ id: 'rows', name: 'Rows', type: 'array' }),
    ],
    outputs: [
      port({ id: 'rows', name: 'Rows', type: 'array' }),
      port({ id: 'done', name: 'Done', type: 'any', kind: 'control' }),
    ],
    configSchema: z.object({
      field: z.string().max(1_000).default(''),
      order: z.enum(['asc', 'desc']).default('asc'),
      limit: z.number().int().min(0).max(100_000).default(0),
      offset: z.number().int().min(0).max(100_000).default(0),
      caseInsensitive: z.boolean().default(false),
    }),
    defaultConfig: () => ({ field: '', order: 'asc', limit: 0, offset: 0, caseInsensitive: false }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
    docs: 'field takes one or more keys: `date desc, symbol` (order is the default for keys without a suffix). Numeric strings sort as numbers and nulls always sort last. limit 0 means no limit.',
  },
  {
    type: 'logic.aggregate',
    version: '1.0.0',
    category: 'logic',
    label: 'Aggregate / group',
    description: 'Numeric aggregate, optionally grouped by dotted fields.',
    icon: 'sigma',
    inputs: [
      port({ id: 'in', name: 'Run', type: 'any', kind: 'control', optional: true }),
      port({ id: 'items', name: 'Items', type: 'array' }),
    ],
    outputs: [
      port({ id: 'value', name: 'Value', type: 'number', nullable: true }),
      port({ id: 'groups', name: 'Groups', type: 'array' }),
      port({ id: 'done', name: 'Done', type: 'any', kind: 'control' }),
    ],
    configSchema: z.object({
      field: z.string().max(200).default(''),
      op: z.enum(['sum', 'avg', 'min', 'max', 'count', 'median', 'stddev', 'percentile']).default('sum'),
      groupBy: z.string().max(1_000).default(''),
      percentile: z.number().min(0).max(100).default(50),
    }),
    defaultConfig: () => ({ field: '', op: 'sum', groupBy: '', percentile: 50 }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
    docs: 'count needs no field; every other op requires a numeric field. stddev is the sample form (n-1); percentile interpolates linearly at the configured p (0-100). An empty input yields null (never a fabricated 0) for every op except count.',
  },
  {
    type: 'logic.deduplicate',
    version: '1.0.0',
    category: 'logic',
    label: 'Deduplicate',
    description: 'Keeps the first row per key, or per whole row when keys is empty.',
    icon: 'sigma',
    inputs: [
      port({ id: 'in', name: 'Run', type: 'any', kind: 'control', optional: true }),
      port({ id: 'items', name: 'Items', type: 'array' }),
    ],
    outputs: [
      port({ id: 'items', name: 'Items', type: 'array' }),
      port({ id: 'dropped', name: 'Dropped', type: 'number' }),
      port({ id: 'done', name: 'Done', type: 'any', kind: 'control' }),
    ],
    configSchema: z.object({
      keys: z.string().max(1_000).default(''),
      keep: z.enum(['first', 'last']).default('first'),
      caseInsensitive: z.boolean().default(false),
    }),
    defaultConfig: () => ({ keys: '', keep: 'first', caseInsensitive: false }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
    docs: 'Keys compare with the join identity rule (1, 1.0 and "1" are one row).',
  },
  {
    type: 'transform.join',
    version: '1.0.0',
    category: 'transform',
    label: 'Join rows',
    description: 'Inner, left, right, full or anti join of two arrays of objects on dotted keys.',
    icon: 'merge',
    inputs: [
      port({ id: 'in', name: 'Run', type: 'any', kind: 'control', optional: true }),
      port({ id: 'left', name: 'Left', type: 'array' }),
      port({ id: 'right', name: 'Right', type: 'array' }),
    ],
    outputs: [
      port({ id: 'rows', name: 'Rows', type: 'array' }),
      port({ id: 'matched', name: 'Matched', type: 'number' }),
      port({ id: 'done', name: 'Done', type: 'any', kind: 'control' }),
    ],
    configSchema: z.object({
      leftKey: z.string().max(1_000).default(''),
      rightKey: z.string().max(1_000).default(''),
      how: z.enum(['inner', 'left', 'right', 'full', 'anti']).default('inner'),
      caseInsensitive: z.boolean().default(false),
      suffix: z.string().max(100).default(''),
      onDuplicate: z.enum(['first', 'last', 'all']).default('first'),
    }),
    defaultConfig: () => ({
      leftKey: '', rightKey: '', how: 'inner', caseInsensitive: false, suffix: '', onDuplicate: 'first',
    }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
    docs: 'Both keys accept a comma-separated composite (`symbol,date`). Keys normalise numbers/numeric strings, so "123" matches 123. onDuplicate decides what happens when several right rows share a key; suffix keeps colliding right columns instead of losing them.',
  },
];
