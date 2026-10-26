import { describe, expect, it } from 'vitest';
import { applyPatches } from './patches';
import {
  buildAppendToPort, buildClipboard, buildDuplicateNodes, buildInsertOnEdge, buildPaste,
  canAppendToPort, canInsertOnEdge,
} from './edit-ops';
import { buildTemplate } from './templates';

describe('graph edit operations', () => {
  it('inserts a compatible node into an edge and rewires both sides', () => {
    const ir = buildTemplate('blank')!;
    const edge = ir.edges[0];
    expect(canInsertOnEdge(ir, edge, 'logic.merge')).toBe(true);
    const result = buildInsertOnEdge(ir, edge.id, 'logic.merge');
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    const applied = applyPatches(ir, result.patches);
    expect(applied.ok).toBe(true);
    if (!applied.ok) return;
    expect(applied.ir.nodes).toHaveLength(3);
    expect(applied.ir.edges).toHaveLength(2);
    expect(applied.ir.edges.some((item) => item.target === result.nodeId)).toBe(true);
    expect(applied.ir.edges.some((item) => item.source === result.nodeId)).toBe(true);
  });

  it('refuses an incompatible insertion', () => {
    const ir = buildTemplate('blank')!;
    expect(canInsertOnEdge(ir, ir.edges[0], 'output.result')).toBe(false);
    const result = buildInsertOnEdge(ir, ir.edges[0].id, 'output.result');
    expect(result.ok).toBe(false);
  });

  it('appends a node to an output port', () => {
    const ir = buildTemplate('blank')!;
    expect(canAppendToPort(ir, 'trigger', 'start', 'logic.merge')).toBe(true);
    const result = buildAppendToPort(ir, 'trigger', 'start', 'logic.merge');
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    const applied = applyPatches(ir, result.patches);
    expect(applied.ok).toBe(true);
    if (!applied.ok) return;
    expect(applied.ir.nodes).toHaveLength(3);
    expect(applied.ir.edges).toHaveLength(2);
  });

  it('duplicates selected nodes and the edges between them', () => {
    const ir = buildTemplate('blank')!;
    const result = buildDuplicateNodes(ir, ir.nodes.map((node) => node.id));
    expect(result.nodeIds).toHaveLength(2);
    const applied = applyPatches(ir, result.patches);
    expect(applied.ok).toBe(true);
    if (!applied.ok) return;
    expect(applied.ir.nodes).toHaveLength(4);
    expect(applied.ir.edges).toHaveLength(2);
    const positions = new Set(applied.ir.nodes.map((node) => `${node.layout.x},${node.layout.y}`));
    expect(positions.size).toBe(4);
  });

  it('copies and pastes a selection with fresh ids', () => {
    const ir = buildTemplate('blank')!;
    const clipboard = buildClipboard(ir, ir.nodes.map((node) => node.id));
    const pasted = buildPaste(ir, clipboard);
    expect(pasted.nodeIds).toHaveLength(2);
    const applied = applyPatches(ir, pasted.patches);
    expect(applied.ok).toBe(true);
    if (!applied.ok) return;
    expect(applied.ir.nodes).toHaveLength(4);
    for (const id of pasted.nodeIds) {
      expect(ir.nodes.some((node) => node.id === id)).toBe(false);
    }
  });
});
