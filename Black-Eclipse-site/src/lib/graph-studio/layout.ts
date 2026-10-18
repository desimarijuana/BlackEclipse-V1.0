// ── Deterministic auto-layout ─────────────────────────────────────────────────
// A small layered ("Sugiyama-lite") layout, dependency-free on purpose: pulling
// in a full layout engine (elkjs) would add megabytes for a need this covers.
// Nodes are assigned to layers by their longest path from a source; each layer
// is then stacked vertically. Position is NON-SEMANTIC — this only produces the
// initial coordinates a newly-generated or imported graph is drawn at.

import type { NodePosition, WorkflowIR } from './types';

export interface LayoutOptions {
  xGap?: number;
  yGap?: number;
  originX?: number;
  originY?: number;
}

export function autoLayout(ir: WorkflowIR, options: LayoutOptions = {}): Record<string, NodePosition> {
  const xGap = options.xGap ?? 300;
  const yGap = options.yGap ?? 140;
  const originX = options.originX ?? 80;
  const originY = options.originY ?? 80;

  const indegree = new Map<string, number>();
  const adj = new Map<string, string[]>();
  for (const node of ir.nodes) {
    indegree.set(node.id, 0);
    adj.set(node.id, []);
  }
  for (const edge of ir.edges) {
    if (!adj.has(edge.source) || !indegree.has(edge.target)) continue;
    adj.get(edge.source)?.push(edge.target);
    indegree.set(edge.target, (indegree.get(edge.target) ?? 0) + 1);
  }

  // Longest-path layer via Kahn topological order.
  const layer = new Map<string, number>();
  const queue: string[] = [];
  for (const [id, deg] of indegree) {
    if (deg === 0) {
      layer.set(id, 0);
      queue.push(id);
    }
  }
  const remaining = new Map(indegree);
  while (queue.length) {
    const id = queue.shift() as string;
    for (const next of adj.get(id) ?? []) {
      const candidate = (layer.get(id) ?? 0) + 1;
      layer.set(next, Math.max(layer.get(next) ?? 0, candidate));
      const deg = (remaining.get(next) ?? 0) - 1;
      remaining.set(next, deg);
      if (deg === 0) queue.push(next);
    }
  }
  // Any nodes left (in a cycle — invalid, but don't crash) get their own layer.
  for (const node of ir.nodes) {
    if (!layer.has(node.id)) layer.set(node.id, 0);
  }

  // Group by layer, order stably by id for reproducibility.
  const layers = new Map<number, string[]>();
  for (const [id, l] of layer) {
    (layers.get(l) ?? layers.set(l, []).get(l)!).push(id);
  }
  const positions: Record<string, NodePosition> = {};
  for (const [l, ids] of [...layers.entries()].sort((a, b) => a[0] - b[0])) {
    ids.sort();
    ids.forEach((id, index) => {
      positions[id] = { x: originX + l * xGap, y: originY + index * yGap };
    });
  }
  return positions;
}
