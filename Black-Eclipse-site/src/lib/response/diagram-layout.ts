// ── Diagram layout (pure) ─────────────────────────────────────────────────────
//
// A small, deterministic layered layout (a Sugiyama-lite) for flow / dependency
// / state diagrams. It is intentionally dependency-free and side-effect-free so
// it can be unit-tested and rendered to SVG by `diagram-block.tsx`.
//
// It lays out the graph the producer declared. It NEVER invents nodes or edges;
// edges that reference unknown nodes are dropped and reported as a diagnostic.

import type { DiagramBlock, DiagramEdge, DiagramNode } from './contract';

export interface LaidOutNode {
  id: string;
  label: string;
  tone: DiagramNode['tone'];
  x: number;
  y: number;
  width: number;
  height: number;
  layer: number;
}

export interface LaidOutEdge {
  from: string;
  to: string;
  label?: string;
  tone: DiagramEdge['tone'];
  dashed?: boolean;
  path: string;
  labelX: number;
  labelY: number;
}

export interface DiagramLayout {
  nodes: LaidOutNode[];
  edges: LaidOutEdge[];
  width: number;
  height: number;
  diagnostics: string[];
}

const NODE_HEIGHT = 40;
const NODE_MIN_WIDTH = 88;
const H_GAP = 26;
const V_GAP = 62;
const PADDING = 16;

function measure(label: string): number {
  return Math.max(NODE_MIN_WIDTH, Math.min(240, label.length * 7.6 + 28));
}

/**
 * Assign each node a layer (axis index) using Kahn's topological order, so
 * dependencies flow left-to-right / top-to-bottom. Nodes left over after the
 * topological pass (i.e. in a cycle) are placed in the next layer and flagged.
 */
function assignLayers(nodes: DiagramNode[], edges: DiagramEdge[]): { layer: Map<string, number>; diagnostics: string[] } {
  const diagnostics: string[] = [];
  const ids = new Set(nodes.map((n) => n.id));
  const validEdges = edges.filter((e) => ids.has(e.from) && ids.has(e.to));

  const indegree = new Map<string, number>();
  const adj = new Map<string, string[]>();
  for (const n of nodes) {
    indegree.set(n.id, 0);
    adj.set(n.id, []);
  }
  for (const e of validEdges) {
    adj.get(e.from)!.push(e.to);
    indegree.set(e.to, (indegree.get(e.to) ?? 0) + 1);
  }

  const layer = new Map<string, number>();
  const queue = nodes.filter((n) => (indegree.get(n.id) ?? 0) === 0).map((n) => n.id);
  for (const id of queue) layer.set(id, 0);

  const remaining = new Set(nodes.map((n) => n.id));
  const head = [...queue];
  while (head.length) {
    const id = head.shift()!;
    remaining.delete(id);
    const base = layer.get(id) ?? 0;
    for (const next of adj.get(id) ?? []) {
      layer.set(next, Math.max(layer.get(next) ?? 0, base + 1));
      indegree.set(next, (indegree.get(next) ?? 0) - 1);
      if ((indegree.get(next) ?? 0) === 0) head.push(next);
    }
  }

  // Cyclic remainder: give each a layer after its deepest already-placed parent.
  if (remaining.size > 0) {
    diagnostics.push(`${remaining.size} node(s) participate in a cycle; laid out in edge order.`);
    let cursor = Math.max(0, ...layer.values()) + 1;
    for (const n of nodes) {
      if (remaining.has(n.id)) {
        layer.set(n.id, cursor);
        cursor += 1;
      }
    }
  }
  return { layer, diagnostics };
}

export function layoutDiagram(block: DiagramBlock): DiagramLayout {
  const { nodes, edges, direction } = block;
  const { layer, diagnostics } = assignLayers(nodes, edges);

  // Group nodes by layer, preserving declaration order within a layer.
  const byLayer = new Map<number, DiagramNode[]>();
  for (const n of nodes) {
    const l = layer.get(n.id) ?? 0;
    const bucket = byLayer.get(l) ?? [];
    bucket.push(n);
    byLayer.set(l, bucket);
  }
  const layers = [...byLayer.keys()].sort((a, b) => a - b);
  const isHorizontal = direction === 'LR';

  const laid: LaidOutNode[] = [];
  // Track the cross-axis extent per layer to centre shorter layers.
  const layerExtent = layers.map((l) => {
    const bucket = byLayer.get(l)!;
    const widths = bucket.map((n) => measure(n.label));
    return isHorizontal
      ? bucket.length * NODE_HEIGHT + Math.max(0, bucket.length - 1) * H_GAP
      : widths.reduce((a, b) => a + b, 0) + Math.max(0, widths.length - 1) * H_GAP;
  });
  const mainExtent = Math.max(...layerExtent, 0);

  layers.forEach((l, li) => {
    const bucket = byLayer.get(l)!;
    let cursor = PADDING + (mainExtent - layerExtent[li]) / 2;
    for (const n of bucket) {
      const width = measure(n.label);
      if (isHorizontal) {
        laid.push({ id: n.id, label: n.label, tone: n.tone, x: PADDING + li * 200, y: cursor, width, height: NODE_HEIGHT, layer: l });
        cursor += NODE_HEIGHT + H_GAP;
      } else {
        laid.push({ id: n.id, label: n.label, tone: n.tone, x: cursor, y: PADDING + li * (NODE_HEIGHT + V_GAP), width, height: NODE_HEIGHT, layer: l });
        cursor += width + H_GAP;
      }
    }
  });

  const byId = new Map(laid.map((n) => [n.id, n]));
  const laidEdges: LaidOutEdge[] = [];
  for (const e of edges) {
    const from = byId.get(e.from);
    const to = byId.get(e.to);
    if (!from || !to) {
      diagnostics.push(`Edge ${e.from} → ${e.to} references an unknown node and was omitted.`);
      continue;
    }
    const { path, labelX, labelY } = edgePath(from, to, isHorizontal);
    laidEdges.push({ from: e.from, to: e.to, label: e.label, tone: e.tone, dashed: e.dashed, path, labelX, labelY });
  }

  const width = Math.max(...laid.map((n) => n.x + n.width), 0) + PADDING;
  const height = Math.max(...laid.map((n) => n.y + n.height), 0) + PADDING;

  return { nodes: laid, edges: laidEdges, width, height, diagnostics };
}

function edgePath(from: LaidOutNode, to: LaidOutNode, horizontal: boolean): { path: string; labelX: number; labelY: number } {
  if (horizontal) {
    const x1 = from.x + from.width;
    const y1 = from.y + from.height / 2;
    const x2 = to.x;
    const y2 = to.y + to.height / 2;
    const mid = (x1 + x2) / 2;
    return { path: `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`, labelX: mid, labelY: (y1 + y2) / 2 - 4 };
  }
  const x1 = from.x + from.width / 2;
  const y1 = from.y + from.height;
  const x2 = to.x + to.width / 2;
  const y2 = to.y;
  const mid = (y1 + y2) / 2;
  return { path: `M ${x1} ${y1} C ${x1} ${mid}, ${x2} ${mid}, ${x2} ${y2}`, labelX: (x1 + x2) / 2 + 6, labelY: mid };
}
