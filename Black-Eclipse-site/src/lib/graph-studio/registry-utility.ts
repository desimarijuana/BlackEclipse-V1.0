// Pure utility + memory node contracts. Split out of `registry.ts` to keep the
// main registry under the size budget.
//
// `logic.assert` / `logic.fallback` / `data.extract` are deterministic: no model,
// no store. `memory.recall` / `memory.remember` are thin adapters over the ONE
// Eclipse memory service (same policy, dedupe and retention); `memory.remember`
// writes durable state, so a test run is refused in the executor.

import { z } from 'zod';
import type { ExecutionMode, NodeDefinition, PortDef } from './types';

const ALL_MODES: ExecutionMode[] = ['research', 'backtest', 'paper', 'live'];

// Mirrors `graph_runtime/memory_nodes.MEMORY_TYPES` (asserted by the Python
// test), which in turn mirrors `eclipse_memory.store.MEMORY_TYPES`.
export const MEMORY_TYPES = [
  'episodic', 'semantic', 'procedural', 'preference',
  'constraint', 'correction', 'observation', 'summary',
] as const;

function port(p: PortDef): PortDef {
  return { kind: 'data', ...p };
}

export const UTILITY_DEFINITIONS: NodeDefinition[] = [
  {
    type: 'logic.assert',
    version: '1.0.0',
    category: 'logic',
    label: 'Assert',
    description: 'Fails the run with a named message when the condition is not met.',
    icon: 'check',
    inputs: [
      port({ id: 'in', name: 'Run', type: 'any', kind: 'control', optional: true }),
      port({ id: 'value', name: 'Value', type: 'any', optional: true }),
      port({ id: 'message', name: 'Message', type: 'string', optional: true }),
    ],
    outputs: [
      port({ id: 'value', name: 'Value', type: 'any', nullable: true }),
      port({ id: 'done', name: 'Done', type: 'any', kind: 'control' }),
    ],
    configSchema: z.object({
      expect: z.enum(['truthy', 'falsy', 'present']).default('truthy'),
      message: z.string().max(500).default(''),
    }),
    defaultConfig: () => ({ expect: 'truthy', message: '' }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
    docs: '`present` treats null, "" , [] and {} as absent — the same rule logic.merge uses. It never invents a replacement value.',
  },
  {
    type: 'logic.human_approval',
    version: '1.0.0',
    category: 'logic',
    label: 'Wait for approval',
    description: 'Pauses until an operator approves (or denies) this step.',
    icon: 'clock',
    inputs: [
      port({ id: 'in', name: 'Run', type: 'any', kind: 'control', optional: true }),
      port({ id: 'value', name: 'Value', type: 'any', optional: true }),
      port({ id: 'message', name: 'Message', type: 'string', optional: true }),
    ],
    outputs: [
      port({ id: 'value', name: 'Value', type: 'any', nullable: true }),
      port({ id: 'approved', name: 'Approved', type: 'boolean' }),
      port({ id: 'decidedBy', name: 'Decided by', type: 'string', nullable: true }),
      port({ id: 'done', name: 'Done', type: 'any', kind: 'control' }),
    ],
    configSchema: z.object({
      title: z.string().max(200).default(''),
      message: z.string().max(1_000).default(''),
      risk: z.enum(['low', 'medium', 'high']).default('medium'),
      ttlHours: z.number().int().min(1).max(24).default(12),
      pollSeconds: z.number().int().min(2).max(60).default(5),
      maxWaitS: z.number().int().min(10).max(3_600).default(300),
    }),
    defaultConfig: () => ({
      title: '',
      message: '',
      risk: 'medium',
      ttlHours: 12,
      pollSeconds: 5,
      maxWaitS: 300,
    }),
    capabilities: ['approval.request'],
    sideEffects: 'local_write',
    allowedModes: ALL_MODES,
    docs: 'Creates ONE approval of kind graph_approval for this run+node; a denial fails the node with the approver. A durable run pauses and re-checks instead of holding a worker; a synchronous run polls up to Max wait and then fails honestly (the request stays in Approvals). Test runs never request one.',
  },
  {
    type: 'logic.fallback',
    version: '1.0.0',
    category: 'logic',
    label: 'Fallback',
    description: 'Returns the first present input and which port it came from.',
    icon: 'merge',
    inputs: [
      port({ id: 'in', name: 'Run', type: 'any', kind: 'control', optional: true }),
      port({ id: 'in1', name: 'First', type: 'any', optional: true }),
      port({ id: 'in2', name: 'Second', type: 'any', optional: true }),
      port({ id: 'in3', name: 'Third', type: 'any', optional: true }),
    ],
    outputs: [
      port({ id: 'value', name: 'Value', type: 'any', nullable: true }),
      port({ id: 'source', name: 'Source', type: 'string' }),
      port({ id: 'done', name: 'Done', type: 'any', kind: 'control' }),
    ],
    configSchema: z.object({}),
    defaultConfig: () => ({}),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
    docs: 'Null/""/[]/{} are absent. All absent returns null and an empty source. For two inputs, logic.merge (first_present) is equivalent.',
  },
  {
    type: 'data.extract',
    version: '1.0.0',
    category: 'data',
    label: 'Extract field',
    description: 'Reads a dotted path out of an object or array.',
    icon: 'variable',
    inputs: [
      port({ id: 'in', name: 'Run', type: 'any', kind: 'control', optional: true }),
      port({ id: 'value', name: 'Value', type: 'any' }),
    ],
    outputs: [
      port({ id: 'value', name: 'Value', type: 'any', nullable: true }),
      port({ id: 'found', name: 'Found', type: 'boolean' }),
      port({ id: 'done', name: 'Done', type: 'any', kind: 'control' }),
    ],
    configSchema: z.object({
      path: z.string().max(500).default(''),
      onMissing: z.enum(['null', 'error']).default('null'),
    }),
    defaultConfig: () => ({ path: '', onMissing: 'null' }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
    docs: 'A numeric segment indexes a list. A missing path returns found: false + null, or fails by name when onMissing is `error`. It never invents a value.',
  },
  {
    type: 'research.source_rank',
    version: '1.0.0',
    category: 'research',
    label: 'Rank evidence',
    description: 'Ranks evidence by the confidence and freshness it already carries.',
    icon: 'activity',
    inputs: [port({ id: 'evidence', name: 'Evidence', type: 'array', optional: true })],
    outputs: [
      port({ id: 'evidence', name: 'Ranked evidence', type: 'array' }),
      port({ id: 'ranking', name: 'Ranking', type: 'array' }),
      port({ id: 'summary', name: 'Summary', type: 'object' }),
    ],
    configSchema: z.object({
      halfLifeDays: z.number().int().min(1).max(3_650).default(30),
    }),
    defaultConfig: () => ({ halfLifeDays: 30 }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
    docs: 'Pure: confidence + exponential freshness decay of publishedAt/retrievedAt. An item with neither is sorted last and counted as insufficient_signal — no score is invented.',
  },
  {
    type: 'memory.recall',
    version: '1.0.0',
    category: 'data',
    label: 'Recall memory',
    description: 'Reads the app memory service into the graph.',
    icon: 'bot',
    inputs: [port({ id: 'query', name: 'Query', type: 'string', optional: true })],
    outputs: [
      port({ id: 'memories', name: 'Memories', type: 'array' }),
      port({ id: 'context', name: 'Context', type: 'string' }),
      port({ id: 'count', name: 'Count', type: 'number' }),
    ],
    configSchema: z.object({
      query: z.string().max(2_000).default(''),
      types: z.string().max(300).default(''),
      limit: z.number().int().min(1).max(50).default(8),
      scope: z.string().max(40).default(''),
    }),
    defaultConfig: () => ({ query: '', types: '', limit: 8, scope: '' }),
    capabilities: ['research.read'],
    sideEffects: 'read',
    allowedModes: ALL_MODES,
    docs: 'Uses the ONE memory service, so its policy, dedupe and recall-deny rules apply. `context` is the same bounded prompt block an agent receives.',
  },
  {
    type: 'memory.remember',
    version: '1.0.0',
    category: 'data',
    label: 'Remember',
    description: 'Writes one durable memory record.',
    icon: 'bot',
    inputs: [port({ id: 'content', name: 'Content', type: 'string', optional: true })],
    outputs: [
      port({ id: 'memory', name: 'Memory', type: 'object' }),
      port({ id: 'written', name: 'Written', type: 'boolean' }),
    ],
    configSchema: z.object({
      content: z.string().max(4_000).default(''),
      memoryType: z.enum(MEMORY_TYPES).default('observation'),
      scope: z.string().max(40).default('general'),
      subject: z.string().max(200).default(''),
      importance: z.number().min(0).max(1).default(0.5),
    }),
    defaultConfig: () => ({
      content: '',
      memoryType: 'observation',
      scope: 'general',
      subject: '',
      importance: 0.5,
    }),
    capabilities: ['memory.write'],
    sideEffects: 'local_write',
    allowedModes: ALL_MODES,
    docs: 'Dedupe, conflict resolution and retention are the memory service\'s. Operator-run only: a test run is refused so it cannot leave state behind.',
  },
];
