// ── Envelope state + computed values ──────────────────────────────────────────
// Pure helpers for the v1.1 envelope `state`/`computed`. State is the shared
// input a user drives; computed entries are safe expressions over state (the SAME
// evaluator as the `simulation` block). Everything is local — 0 model calls.

import { evaluateExpression } from './evaluate';
import type { ComputedVar, StateVar } from './contract';

/** The default values for an envelope's state. */
export function initialEnvelopeValues(state: StateVar[]): Record<string, number> {
  const values: Record<string, number> = {};
  for (const variable of state) values[variable.id] = variable.value;
  return values;
}

/**
 * Compute the envelope's derived values from the current state. Computed entries
 * evaluate in order, so a later computed may reference an earlier one. An output
 * whose expression cannot resolve is simply absent (its bound figures render
 * UNAVAILABLE via the resolver).
 */
export function computeEnvelopeValues(
  state: StateVar[],
  computed: ComputedVar[],
  values: Record<string, number>,
): Record<string, number> {
  const out: Record<string, number> = { ...initialEnvelopeValues(state), ...values };
  for (const entry of computed) {
    const value = evaluateExpression(entry.expression, out);
    if (value != null) out[entry.id] = value;
  }
  return out;
}
