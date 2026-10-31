import { describe, expect, it } from 'vitest';
import { createWorkflowIR, parseWorkflowIR, WorkflowIRError } from './ir';
import { migrateWorkflowIR, readWorkflowIR } from './migrations';
import { WORKFLOW_IR_VERSION } from './types';
import { contentHash, canonicalStringify } from './hash';

describe('workflow IR', () => {
  it('creates a fresh document at the current IR version', () => {
    const ir = createWorkflowIR({ name: 'Test' });
    expect(ir.irVersion).toBe(WORKFLOW_IR_VERSION);
    expect(ir.nodes).toEqual([]);
    expect(ir.settings.executionMode).toBe('research');
  });

  it('round-trips through parse', () => {
    const ir = createWorkflowIR({ name: 'Round trip' });
    const parsed = parseWorkflowIR(JSON.parse(JSON.stringify(ir)));
    expect(parsed).toEqual(ir);
  });

  it('rejects a malformed document', () => {
    expect(() => parseWorkflowIR({ irVersion: 1, name: 3 })).toThrow(WorkflowIRError);
  });

  it('migrates an unversioned document to the current version', () => {
    const migrated = migrateWorkflowIR({ name: 'Legacy', nodes: [], edges: [] }) as Record<string, unknown>;
    expect(migrated.irVersion).toBe(WORKFLOW_IR_VERSION);
    expect(readWorkflowIR({ name: 'Legacy', nodes: [], edges: [], id: 'x' }).name).toBe('Legacy');
  });

  it('migrates a v1 node to v2 with an empty inputValues map', () => {
    const migrated = migrateWorkflowIR({
      irVersion: 1,
      id: 'wf',
      name: 'V1',
      nodes: [{ id: 'n', type: 'data.json.parse', version: '1.0.0', config: {}, layout: { x: 0, y: 0 } }],
      edges: [],
      settings: { executionMode: 'research', failFast: false, maxConcurrency: 1, timeoutMs: 0 },
    }) as { irVersion: number; nodes: Array<Record<string, unknown>> };
    expect(migrated.irVersion).toBe(2);
    expect(migrated.nodes[0].inputValues).toEqual({});
  });

  it('produces a stable content hash regardless of key order', () => {
    expect(canonicalStringify({ b: 1, a: 2 })).toBe(canonicalStringify({ a: 2, b: 1 }));
    expect(contentHash({ a: 1, b: 2 })).toBe(contentHash({ b: 2, a: 1 }));
    expect(contentHash({ a: 1 })).not.toBe(contentHash({ a: 2 }));
  });
});
