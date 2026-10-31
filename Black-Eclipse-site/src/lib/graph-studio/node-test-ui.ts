// ── Node test state (client) ─────────────────────────────────────────────────
// Pure helpers shared by the node card, the quick-edit popover and the canvas.
// A per-node test is a one-off runtime call; nothing here is persisted.

import type { NodeDefinition } from './types';

export interface NodeTestUiState {
  status: 'running' | 'succeeded' | 'failed';
  durationMs?: number;
  outputs?: Record<string, unknown>;
  logs?: string[];
  error?: string;
}

const ORCHESTRATED = new Set([
  'flow.subworkflow',
  'flow.for_each',
  'flow.repeat',
  'flow.while',
]);

/** The safe envelope: only none/read nodes may be tested in isolation. */
export function canTestNode(definition: NodeDefinition): boolean {
  if (ORCHESTRATED.has(definition.type)) return false;
  return definition.sideEffects === 'none' || definition.sideEffects === 'read';
}

export type NodeInputsResult =
  | { ok: true; value: Record<string, unknown> }
  | { ok: false; error: string };

/** Parse the per-node test inputs textarea (a JSON object keyed by port id). */
export function parseNodeInputs(text: string): NodeInputsResult {
  const trimmed = text.trim();
  if (!trimmed) return { ok: true, value: {} };
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    return { ok: false, error: 'Inputs must be valid JSON.' };
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { ok: false, error: 'Inputs must be a JSON object keyed by input port id.' };
  }
  return { ok: true, value: parsed as Record<string, unknown> };
}

/** Required input ports with no value in the test inputs. */
export function missingRequiredInputs(
  definition: NodeDefinition,
  inputs: Record<string, unknown>,
): string[] {
  return definition.inputs
    .filter((port) => !port.optional && !(port.id in inputs))
    .map((port) => port.id);
}

export function inputsText(value: Record<string, unknown> | undefined | null): string {
  if (!value || Object.keys(value).length === 0) return '{}';
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return '{}';
  }
}
