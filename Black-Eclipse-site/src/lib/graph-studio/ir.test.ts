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

  it('produces a stable content hash regardless of key order', () => {
    expect(canonicalStringify({ b: 1, a: 2 })).toBe(canonicalStringify({ a: 2, b: 1 }));
    expect(contentHash({ a: 1, b: 2 })).toBe(contentHash({ b: 2, a: 1 }));
    expect(contentHash({ a: 1 })).not.toBe(contentHash({ a: 2 }));
  });
});
