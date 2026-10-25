// ── Structural IR diff ───────────────────────────────────────────────────────
// Compare two immutable workflow versions without executing either one. The
// diff is deterministic (ids, then ordered fields) and reports only what changed:
// added/removed nodes and edges, changed node fields, and changed settings.

import type { WorkflowEdge, WorkflowIR, WorkflowNode } from './types';

export type NodeChangeKind = 'added' | 'removed' | 'changed';
export type EdgeChangeKind = 'added' | 'removed' | 'changed';

export interface NodeDiff {
  nodeId: string;
  kind: NodeChangeKind;
  label: string;
  fields: string[];
  before?: WorkflowNode;
  after?: WorkflowNode;
}

export interface EdgeDiff {
  edgeId: string;
  kind: EdgeChangeKind;
  fields: string[];
  before?: WorkflowEdge;
  after?: WorkflowEdge;
}

export interface IrDiff {
  identical: boolean;
  nameChanged: boolean;
  beforeName: string;
  afterName: string;
  nodes: NodeDiff[];
  edges: EdgeDiff[];
  settings: string[];
  summary: {
    addedNodes: number;
    removedNodes: number;
    changedNodes: number;
    addedEdges: number;
    removedEdges: number;
    changedEdges: number;
  };
}

function stable(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stable).join(',')}]`;
  const entries = Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b));
  return `{${entries.map(([key, item]) => `${JSON.stringify(key)}:${stable(item)}`).join(',')}}`;
}

function nodeFields(before: WorkflowNode, after: WorkflowNode): string[] {
  const fields: string[] = [];
  if (before.type !== after.type) fields.push('type');
  if (before.version !== after.version) fields.push('version');
  if ((before.label ?? '') !== (after.label ?? '')) fields.push('label');
  if (before.layout?.x !== after.layout?.x || before.layout?.y !== after.layout?.y) fields.push('position');
  if (stable(before.config ?? {}) !== stable(after.config ?? {})) fields.push('config');
  return fields;
}

function edgeFields(before: WorkflowEdge, after: WorkflowEdge): string[] {
  const fields: string[] = [];
  if (before.source !== after.source) fields.push('source');
  if (before.sourceHandle !== after.sourceHandle) fields.push('sourceHandle');
  if (before.target !== after.target) fields.push('target');
  if (before.targetHandle !== after.targetHandle) fields.push('targetHandle');
  return fields;
}

/** Compare two workflow versions structurally. */
export function diffWorkflowIr(before: WorkflowIR, after: WorkflowIR): IrDiff {
  const beforeNodes = new Map(before.nodes.map((node) => [node.id, node]));
  const afterNodes = new Map(after.nodes.map((node) => [node.id, node]));
  const nodes: NodeDiff[] = [];

  for (const id of [...beforeNodes.keys()].sort()) {
    if (!afterNodes.has(id)) {
      const old = beforeNodes.get(id)!;
      nodes.push({ nodeId: id, kind: 'removed', label: old.label ?? old.type, fields: [], before: old });
    }
  }
  for (const id of [...afterNodes.keys()].sort()) {
    const old = beforeNodes.get(id);
    const next = afterNodes.get(id)!;
    if (!old) {
      nodes.push({ nodeId: id, kind: 'added', label: next.label ?? next.type, fields: [], after: next });
      continue;
    }
    const fields = nodeFields(old, next);
    if (fields.length > 0) {
      nodes.push({ nodeId: id, kind: 'changed', label: next.label ?? next.type, fields, before: old, after: next });
    }
  }

  const beforeEdges = new Map(before.edges.map((edge) => [edge.id, edge]));
  const afterEdges = new Map(after.edges.map((edge) => [edge.id, edge]));
  const edges: EdgeDiff[] = [];
  for (const id of [...beforeEdges.keys()].sort()) {
    if (!afterEdges.has(id)) {
      edges.push({ edgeId: id, kind: 'removed', fields: [], before: beforeEdges.get(id) });
    }
  }
  for (const id of [...afterEdges.keys()].sort()) {
    const old = beforeEdges.get(id);
    const next = afterEdges.get(id)!;
    if (!old) {
      edges.push({ edgeId: id, kind: 'added', fields: [], after: next });
      continue;
    }
    const fields = edgeFields(old, next);
    if (fields.length > 0) edges.push({ edgeId: id, kind: 'changed', fields, before: old, after: next });
  }

  const beforeSettings = (before.settings ?? {}) as unknown as Record<string, unknown>;
  const afterSettings = (after.settings ?? {}) as unknown as Record<string, unknown>;
  const settings = [...new Set([...Object.keys(beforeSettings), ...Object.keys(afterSettings)])]
    .sort()
    .filter((key) => stable(beforeSettings[key]) !== stable(afterSettings[key]));

  const summary = {
    addedNodes: nodes.filter((item) => item.kind === 'added').length,
    removedNodes: nodes.filter((item) => item.kind === 'removed').length,
    changedNodes: nodes.filter((item) => item.kind === 'changed').length,
    addedEdges: edges.filter((item) => item.kind === 'added').length,
    removedEdges: edges.filter((item) => item.kind === 'removed').length,
    changedEdges: edges.filter((item) => item.kind === 'changed').length,
  };

  return {
    identical:
      before.name === after.name &&
      nodes.length === 0 && edges.length === 0 && settings.length === 0,
    nameChanged: before.name !== after.name,
    beforeName: before.name,
    afterName: after.name,
    nodes,
    edges,
    settings,
    summary,
  };
}
