import { describe, it, expect } from 'vitest';
import { layoutDiagram } from './diagram-layout';
import { validateBlock, type DiagramBlock } from './contract';

function diagram(raw: unknown): DiagramBlock {
  const { block } = validateBlock(raw);
  if (block.type !== 'diagram') throw new Error('expected diagram block');
  return block;
}

describe('layoutDiagram', () => {
  it('orders a chain into increasing layers top-to-bottom', () => {
    const layout = layoutDiagram(
      diagram({
        type: 'diagram',
        nodes: [{ id: 'a', label: 'A' }, { id: 'b', label: 'B' }, { id: 'c', label: 'C' }],
        edges: [{ from: 'a', to: 'b' }, { from: 'b', to: 'c' }],
      }),
    );
    const byId = Object.fromEntries(layout.nodes.map((n) => [n.id, n]));
    expect(byId.a.layer).toBe(0);
    expect(byId.b.layer).toBe(1);
    expect(byId.c.layer).toBe(2);
    expect(byId.b.y).toBeGreaterThan(byId.a.y);
    expect(layout.edges).toHaveLength(2);
    expect(layout.width).toBeGreaterThan(0);
  });

  it('drops edges that reference unknown nodes and reports a diagnostic', () => {
    const layout = layoutDiagram(
      diagram({ type: 'diagram', nodes: [{ id: 'a', label: 'A' }], edges: [{ from: 'a', to: 'ghost' }] }),
    );
    expect(layout.edges).toHaveLength(0);
    expect(layout.diagnostics.length).toBeGreaterThan(0);
  });

  it('does not throw on a cyclic graph', () => {
    const layout = layoutDiagram(
      diagram({
        type: 'diagram',
        nodes: [{ id: 'a', label: 'A' }, { id: 'b', label: 'B' }],
        edges: [{ from: 'a', to: 'b' }, { from: 'b', to: 'a' }],
      }),
    );
    expect(layout.nodes).toHaveLength(2);
    expect(layout.diagnostics.some((d) => d.includes('cycle'))).toBe(true);
  });
});
