// ── Subworkflow bundle collection ────────────────────────────────────────────
// The Python runtime cannot read JDDS, so the front door resolves every pinned
// subworkflow a run references and sends the IRs with the run. This module is
// the pure walk: it never executes anything, never trusts a stored document,
// and refuses cycles, missing workflows and excessive nesting before the
// runtime sees them.
//
// Server-only callers supply the loader (`run-server.ts` uses the Prisma store).

import type { WorkflowIR } from './types';

export const MAX_SUBWORKFLOW_DEPTH = 5;
export const MAX_SUBWORKFLOW_BUNDLE = 20;

export interface SubworkflowRef {
  id: string;
  version: number;
}

export interface SubworkflowBundleEntry extends SubworkflowRef {
  ir: WorkflowIR;
}

export type SubworkflowLoader = (id: string, version: number) => Promise<WorkflowIR | null>;

/** The pinned subworkflows directly referenced by a graph. Ignore incomplete
 *  nodes: the editor/compiler reports those as invalid configuration. */
export function subworkflowRefs(ir: WorkflowIR): SubworkflowRef[] {
  const refs: SubworkflowRef[] = [];
  for (const node of ir.nodes) {
    if (node.type !== 'flow.subworkflow') continue;
    const workflowId = typeof node.config.workflowId === 'string' ? node.config.workflowId.trim() : '';
    const version = Number(node.config.version);
    if (!workflowId || !Number.isInteger(version) || version < 1) continue;
    refs.push({ id: workflowId, version });
  }
  return refs;
}

/** Resolve every referenced subworkflow (recursively), or throw a user-facing
 *  error. Each workflow appears once, even if referenced by several nodes. */
export async function collectSubworkflows(
  root: WorkflowIR,
  load: SubworkflowLoader,
  options: { rootKey?: string } = {},
): Promise<SubworkflowBundleEntry[]> {
  const bundle = new Map<string, SubworkflowBundleEntry>();

  const visit = async (ir: WorkflowIR, depth: number, stack: string[]): Promise<void> => {
    for (const ref of subworkflowRefs(ir)) {
      const key = `${ref.id}@${ref.version}`;
      if (stack.includes(key)) {
        throw new Error(`Subworkflow cycle detected: ${[...stack, key].join(' -> ')}`);
      }
      if (depth >= MAX_SUBWORKFLOW_DEPTH) {
        throw new Error(`Subworkflow nesting exceeds the maximum depth (${MAX_SUBWORKFLOW_DEPTH}).`);
      }
      if (bundle.has(key)) continue;
      if (bundle.size >= MAX_SUBWORKFLOW_BUNDLE) {
        throw new Error(`Too many subworkflows (max ${MAX_SUBWORKFLOW_BUNDLE}).`);
      }
      const child = await load(ref.id, ref.version);
      if (!child) throw new Error(`Subworkflow ${key} was not found.`);
      bundle.set(key, { id: ref.id, version: ref.version, ir: child });
      await visit(child, depth + 1, [...stack, key]);
    }
  };

  await visit(root, 0, options.rootKey ? [options.rootKey] : []);
  return [...bundle.values()];
}
