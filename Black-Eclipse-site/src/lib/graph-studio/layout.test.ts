import { describe, expect, it } from 'vitest';
import { autoLayout } from './layout';
import type { WorkflowIR, WorkflowNode } from './types';

function node(id: string): WorkflowNode {
  return { id, type: 'transform.set', version: '1', config: {}, layout: { x: 0, y: 0 } };
}

function graph(nodes: WorkflowNode[], edges: WorkflowIR['edges'] = []): WorkflowIR {
  return {
    irVersion: 2,
    id: 'test',
    name: 'test',
    description: '',
    meta: { createdAt: '', updatedAt: '', tags: [] },
    nodes,
    edges,
    settings: { executionMode: 'research', failFast: true, maxConcurrency: 4, timeoutMs: 0 },
    requiredCapabilities: [],
  };
}

describe('autoLayout', () => {
  it('stacks a layer by the measured node heights so cards never overlap', () => {
    const ir = graph([node('a'), node('b'), node('c')]);
    const positions = autoLayout(ir, { heights: { a: 200, b: 320, c: 150 } });

    expect(positions.a).toEqual({ x: 80, y: 80 });
    expect(positions.b).toEqual({ x: 80, y: 80 + 200 + 48 });
    expect(positions.c).toEqual({ x: 80, y: 80 + 200 + 48 + 320 + 48 });
    expect(positions.b.y - positions.a.y).toBeGreaterThanOrEqual(200);
    expect(positions.c.y - positions.b.y).toBeGreaterThanOrEqual(320);
  });

  it('spaces layers by the node width plus the horizontal gap', () => {
    const ir = graph(
      [node('a'), node('b')],
      [{ id: 'e', source: 'a', sourceHandle: 'out', target: 'b', targetHandle: 'in' }],
    );
    const positions = autoLayout(ir);
    expect(positions.b.x - positions.a.x).toBe(280 + 96);
  });

  it('falls back to a safe height when a node has not been measured yet', () => {
    const ir = graph([node('a'), node('b')]);
    const positions = autoLayout(ir);
    expect(positions.b.y - positions.a.y).toBe(240 + 48);
  });
});
