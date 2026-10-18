import { describe, expect, it } from 'vitest';
import { applyPatch, applyPatches, canConnect, type Patch } from './patches';
import { createWorkflowIR } from './ir';
import { getNodeDefinition } from './registry';
import { buildTemplate } from './templates';
import type { WorkflowIR } from './types';

function addNode(ir: WorkflowIR, type: string, id: string): Patch {
  const def = getNodeDefinition(type)!;
  return { op: 'add_node', node: { id, type, version: def.version, config: def.defaultConfig(), layout: { x: 0, y: 0 } } };
}

describe('graph patches', () => {
  it('adds and removes a node, dropping incident edges on removal', () => {
    const ir = buildTemplate('blank')!;
    const withNode = applyPatch(ir, addNode(ir, 'logic.merge', 'm'));
    expect(withNode.ok).toBe(true);
    if (!withNode.ok) return;
    const removed = applyPatch(withNode.ir, { op: 'remove_node', nodeId: 'trigger' });
    expect(removed.ok).toBe(true);
    if (!removed.ok) return;
    expect(removed.ir.nodes.find((n) => n.id === 'trigger')).toBeUndefined();
    expect(removed.ir.edges.length).toBe(0);
  });

  it('rejects a duplicate node id', () => {
    const ir = buildTemplate('blank')!;
    const result = applyPatch(ir, addNode(ir, 'logic.merge', 'trigger'));
    expect(result.ok).toBe(false);
  });

  it('rejects an edge that would create a cycle', () => {
    const base = createWorkflowIR();
    let ir = base;
    for (const [type, id] of [['trigger.manual', 'a'], ['logic.merge', 'b'], ['logic.merge', 'c']] as const) {
      const r = applyPatch(ir, addNode(ir, type, id));
      if (r.ok) ir = r.ir;
    }
    const forward = applyPatch(ir, { op: 'add_edge', edge: { source: 'a', sourceHandle: 'start', target: 'b', targetHandle: 'a' } });
    expect(forward.ok).toBe(true);
    if (!forward.ok) return;
    const loop = applyPatch(forward.ir, { op: 'add_edge', edge: { source: 'b', sourceHandle: 'value', target: 'a', targetHandle: 'nope' } });
    expect(loop.ok).toBe(false);
  });

  it('canConnect rejects incompatible port types', () => {
    const base = createWorkflowIR();
    let ir: WorkflowIR = {
      ...base,
      nodes: [
        { id: 'trig', type: 'trigger.manual', version: '1.0.0', config: {}, layout: { x: 0, y: 0 } },
        { id: 'http', type: 'integration.http', version: '1.0.0', config: { url: '', method: 'GET' }, layout: { x: 0, y: 0 } },
      ],
    };
    // http.status (number) → trigger has no inputs; use parse.json text (string):
    const r = applyPatch(ir, addNode(ir, 'data.json.parse', 'parse'));
    expect(r.ok).toBe(true);
    if (r.ok) ir = r.ir;
    expect(canConnect(ir, 'http', 'status', 'parse', 'text').ok).toBe(false);
    expect(canConnect(ir, 'trig', 'start', 'parse', 'text').ok).toBe(true);
  });

  it('applyPatches stops at the first rejection', () => {
    const ir = buildTemplate('blank')!;
    const result = applyPatches(ir, [addNode(ir, 'logic.merge', 'm'), addNode(ir, 'logic.merge', 'm')]);
    expect(result.ok).toBe(false);
  });

  it('recomputes capabilities after a structural patch', () => {
    const ir = buildTemplate('blank')!;
    const result = applyPatch(ir, addNode(ir, 'finance.market_data', 'mkt'));
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.ir.requiredCapabilities).toContain('market.read');
  });

  it('move_node does not change semantics', () => {
    const ir = buildTemplate('blank')!;
    const result = applyPatch(ir, { op: 'move_node', nodeId: 'trigger', position: { x: 42, y: 99 } });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.ir.nodes.find((n) => n.id === 'trigger')?.layout).toEqual({ x: 42, y: 99 });
      expect(result.ir.meta.updatedAt).toBe(ir.meta.updatedAt);
    }
  });
});
