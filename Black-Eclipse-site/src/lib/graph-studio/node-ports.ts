// ── Per-node PORT PRESENTATION ─────────────────────────────────────────────
// A node definition declares the full contract, but some nodes are only usable
// when the card shows the ports the operator actually asked for. `logic.switch`
// is the case that matters: its contract declares eight `case1..case8` control
// outputs so one switch can own an eight-way branch, which would otherwise render
// as ten anonymous handles — a switch with three cases looked broken.
//
// This module is PRESENTATION ONLY. Handle ids never change, so edges, the
// validator, the compiler and the runtime are untouched; the canvas simply hides
// the case handles that have no case (unless something is already wired to them,
// so an old edge is never orphaned) and labels each remaining one with its case
// value.

import type { NodeDefinition, PortDef, WorkflowNode } from './types';

export const MAX_SWITCH_CASES = 8;

/** Operator-visible label for a case value. */
export function caseLabel(value: string, index: number): string {
  const text = value.trim();
  if (!text) return `Case ${index + 1}`;
  return text.length <= 18 ? text : `${text.slice(0, 17)}…`;
}

/**
 * Mirror of the runtime's `_switch_cases`: a comma-separated list, or a JSON
 * array when a case itself contains a comma. `null` means the text is not valid
 * JSON (the runtime would refuse it, so the validator reports it).
 */
export function parseSwitchCases(raw: unknown): string[] | null {
  const text = typeof raw === 'string' ? raw.trim() : '';
  if (!text) return [];
  if (text.startsWith('[')) {
    try {
      const parsed: unknown = JSON.parse(text);
      if (!Array.isArray(parsed)) return null;
      return parsed.map((item) => String(item));
    } catch {
      return null;
    }
  }
  return text
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean);
}

/** The ports the canvas should draw for ONE node instance. */export function visiblePorts(
  definition: NodeDefinition,
  node: Pick<WorkflowNode, 'type' | 'config'>,
  wiredOutputHandles: string[] = [],
): { inputs: PortDef[]; outputs: PortDef[] } {
  if (definition.type !== 'logic.switch') {
    return { inputs: definition.inputs, outputs: definition.outputs };
  }

  const cases = parseSwitchCases(node.config.cases) ?? [];
  const wired = new Set(wiredOutputHandles);
  const keep = (port: PortDef): boolean => {
    // The case index is inspection data, not a branch: it only earns a handle on
    // the card when something is actually wired to it.
    if (port.id === 'caseIndex') return wired.has(port.id);
    const match = /^case(\d+)$/.exec(port.id);
    if (!match) return true;
    const index = Number(match[1]);
    // Show a case handle when the case EXISTS, or when an edge still uses it —
    // hiding a wired handle would silently orphan that edge.
    return index <= cases.length || wired.has(port.id);
  };

  const byId = new Map(definition.outputs.map((port) => [port.id, port]));
  const labelled = (port: PortDef): PortDef => {
    const match = /^case(\d+)$/.exec(port.id);
    if (!match) return port;
    return { ...port, name: caseLabel(cases[Number(match[1]) - 1] ?? '', Number(match[1]) - 1) };
  };

  // Case outputs first (they are the point of the node), then default/matched,
  // then the case index. Same ids, different order: edges are keyed by id.
  const order = [
    ...cases.slice(0, MAX_SWITCH_CASES).map((_, index) => `case${index + 1}`),
    'default',
    'matched',
    'caseIndex',
  ];
  const seen = new Set<string>();
  const outputs: PortDef[] = [];
  for (const id of order) {
    const port = byId.get(id);
    if (!port || seen.has(id) || !keep(port)) continue;
    seen.add(id);
    outputs.push(labelled(port));
  }
  // Any wired case beyond the configured list still renders (keep() allowed it).
  for (const port of definition.outputs) {
    if (seen.has(port.id) || !keep(port)) continue;
    outputs.push(labelled(port));
  }
  return { inputs: definition.inputs, outputs };
}

/**
 * Required inputs that nothing satisfies yet: not wired, no node literal.
 *
 * This is the CARD's version of the validator's `missing_required_input` — it
 * exists so the node itself can say "connect: Items" instead of the user finding
 * out from a diagnostics list after a failed run.
 */
export function unwiredRequiredInputs(
  definition: NodeDefinition,
  wiredHandles: string[],
  literals: Record<string, unknown> = {},
): PortDef[] {
  const wired = new Set(wiredHandles);
  return definition.inputs.filter(
    (port) => !port.optional && !wired.has(port.id) && !(port.id in literals),
  );
}

