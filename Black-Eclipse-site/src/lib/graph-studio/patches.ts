// ── Graph patch operations ────────────────────────────────────────────────────
// Every mutation of a workflow is expressed as a PATCH. Patches are pure
// (IR in → new IR out), individually validated against the registry, and are
// the ONLY way the editor changes a document. That gives undo/redo for free
// (push the previous IR) and a single chokepoint for validation and, later,
// server-side re-validation and audit.

import type {
  NodePosition,
  WorkflowEdge,
  WorkflowIR,
  WorkflowNode,
  WorkflowSettings,
} from './types';
import { getNodeDefinition } from './registry';
import { portsCompatible, requiredCapabilitiesFor } from './validation';

export type Patch =
  | { op: 'add_node'; node: Omit<WorkflowNode, 'id'> & { id?: string } }
  | { op: 'remove_node'; nodeId: string }
  | { op: 'move_node'; nodeId: string; position: NodePosition }
  | { op: 'update_node_config'; nodeId: string; config: Record<string, unknown> }
  | { op: 'update_node_label'; nodeId: string; label?: string }
  | { op: 'update_node_notes'; nodeId: string; notes?: string }
  | { op: 'replace_node'; nodeId: string; type: string; version: string; config?: Record<string, unknown> }
  | { op: 'add_edge'; edge: Omit<WorkflowEdge, 'id'> & { id?: string } }
  | { op: 'remove_edge'; edgeId: string }
  | { op: 'set_settings'; settings: Partial<WorkflowSettings> }
  | { op: 'set_meta'; name?: string; description?: string; tags?: string[] };

export type PatchResult =
  | { ok: true; ir: WorkflowIR; patch: Patch }
  | { ok: false; error: string; patch: Patch };

function genId(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

function touch(ir: WorkflowIR): WorkflowIR {
  return { ...ir, meta: { ...ir.meta, updatedAt: new Date().toISOString() } };
}

/** Recompute the workflow's declared capabilities from its nodes. */
function withCapabilities(ir: WorkflowIR): WorkflowIR {
  return { ...ir, requiredCapabilities: requiredCapabilitiesFor(ir) };
}

/** Does adding this edge create a cycle? (DAG required in Phase 1.) */
function createsCycle(ir: WorkflowIR, source: string, target: string): boolean {
  if (source === target) return true;
  const adj = new Map<string, string[]>();
  for (const node of ir.nodes) adj.set(node.id, []);
  for (const edge of ir.edges) adj.get(edge.source)?.push(edge.target);
  // Walk forward from target: if we can reach source, the new edge closes a loop.
  const stack = [target];
  const seen = new Set<string>();
  while (stack.length) {
    const id = stack.pop() as string;
    if (id === source) return true;
    if (seen.has(id)) continue;
    seen.add(id);
    for (const next of adj.get(id) ?? []) stack.push(next);
  }
  return false;
}

/**
 * Can these two ports be wired? Combines registry existence, port-type
 * compatibility, endpoint guards and the acyclicity rule. Used by the canvas
 * `isValidConnection` hook BEFORE an edge is created.
 */
export function canConnect(
  ir: WorkflowIR,
  source: string,
  sourceHandle: string,
  target: string,
  targetHandle: string,
): { ok: boolean; reason?: string } {
  if (source === target) return { ok: false, reason: 'A node cannot connect to itself.' };
  const srcNode = ir.nodes.find((n) => n.id === source);
  const tgtNode = ir.nodes.find((n) => n.id === target);
  if (!srcNode || !tgtNode) return { ok: false, reason: 'Missing endpoint.' };
  const srcDef = getNodeDefinition(srcNode.type, srcNode.version);
  const tgtDef = getNodeDefinition(tgtNode.type, tgtNode.version);
  const outPort = srcDef?.outputs.find((p) => p.id === sourceHandle);
  const inPort = tgtDef?.inputs.find((p) => p.id === targetHandle);
  if (!outPort || !inPort) return { ok: false, reason: 'Unknown port.' };
  if (!portsCompatible(outPort, inPort)) {
    return { ok: false, reason: `Incompatible types: ${outPort.type} → ${inPort.type}.` };
  }
  const dup = ir.edges.some(
    (e) => e.source === source && e.sourceHandle === sourceHandle && e.target === target && e.targetHandle === targetHandle,
  );
  if (dup) return { ok: false, reason: 'That connection already exists.' };
  if (createsCycle(ir, source, target)) return { ok: false, reason: 'This would create a cycle.' };
  return { ok: true };
}

/** Apply a single patch. Returns a new IR or a rejection with a reason. */
export function applyPatch(ir: WorkflowIR, patch: Patch): PatchResult {
  switch (patch.op) {
    case 'add_node': {
      const def = getNodeDefinition(patch.node.type, patch.node.version);
      if (!def) return { ok: false, error: `Unknown node type ${patch.node.type}@${patch.node.version}`, patch };
      const id = patch.node.id ?? genId('n');
      if (ir.nodes.some((n) => n.id === id)) return { ok: false, error: `Node id "${id}" already exists.`, patch };
      const node: WorkflowNode = {
        id,
        type: patch.node.type,
        version: patch.node.version,
        label: patch.node.label,
        notes: patch.node.notes,
        config: patch.node.config ?? def.defaultConfig(),
        layout: patch.node.layout,
      };
      return { ok: true, ir: withCapabilities(touch({ ...ir, nodes: [...ir.nodes, node] })), patch };
    }
    case 'remove_node': {
      if (!ir.nodes.some((n) => n.id === patch.nodeId)) return { ok: false, error: `Node "${patch.nodeId}" not found.`, patch };
      const nodes = ir.nodes.filter((n) => n.id !== patch.nodeId);
      const edges = ir.edges.filter((e) => e.source !== patch.nodeId && e.target !== patch.nodeId);
      return { ok: true, ir: withCapabilities(touch({ ...ir, nodes, edges })), patch };
    }
    case 'move_node': {
      const nodes = ir.nodes.map((n) => (n.id === patch.nodeId ? { ...n, layout: patch.position } : n));
      if (!ir.nodes.some((n) => n.id === patch.nodeId)) return { ok: false, error: `Node "${patch.nodeId}" not found.`, patch };
      // Layout is non-semantic: do not bump `updatedAt` for a pure move.
      return { ok: true, ir: { ...ir, nodes }, patch };
    }
    case 'update_node_config': {
      if (!ir.nodes.some((n) => n.id === patch.nodeId)) return { ok: false, error: `Node "${patch.nodeId}" not found.`, patch };
      const nodes = ir.nodes.map((n) => (n.id === patch.nodeId ? { ...n, config: patch.config } : n));
      return { ok: true, ir: touch({ ...ir, nodes }), patch };
    }
    case 'update_node_label': {
      if (!ir.nodes.some((n) => n.id === patch.nodeId)) return { ok: false, error: `Node "${patch.nodeId}" not found.`, patch };
      const nodes = ir.nodes.map((n) => (n.id === patch.nodeId ? { ...n, label: patch.label } : n));
      return { ok: true, ir: touch({ ...ir, nodes }), patch };
    }
    case 'update_node_notes': {
      if (!ir.nodes.some((n) => n.id === patch.nodeId)) return { ok: false, error: `Node "${patch.nodeId}" not found.`, patch };
      const notes = patch.notes?.trim();
      const nodes = ir.nodes.map((n) => (n.id === patch.nodeId ? { ...n, notes: notes || undefined } : n));
      return { ok: true, ir: touch({ ...ir, nodes }), patch };
    }
    case 'replace_node': {
      const existing = ir.nodes.find((n) => n.id === patch.nodeId);
      if (!existing) return { ok: false, error: `Node "${patch.nodeId}" not found.`, patch };
      const def = getNodeDefinition(patch.type, patch.version);
      if (!def) return { ok: false, error: `Unknown node type ${patch.type}@${patch.version}`, patch };
      const nodes = ir.nodes.map((n) =>
        n.id === patch.nodeId
          ? { ...n, type: patch.type, version: patch.version, config: patch.config ?? def.defaultConfig() }
          : n,
      );
      // Dropping edges whose handles no longer exist on the replaced node.
      const edges = ir.edges.filter((e) => {
        if (e.source === patch.nodeId) return def.outputs.some((p) => p.id === e.sourceHandle);
        if (e.target === patch.nodeId) return def.inputs.some((p) => p.id === e.targetHandle);
        return true;
      });
      return { ok: true, ir: withCapabilities(touch({ ...ir, nodes, edges })), patch };
    }
    case 'add_edge': {
      const id = patch.edge.id ?? genId('e');
      if (ir.edges.some((e) => e.id === id)) return { ok: false, error: `Edge id "${id}" already exists.`, patch };
      const check = canConnect(ir, patch.edge.source, patch.edge.sourceHandle, patch.edge.target, patch.edge.targetHandle);
      if (!check.ok) return { ok: false, error: check.reason ?? 'Invalid connection.', patch };
      const edge: WorkflowEdge = { ...patch.edge, id };
      return { ok: true, ir: touch({ ...ir, edges: [...ir.edges, edge] }), patch };
    }
    case 'remove_edge': {
      if (!ir.edges.some((e) => e.id === patch.edgeId)) return { ok: false, error: `Edge "${patch.edgeId}" not found.`, patch };
      const edges = ir.edges.filter((e) => e.id !== patch.edgeId);
      return { ok: true, ir: touch({ ...ir, edges }), patch };
    }
    case 'set_settings': {
      return { ok: true, ir: touch({ ...ir, settings: { ...ir.settings, ...patch.settings } }), patch };
    }
    case 'set_meta': {
      const meta = { ...ir.meta };
      if (patch.tags) meta.tags = patch.tags;
      return {
        ok: true,
        ir: touch({
          ...ir,
          name: patch.name ?? ir.name,
          description: patch.description ?? ir.description,
          meta,
        }),
        patch,
      };
    }
    default:
      return { ok: false, error: 'Unknown patch operation.', patch: patch as Patch };
  }
}

/** Apply patches in order, stopping at the first rejection. */
export function applyPatches(ir: WorkflowIR, patches: Patch[]): PatchResult {
  let current = ir;
  for (const patch of patches) {
    const result = applyPatch(current, patch);
    if (!result.ok) return result;
    current = result.ir;
  }
  return { ok: true, ir: current, patch: patches[patches.length - 1] };
}
