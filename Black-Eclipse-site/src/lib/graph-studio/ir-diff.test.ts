import { describe, expect, it } from 'vitest';
import { createWorkflowIR } from './ir';
import { diffWorkflowIr } from './ir-diff';

function graph(config: Record<string, unknown> = {}, extra = false) {
  return createWorkflowIR({
    name: 'Daily scan',
    nodes: [
      { id: 'trig', type: 'trigger.manual', version: '1.0.0', config: {}, layout: { x: 0, y: 0 } },
      { id: 'calc', type: 'transform.formula', version: '1.0.0', config, layout: { x: 100, y: 0 } },
      ...(extra
        ? [{ id: 'out2', type: 'output.result', version: '1.0.0', config: {}, layout: { x: 200, y: 0 } }]
        : []),
      { id: 'out', type: 'output.result', version: '1.0.0', config: {}, layout: { x: 200, y: 100 } },
    ],
    edges: [
      { id: 'e1', source: 'trig', sourceHandle: 'start', target: 'calc', targetHandle: 'values' },
      { id: 'e2', source: 'calc', sourceHandle: 'result', target: 'out', targetHandle: 'value' },
    ],
  });
}

describe('structural IR diff', () => {
  it('reports identical graphs as identical', () => {
    const result = diffWorkflowIr(graph({ expression: 'a + b' }), graph({ expression: 'a + b' }));
    expect(result.identical).toBe(true);
    expect(result.nodes).toEqual([]);
    expect(result.edges).toEqual([]);
    expect(result.settings).toEqual([]);
  });

  it('names changed node fields and ignores key order', () => {
    const before = graph({ expression: 'a + b', decimals: 2 });
    const after = graph({ decimals: 2, expression: 'a * b' });
    const result = diffWorkflowIr(before, after);
    expect(result.identical).toBe(false);
    expect(result.nodes).toHaveLength(1);
    expect(result.nodes[0]).toMatchObject({ nodeId: 'calc', kind: 'changed', fields: ['config'] });
  });

  it('reports added and removed nodes and edges', () => {
    const result = diffWorkflowIr(graph(), graph({}, true));
    expect(result.summary.addedNodes).toBe(1);
    expect(result.nodes.find((node) => node.nodeId === 'out2')?.kind).toBe('added');
    expect(result.identical).toBe(false);

    const reversed = diffWorkflowIr(graph({}, true), graph());
    expect(reversed.summary.removedNodes).toBe(1);
  });

  it('reports settings and name changes', () => {
    const before = graph();
    const after = graph();
    after.name = 'Nightly scan';
    after.settings.executionMode = 'paper';
    const result = diffWorkflowIr(before, after);
    expect(result.nameChanged).toBe(true);
    expect(result.beforeName).toBe('Daily scan');
    expect(result.afterName).toBe('Nightly scan');
    expect(result.settings).toEqual(['executionMode']);
  });

  it('reports a changed edge endpoint', () => {
    const before = graph();
    const after = graph();
    after.edges[1] = { ...after.edges[1], targetHandle: 'other' };
    const result = diffWorkflowIr(before, after);
    expect(result.edges).toEqual([
      expect.objectContaining({ edgeId: 'e2', kind: 'changed', fields: ['targetHandle'] }),
    ]);
  });
});
