// Bounded loop node contracts (Phase 4). Split out of `registry.ts` to keep the
// main registry under the size budget; the definitions still live in ONE array.

import { z } from 'zod';
import type { ExecutionMode, NodeDefinition, PortDef } from './types';

const ALL_MODES: ExecutionMode[] = ['research', 'backtest', 'paper', 'live'];

function port(p: PortDef): PortDef {
  return { kind: 'data', ...p };
}

export const LOOP_DEFINITIONS: NodeDefinition[] = [
  {
    type: 'flow.for_each',
    version: '1.0.0',
    category: 'logic',
    label: 'For each',
    description: 'Runs a pinned body workflow once per array item, up to a hard cap.',
    icon: 'branch',
    inputs: [
      port({ id: 'in', name: 'Run', type: 'any', kind: 'control', optional: true }),
      port({ id: 'items', name: 'Items', type: 'array' }),
    ],
    outputs: [
      port({ id: 'results', name: 'Results', type: 'array' }),
      port({ id: 'iterations', name: 'Iterations', type: 'number' }),
      port({ id: 'stopped', name: 'Stopped early', type: 'boolean' }),
      port({ id: 'done', name: 'Done', type: 'any', kind: 'control' }),
    ],
    configSchema: z.object({
      workflowId: z.string().max(80).default(''),
      version: z.number().int().min(1).max(1_000_000).default(1),
      maxIterations: z.number().int().min(1).max(1_000).default(100),
      maxDurationMs: z.number().int().min(0).max(86_400_000).default(0),
      continueOnError: z.boolean().default(false),
    }),
    defaultConfig: () => ({
      workflowId: '', version: 1, maxIterations: 100, maxDurationMs: 0, continueOnError: false,
    }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
    docs: 'Each iteration is a durable child run; a resumed parent reuses a succeeded iteration.',
  },
  {
    type: 'flow.repeat',
    version: '1.0.0',
    category: 'logic',
    label: 'Repeat',
    description: 'Runs a pinned body workflow N times, passing the previous output on.',
    icon: 'branch',
    inputs: [
      port({ id: 'in', name: 'Run', type: 'any', kind: 'control', optional: true }),
      port({ id: 'input', name: 'Input', type: 'any', optional: true }),
    ],
    outputs: [
      port({ id: 'state', name: 'State', type: 'any' }),
      port({ id: 'iterations', name: 'Iterations', type: 'number' }),
      port({ id: 'stopped', name: 'Stopped early', type: 'boolean' }),
      port({ id: 'done', name: 'Done', type: 'any', kind: 'control' }),
    ],
    configSchema: z.object({
      workflowId: z.string().max(80).default(''),
      version: z.number().int().min(1).max(1_000_000).default(1),
      count: z.number().int().min(1).max(1_000).default(1),
      maxDurationMs: z.number().int().min(0).max(86_400_000).default(0),
      continueOnError: z.boolean().default(false),
    }),
    defaultConfig: () => ({
      workflowId: '', version: 1, count: 1, maxDurationMs: 0, continueOnError: false,
    }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
    docs: 'A bounded loop: count is a hard cap and each iteration is checkpointed as a child run.',
  },
  {
    type: 'flow.while',
    version: '1.0.0',
    category: 'logic',
    label: 'While',
    description: 'Runs a pinned body workflow while a safe numeric condition holds.',
    icon: 'branch',
    inputs: [
      port({ id: 'in', name: 'Run', type: 'any', kind: 'control', optional: true }),
      port({ id: 'input', name: 'Initial state', type: 'any', optional: true }),
    ],
    outputs: [
      port({ id: 'state', name: 'Final state', type: 'any' }),
      port({ id: 'iterations', name: 'Iterations', type: 'number' }),
      port({ id: 'stopped', name: 'Stopped early', type: 'boolean' }),
      port({ id: 'done', name: 'Done', type: 'any', kind: 'control' }),
    ],
    configSchema: z.object({
      workflowId: z.string().max(80).default(''),
      version: z.number().int().min(1).max(1_000_000).default(1),
      condition: z.string().max(500).default('value > 0'),
      maxIterations: z.number().int().min(1).max(1_000).default(100),
      maxDurationMs: z.number().int().min(0).max(86_400_000).default(0),
      continueOnError: z.boolean().default(false),
    }),
    defaultConfig: () => ({
      workflowId: '', version: 1, condition: 'value > 0', maxIterations: 100, maxDurationMs: 0,
      continueOnError: false,
    }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
    docs: 'value, index and iterations are in scope. Both caps are enforced by the runtime.',
  },
  {
    type: 'flow.parallel',
    version: '1.0.0',
    category: 'logic',
    label: 'Parallel map',
    description: 'Runs a pinned body workflow once per item, concurrently and bounded.',
    icon: 'branch',
    inputs: [
      port({ id: 'in', name: 'Run', type: 'any', kind: 'control', optional: true }),
      port({ id: 'items', name: 'Items', type: 'array' }),
    ],
    outputs: [
      port({ id: 'results', name: 'Results', type: 'array' }),
      port({ id: 'summary', name: 'Summary', type: 'object' }),
      port({ id: 'done', name: 'Done', type: 'any', kind: 'control' }),
    ],
    configSchema: z.object({
      workflowId: z.string().max(80).default(''),
      version: z.number().int().min(1).max(1_000_000).default(1),
      maxItems: z.number().int().min(1).max(100).default(25),
      concurrency: z.number().int().min(1).max(8).default(4),
      continueOnError: z.boolean().default(true),
    }),
    defaultConfig: () => ({
      workflowId: '', version: 1, maxItems: 25, concurrency: 4, continueOnError: true,
    }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: ALL_MODES,
    docs: 'Concurrency is capped by the workflow’s maxConcurrency setting and a hard cap of 8. Results keep the INPUT order. Each item is a durable child run, so a resumed parent reuses a succeeded item. A failed item is {error} in results; with continueOnError off the node fails naming the first failure.',
  },
];
