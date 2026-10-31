// ── Eclipse Workflow IR — the canonical, versioned graph representation ──────
// This is the ONE workflow document model. It is deliberately independent of
// React Flow's internal node/edge shape: React Flow state is built FROM the IR
// and folded BACK into it, never the other way around. The IR is what gets
// validated, versioned, diffed, compiled and (Phase 3+) executed.
//
// Storage is untrusted: `parseWorkflowIR` re-validates every field with zod. A
// stored document that no longer satisfies the schema is migrated first (see
// `migrations.ts`) and rejected if it still cannot be read.

import { z } from 'zod';
import { WORKFLOW_IR_VERSION } from './types';
import type {
  ExecutionMode,
  PortDef,
  WorkflowEdge,
  WorkflowIR,
  WorkflowNode,
  WorkflowSettings,
} from './types';

export const PORT_TYPES = [
  'number', 'boolean', 'string', 'object', 'array', 'datetime',
  'instrument', 'ohlcv', 'indicator', 'signal', 'portfolio', 'order_intent',
  'research_finding', 'evidence', 'agent_result', 'execution_result', 'any',
] as const;

export const EXECUTION_MODES = ['research', 'backtest', 'paper', 'live'] as const;

export const portTypeSchema = z.enum(PORT_TYPES);

export const portSchema = z.object({
  id: z.string().min(1).max(64),
  name: z.string().min(1).max(80),
  type: portTypeSchema,
  kind: z.enum(['data', 'control']).default('data'),
  optional: z.boolean().optional(),
  nullable: z.boolean().optional(),
  description: z.string().max(300).optional(),
});

export const positionSchema = z.object({
  x: z.number().finite(),
  y: z.number().finite(),
});

export const nodeSchema = z.object({
  id: z.string().min(1).max(80),
  type: z.string().min(1).max(120),
  version: z.string().min(1).max(32),
  label: z.string().max(120).optional(),
  notes: z.string().max(2_000).optional(),
  config: z.record(z.string(), z.unknown()).default({}),
  layout: positionSchema,
});

export const edgeSchema = z.object({
  id: z.string().min(1).max(120),
  source: z.string().min(1).max(80),
  sourceHandle: z.string().min(1).max(64),
  target: z.string().min(1).max(80),
  targetHandle: z.string().min(1).max(64),
  condition: z.string().max(500).optional(),
});

export const settingsSchema = z.object({
  executionMode: z.enum(EXECUTION_MODES).default('research'),
  failFast: z.boolean().default(false),
  maxConcurrency: z.number().int().min(1).max(64).default(4),
  timeoutMs: z.number().int().min(0).max(3_600_000).default(0),
});

export const workflowIRSchema = z.object({
  irVersion: z.number().int().min(1),
  id: z.string().min(1).max(80),
  name: z.string().min(1).max(200),
  description: z.string().max(2_000).default(''),
  meta: z
    .object({
      createdAt: z.string().default(''),
      updatedAt: z.string().default(''),
      tags: z.array(z.string().max(40)).max(32).default([]),
    })
    .default({ createdAt: '', updatedAt: '', tags: [] }),
  nodes: z.array(nodeSchema).max(500),
  edges: z.array(edgeSchema).max(2_000),
  settings: settingsSchema,
  requiredCapabilities: z.array(z.string().max(80)).max(64).default([]),
});

export class WorkflowIRError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'WorkflowIRError';
  }
}

/** Validate an already-migrated object and return a typed IR, or throw. */
export function parseWorkflowIR(value: unknown): WorkflowIR {
  const result = workflowIRSchema.safeParse(value);
  if (!result.success) {
    const first = result.error.issues[0];
    const path = first?.path.join('.') ?? '';
    throw new WorkflowIRError(
      `Invalid workflow IR${path ? ` at ${path}` : ''}: ${first?.message ?? 'unknown error'}`,
    );
  }
  return result.data as WorkflowIR;
}

export function defaultSettings(): WorkflowSettings {
  return { executionMode: 'research', failFast: false, maxConcurrency: 4, timeoutMs: 0 };
}

/** Generate a fresh, empty workflow document. */
export function createWorkflowIR(overrides: Partial<WorkflowIR> = {}): WorkflowIR {
  const now = new Date().toISOString();
  return {
    irVersion: WORKFLOW_IR_VERSION,
    id: overrides.id ?? `wf_${Math.random().toString(36).slice(2, 10)}`,
    name: overrides.name ?? 'Untitled workflow',
    description: overrides.description ?? '',
    meta: overrides.meta ?? { createdAt: now, updatedAt: now, tags: [] },
    nodes: overrides.nodes ?? [],
    edges: overrides.edges ?? [],
    settings: overrides.settings ?? defaultSettings(),
    requiredCapabilities: overrides.requiredCapabilities ?? [],
  };
}

/** A stable handle id from a port, matching how the canvas derives handles. */
export function handleId(port: PortDef): string {
  return port.id;
}

/** Find a node by id. */
export function findNode(ir: WorkflowIR, nodeId: string): WorkflowNode | undefined {
  return ir.nodes.find((n) => n.id === nodeId);
}

/** Find an edge by id. */
export function findEdge(ir: WorkflowIR, edgeId: string): WorkflowEdge | undefined {
  return ir.edges.find((e) => e.id === edgeId);
}

export function isExecutionMode(value: unknown): value is ExecutionMode {
  return typeof value === 'string' && (EXECUTION_MODES as readonly string[]).includes(value);
}
