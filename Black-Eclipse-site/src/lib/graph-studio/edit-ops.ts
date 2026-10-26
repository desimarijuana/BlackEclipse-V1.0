// ── High-level editor operations ──────────────────────────────────────────────
// The canvas needs a few compound edits (split an edge with a new node, duplicate
// a selection, copy/paste) that are more than one PATCH. They are still expressed
// as ordinary patches and applied through `applyPatches`, so validation, undo and
// the "one chokepoint" rule are preserved. This module is pure (no React, no
// store) so it can be unit-tested directly.

import type { NodePosition, PortDef, WorkflowEdge, WorkflowIR, WorkflowNode } from './types';
import type { Patch } from './patches';
import { getNodeDefinition } from './registry';
import { portsCompatible } from './validation';

export interface EditClipboard {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function uniqueNodeId(used: Set<string>, prefix = 'n'): string {
  for (;;) {
    const id = `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
    if (!used.has(id)) {
      used.add(id);
      return id;
    }
  }
}

export function newNodeId(ir: WorkflowIR, prefix = 'n'): string {
  return uniqueNodeId(new Set(ir.nodes.map((node) => node.id)), prefix);
}

export function newEdgeId(ir: WorkflowIR, extraIds: Iterable<string> = []): string {
  const taken = new Set([...ir.edges.map((edge) => edge.id), ...extraIds]);
  for (;;) {
    const id = `e_${Math.random().toString(36).slice(2, 10)}`;
    if (!taken.has(id)) {
      taken.add(id);
      return id;
    }
  }
}

function midpoint(a: NodePosition, b: NodePosition): NodePosition {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

function outputPort(ir: WorkflowIR, nodeId: string, handle: string): PortDef | undefined {
  const node = ir.nodes.find((n) => n.id === nodeId);
  if (!node) return undefined;
  return getNodeDefinition(node.type, node.version)?.outputs.find((port) => port.id === handle);
}

function inputPort(ir: WorkflowIR, nodeId: string, handle: string): PortDef | undefined {
  const node = ir.nodes.find((n) => n.id === nodeId);
  if (!node) return undefined;
  return getNodeDefinition(node.type, node.version)?.inputs.find((port) => port.id === handle);
}

/** Can a node of `type` sit in the middle of this edge with both sides wired? */
export function canInsertOnEdge(ir: WorkflowIR, edge: WorkflowEdge, type: string, version?: string): boolean {
  const def = getNodeDefinition(type, version);
  if (!def) return false;
  const from = outputPort(ir, edge.source, edge.sourceHandle);
  const to = inputPort(ir, edge.target, edge.targetHandle);
  if (!from || !to) return false;
  return (
    def.inputs.some((port) => portsCompatible(from, port)) &&
    def.outputs.some((port) => portsCompatible(port, to))
  );
}

/** Can a node of `type` be appended to this output port? */
export function canAppendToPort(ir: WorkflowIR, nodeId: string, handle: string, type: string, version?: string): boolean {
  const from = outputPort(ir, nodeId, handle);
  const def = getNodeDefinition(type, version);
  if (!from || !def) return false;
  return def.inputs.some((port) => portsCompatible(from, port));
}

/**
 * Split one edge with a new node: remove the old edge, add the node at the
 * edge midpoint and wire source → node → target on the first compatible ports.
 */
export function buildInsertOnEdge(
  ir: WorkflowIR,
  edgeId: string,
  type: string,
  version?: string,
  layout?: NodePosition,
): { ok: true; patches: Patch[]; nodeId: string } | { ok: false; error: string } {
  const edge = ir.edges.find((item) => item.id === edgeId);
  if (!edge) return { ok: false, error: `Edge "${edgeId}" not found.` };
  const def = getNodeDefinition(type, version);
  if (!def) return { ok: false, error: `Unknown node type ${type}.` };
  const from = outputPort(ir, edge.source, edge.sourceHandle);
  const to = inputPort(ir, edge.target, edge.targetHandle);
  if (!from || !to) return { ok: false, error: 'The edge has an unknown port.' };
  const inPort = def.inputs.find((port) => portsCompatible(from, port));
  const outPort = def.outputs.find((port) => portsCompatible(port, to));
  if (!inPort || !outPort) return { ok: false, error: `${def.label} cannot be inserted on this connection.` };

  const sourceNode = ir.nodes.find((node) => node.id === edge.source);
  const targetNode = ir.nodes.find((node) => node.id === edge.target);
  const position = layout ?? midpoint(sourceNode?.layout ?? { x: 0, y: 0 }, targetNode?.layout ?? { x: 0, y: 0 });
  const nodeId = newNodeId(ir);
  const patches: Patch[] = [
    { op: 'remove_edge', edgeId },
    {
      op: 'add_node',
      node: { id: nodeId, type: def.type, version: def.version, config: def.defaultConfig(), layout: position },
    },
    {
      op: 'add_edge',
      edge: { source: edge.source, sourceHandle: edge.sourceHandle, target: nodeId, targetHandle: inPort.id },
    },
    {
      op: 'add_edge',
      edge: { source: nodeId, sourceHandle: outPort.id, target: edge.target, targetHandle: edge.targetHandle },
    },
  ];
  return { ok: true, patches, nodeId };
}

/** Append a node to one output port, placing it to the right of its source. */
export function buildAppendToPort(
  ir: WorkflowIR,
  nodeId: string,
  handle: string,
  type: string,
  version?: string,
): { ok: true; patches: Patch[]; nodeId: string } | { ok: false; error: string } {
  const source = ir.nodes.find((node) => node.id === nodeId);
  const from = outputPort(ir, nodeId, handle);
  const def = getNodeDefinition(type, version);
  if (!source || !from || !def) return { ok: false, error: 'Cannot append to this output.' };
  const inPort = def.inputs.find((port) => portsCompatible(from, port));
  if (!inPort) return { ok: false, error: `${def.label} has no compatible input.` };
  const newId = newNodeId(ir);
  const patches: Patch[] = [
    {
      op: 'add_node',
      node: {
        id: newId,
        type: def.type,
        version: def.version,
        config: def.defaultConfig(),
        layout: { x: source.layout.x + 300, y: source.layout.y },
      },
    },
    {
      op: 'add_edge',
      edge: { source: nodeId, sourceHandle: handle, target: newId, targetHandle: inPort.id },
    },
  ];
  return { ok: true, patches, nodeId: newId };
}

/**
 * Duplicate selected nodes and the edges that connect two selected nodes.
 * New nodes are offset so they are visible (and never sit exactly on top).
 */
export function buildDuplicateNodes(
  ir: WorkflowIR,
  nodeIds: string[],
  offset: NodePosition = { x: 40, y: 40 },
): { patches: Patch[]; nodeIds: string[] } {
  const selected = new Set(nodeIds.filter((id) => ir.nodes.some((node) => node.id === id)));
  if (selected.size === 0) return { patches: [], nodeIds: [] };

  const idMap = new Map<string, string>();
  const used = new Set(ir.nodes.map((node) => node.id));
  for (const oldId of selected) {
    idMap.set(oldId, uniqueNodeId(used));
  }

  const patches: Patch[] = [];
  for (const node of ir.nodes) {
    const id = idMap.get(node.id);
    if (!id) continue;
    patches.push({
      op: 'add_node',
      node: {
        id,
        type: node.type,
        version: node.version,
        label: node.label,
        config: clone(node.config),
        layout: { x: node.layout.x + offset.x, y: node.layout.y + offset.y },
      },
    });
  }

  const createdEdges = new Set<string>();
  for (const edge of ir.edges) {
    const source = idMap.get(edge.source);
    const target = idMap.get(edge.target);
    if (!source || !target) continue;
    const id = newEdgeId(ir, createdEdges);
    createdEdges.add(id);
    patches.push({
      op: 'add_edge',
      edge: { id, source, sourceHandle: edge.sourceHandle, target, targetHandle: edge.targetHandle },
    });
  }

  return { patches, nodeIds: [...idMap.values()] };
}

export function buildClipboard(ir: WorkflowIR, nodeIds: string[]): EditClipboard {
  const selected = new Set(nodeIds);
  const nodes = ir.nodes.filter((node) => selected.has(node.id)).map((node) => clone(node));
  const edges = ir.edges
    .filter((edge) => selected.has(edge.source) && selected.has(edge.target))
    .map((edge) => clone(edge));
  return { nodes, edges };
}

/** Paste a previously copied payload with fresh ids, offset from the originals. */
export function buildPaste(
  ir: WorkflowIR,
  payload: EditClipboard | null,
  offset: NodePosition = { x: 56, y: 56 },
): { patches: Patch[]; nodeIds: string[] } {
  if (!payload || payload.nodes.length === 0) return { patches: [], nodeIds: [] };

  const idMap = new Map<string, string>();
  const used = new Set(ir.nodes.map((node) => node.id));
  for (const node of payload.nodes) {
    idMap.set(node.id, uniqueNodeId(used));
  }

  const patches: Patch[] = [];
  for (const node of payload.nodes) {
    const id = idMap.get(node.id);
    if (!id) continue;
    patches.push({
      op: 'add_node',
      node: {
        id,
        type: node.type,
        version: node.version,
        label: node.label,
        config: clone(node.config),
        layout: { x: node.layout.x + offset.x, y: node.layout.y + offset.y },
      },
    });
  }

  const createdEdges = new Set<string>();
  for (const edge of payload.edges) {
    const source = idMap.get(edge.source);
    const target = idMap.get(edge.target);
    if (!source || !target) continue;
    const id = newEdgeId(ir, createdEdges);
    createdEdges.add(id);
    patches.push({
      op: 'add_edge',
      edge: { id, source, sourceHandle: edge.sourceHandle, target, targetHandle: edge.targetHandle },
    });
  }

  return { patches, nodeIds: [...idMap.values()] };
}

export { midpoint };
