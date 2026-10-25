import { describe, expect, it } from 'vitest';
import { createWorkflowIR } from './ir';
import { collectSubworkflows, subworkflowRefs, type SubworkflowLoader } from './subworkflow-bundle';
import type { WorkflowIR } from './types';

function graph(id: string, child?: { id: string; version: number }): WorkflowIR {
  const nodes = [
    { id: 'trig', type: 'trigger.manual', version: '1.0.0', config: {}, layout: { x: 0, y: 0 } },
    { id: 'out', type: 'output.result', version: '1.0.0', config: {}, layout: { x: 0, y: 0 } },
  ];
  const edges = [
    { id: 'e1', source: 'trig', sourceHandle: 'start', target: 'out', targetHandle: 'value' },
  ];
  if (child) {
    nodes.push({
      id: 'sub', type: 'flow.subworkflow', version: '1.0.0',
      config: { workflowId: child.id, version: child.version }, layout: { x: 0, y: 0 },
    });
  }
  return createWorkflowIR({ id, nodes, edges });
}

function loaderOf(map: Record<string, WorkflowIR>): SubworkflowLoader {
  return async (id, version) => map[`${id}@${version}`] ?? null;
}

describe('subworkflow bundle', () => {
  it('finds pinned references and ignores incomplete nodes', () => {
    const ir = graph('root', { id: 'child', version: 3 });
    expect(subworkflowRefs(ir)).toEqual([{ id: 'child', version: 3 }]);
    const blank = graph('root');
    blank.nodes.push({
      id: 'x', type: 'flow.subworkflow', version: '1.0.0',
      config: { workflowId: '', version: 1 }, layout: { x: 0, y: 0 },
    });
    expect(subworkflowRefs(blank)).toEqual([]);
  });

  it('resolves nested subworkflows once', async () => {
    const child = graph('child', { id: 'grandchild', version: 1 });
    const grandchild = graph('grandchild');
    const bundle = await collectSubworkflows(
      graph('root', { id: 'child', version: 2 }),
      loaderOf({ 'child@2': child, 'grandchild@1': grandchild }),
    );
    expect(bundle.map((entry) => `${entry.id}@${entry.version}`)).toEqual(['child@2', 'grandchild@1']);
  });

  it('refuses a missing subworkflow', async () => {
    await expect(collectSubworkflows(graph('root', { id: 'missing', version: 1 }), loaderOf({})))
      .rejects.toThrow('Subworkflow missing@1 was not found');
  });

  it('refuses a cycle', async () => {
    const child = graph('child', { id: 'root', version: 1 });
    await expect(collectSubworkflows(
      graph('root', { id: 'child', version: 1 }),
      loaderOf({ 'child@1': child, 'root@1': graph('root') }),
      { rootKey: 'root@1' },
    )).rejects.toThrow('Subworkflow cycle detected');
  });

  it('refuses nesting beyond the depth limit', async () => {
    const map: Record<string, WorkflowIR> = {};
    for (let i = 0; i < 7; i += 1) {
      map[`w${i}@1`] = graph(`w${i}`, i < 6 ? { id: `w${i + 1}`, version: 1 } : undefined);
    }
    await expect(collectSubworkflows(graph('root', { id: 'w0', version: 1 }), loaderOf(map)))
      .rejects.toThrow('maximum depth');
  });
});
