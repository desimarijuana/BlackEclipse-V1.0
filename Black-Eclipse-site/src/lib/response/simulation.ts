// ── Declarative simulation resolution ─────────────────────────────────────────
// The `simulation` block is a declarative calculator: a set of INPUTS is the
// local state, and a set of OUTPUTS are safe expressions evaluated over that
// state (see `./evaluate`). Nothing here calls a model or the network — a slider
// move recomputes locally, with 0 model calls.
//
// A named `preset` supplies a canonical input/output set; explicit `inputs`/
// `outputs` on the block override it. The preset for `risk_reward` is the
// blueprint's example, expressed the same declarative way a producer would.

import type { SimulationBlock } from './contract';
import { evaluateExpression, formatSimulationValue, type FormatSpec } from './evaluate';

export interface ResolvedInput {
  id: string;
  label: string;
  kind: 'number' | 'select' | 'toggle';
  value: number;
  min?: number;
  max?: number;
  step?: number;
  options?: { value: string; label: string }[];
}

export interface ResolvedOutput {
  id: string;
  label: string;
  expression: string;
  precision?: number;
  format?: 'number' | 'currency' | 'percent';
  unit?: string;
  tone?: 'neutral' | 'info' | 'success' | 'warning' | 'danger';
}

export interface ComputedOutput {
  output: ResolvedOutput;
  value: number | null;
  display: string;
}

const RISK_REWARD_INPUTS: ResolvedInput[] = [
  { id: 'entry', label: 'Entry price', kind: 'number', value: 100, min: 0.01, max: 1_000_000, step: 0.01 },
  { id: 'stopPercent', label: 'Stop-loss distance', kind: 'number', value: 2, min: 0, max: 50, step: 0.1 },
  { id: 'targetPercent', label: 'Target distance', kind: 'number', value: 6, min: 0, max: 100, step: 0.1 },
];

const RISK_REWARD_OUTPUTS: ResolvedOutput[] = [
  { id: 'stopPrice', label: 'Stop price', expression: 'entry - entry * stopPercent / 100', precision: 2 },
  { id: 'targetPrice', label: 'Target price', expression: 'entry + entry * targetPercent / 100', precision: 2 },
  { id: 'riskReward', label: 'Risk / reward', expression: 'targetPercent / stopPercent', precision: 2, tone: 'info' },
  {
    id: 'breakEvenWinRate',
    label: 'Break-even win rate',
    expression: 'stopPercent / (stopPercent + targetPercent) * 100',
    format: 'percent',
    precision: 1,
    tone: 'info',
  },
];

const PRESETS: Record<string, { inputs: ResolvedInput[]; outputs: ResolvedOutput[] }> = {
  risk_reward: { inputs: RISK_REWARD_INPUTS, outputs: RISK_REWARD_OUTPUTS },
};

function presetOf(block: SimulationBlock) {
  return block.preset ? PRESETS[block.preset] : undefined;
}

/** The inputs for a block: explicit inputs win, else the preset, else none. */
export function resolveSimulationInputs(block: SimulationBlock): ResolvedInput[] {
  if (block.inputs.length > 0) {
    return block.inputs.map((input) => ({
      id: input.id,
      label: input.label,
      kind: input.kind,
      value: input.value ?? 0,
      ...(input.min != null ? { min: input.min } : {}),
      ...(input.max != null ? { max: input.max } : {}),
      ...(input.step != null ? { step: input.step } : {}),
      ...(input.options ? { options: input.options } : {}),
    }));
  }
  return presetOf(block)?.inputs ?? [];
}

/** The outputs for a block: explicit outputs win, else the preset, else none. */
export function resolveSimulationOutputs(block: SimulationBlock): ResolvedOutput[] {
  if (block.outputs.length > 0) {
    return block.outputs.map((output) => ({
      id: output.id,
      label: output.label,
      expression: output.expression,
      ...(output.precision != null ? { precision: output.precision } : {}),
      ...(output.format ? { format: output.format } : {}),
      ...(output.unit ? { unit: output.unit } : {}),
      ...(output.tone ? { tone: output.tone } : {}),
    }));
  }
  return presetOf(block)?.outputs ?? [];
}

/**
 * Evaluate every output over the current input values. Outputs evaluate in order,
 * so a later output may reference an earlier output's id. A division-by-zero or
 * non-finite result renders as UNAVAILABLE (`value: null`), never a wrong number.
 */
export function computeSimulation(
  outputs: ResolvedOutput[],
  values: Record<string, number>,
): ComputedOutput[] {
  const vars: Record<string, number> = { ...values };
  const results: ComputedOutput[] = [];
  for (const output of outputs) {
    const value = evaluateExpression(output.expression, vars);
    if (value != null) vars[output.id] = value;
    const spec: FormatSpec = { precision: output.precision, format: output.format, unit: output.unit };
    results.push({ output, value, display: formatSimulationValue(value, spec) });
  }
  return results;
}

/** The initial values for a block's inputs (what the sliders/fields start at). */
export function initialSimulationValues(inputs: ResolvedInput[]): Record<string, number> {
  const values: Record<string, number> = {};
  for (const input of inputs) values[input.id] = input.value;
  return values;
}
