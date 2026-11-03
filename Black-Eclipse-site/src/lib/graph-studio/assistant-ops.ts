// ── Graph assistant operations → editor patches ─────────────────────────────
// The Python assistant returns a closed set of operations (the same shape the
// editor's patch layer understands). This module is the ONE translation seam,
// so the panel never hand-builds patches and tests can cover the mapping
// directly.

import type { Patch } from './patches';
import type { NodePosition, WorkflowSettings } from './types';

export type GraphEditOp =
  | {
      op: 'add_node';
      node: {
        id?: string;
        type: string;
        version: string;
        label?: string;
        config?: Record<string, unknown>;
        layout?: NodePosition;
      };
    }
  | { op: 'remove_node'; nodeId: string }
  | { op: 'update_node_config'; nodeId: string; config: Record<string, unknown> }
  | { op: 'update_node_label'; nodeId: string; label?: string | null }
  | {
      op: 'add_edge';
      edge: {
        id?: string;
        source: string;
        sourceHandle: string;
        target: string;
        targetHandle: string;
      };
    }
  | { op: 'remove_edge'; edgeId: string }
  | { op: 'set_settings'; settings: Partial<WorkflowSettings> }
  | { op: 'set_meta'; name?: string; description?: string; tags?: string[] };

function position(value: GraphEditOp & { op: 'add_node' }): NodePosition {
  const layout = value.node.layout;
  return {
    x: typeof layout?.x === 'number' ? layout.x : 120,
    y: typeof layout?.y === 'number' ? layout.y : 100,
  };
}

/** Convert validated server operations into editor patches. Unknown ops are
 *  skipped (never guessed) so a newer server cannot corrupt an older client. */
export function graphEditOpsToPatches(ops: GraphEditOp[]): Patch[] {
  const patches: Patch[] = [];
  for (const item of ops) {
    switch (item.op) {
      case 'add_node':
        patches.push({
          op: 'add_node',
          node: {
            id: item.node.id,
            type: item.node.type,
            version: item.node.version,
            label: item.node.label,
            config: item.node.config ?? {},
            layout: position(item),
          },
        });
        break;
      case 'remove_node':
        patches.push({ op: 'remove_node', nodeId: item.nodeId });
        break;
      case 'update_node_config':
        patches.push({ op: 'update_node_config', nodeId: item.nodeId, config: item.config });
        break;
      case 'update_node_label':
        patches.push({ op: 'update_node_label', nodeId: item.nodeId, label: item.label ?? undefined });
        break;
      case 'add_edge':
        patches.push({
          op: 'add_edge',
          edge: {
            id: item.edge.id,
            source: item.edge.source,
            sourceHandle: item.edge.sourceHandle,
            target: item.edge.target,
            targetHandle: item.edge.targetHandle,
          },
        });
        break;
      case 'remove_edge':
        patches.push({ op: 'remove_edge', edgeId: item.edgeId });
        break;
      case 'set_settings':
        patches.push({ op: 'set_settings', settings: item.settings });
        break;
      case 'set_meta':
        patches.push({
          op: 'set_meta',
          ...(item.name !== undefined ? { name: item.name } : {}),
          ...(item.description !== undefined ? { description: item.description } : {}),
          ...(item.tags !== undefined ? { tags: item.tags } : {}),
        });
        break;
      default:
        break;
    }
  }
  return patches;
}

/** One-line, human-readable description of an operation for the proposal card. */
export function describeOp(item: GraphEditOp): string {
  switch (item.op) {
    case 'add_node':
      return `Add ${item.node.label || item.node.type}`;
    case 'remove_node':
      return `Remove node ${item.nodeId}`;
    case 'update_node_config':
      return `Update settings on ${item.nodeId}`;
    case 'update_node_label':
      return `Rename ${item.nodeId}${item.label ? ` to “${item.label}”` : ''}`;
    case 'add_edge':
      return `Connect ${item.edge.source} → ${item.edge.target}`;
    case 'remove_edge':
      return `Remove connection ${item.edgeId}`;
    case 'set_settings':
      return `Change workflow settings`;
    case 'set_meta':
      return `Update workflow details`;
    default:
      return 'Change';
  }
}
