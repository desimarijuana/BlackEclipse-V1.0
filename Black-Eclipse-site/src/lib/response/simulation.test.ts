import { describe, expect, it } from 'vitest';
import type { SimulationBlock } from './contract';
import {
  computeSimulation,
  initialSimulationValues,
  resolveSimulationInputs,
  resolveSimulationOutputs,
} from './simulation';

function block(overrides: Partial<SimulationBlock> = {}): SimulationBlock {
  return { type: 'simulation', inputs: [], outputs: [], ...overrides } as SimulationBlock;
}

const preset = block({ preset: 'risk_reward' });

describe('resolveSimulationInputs / Outputs', () => {
  it('expands the risk_reward preset when no explicit inputs/outputs are given', () => {
    const inputs = resolveSimulationInputs(preset);
    const outputs = resolveSimulationOutputs(preset);
    expect(inputs.map((i) => i.id)).toEqual(['entry', 'stopPercent', 'targetPercent']);
    expect(outputs.map((o) => o.id)).toEqual(['stopPrice', 'targetPrice', 'riskReward', 'breakEvenWinRate']);
  });

  it('lets explicit inputs override the preset', () => {
    const inputs = resolveSimulationInputs(
      block({ preset: 'risk_reward', inputs: [{ id: 'qty', label: 'Quantity', kind: 'number', value: 10 }] }),
    );
    expect(inputs.map((i) => i.id)).toEqual(['qty']);
  });

  it('resolves a fully explicit block with no preset', () => {
    const b = block({
      inputs: [{ id: 'cost', label: 'Cost', kind: 'number', value: 3 }],
      outputs: [{ id: 'double', label: 'Double', expression: 'cost * 2' }],
    });
    expect(resolveSimulationInputs(b).map((i) => i.id)).toEqual(['cost']);
    expect(resolveSimulationOutputs(b).map((o) => o.id)).toEqual(['double']);
  });
});

describe('computeSimulation', () => {
  it('computes the preset outputs from the current input values', () => {
    const results = computeSimulation(resolveSimulationOutputs(preset), {
      entry: 100,
      stopPercent: 2,
      targetPercent: 6,
    });
    const byId = Object.fromEntries(results.map((r) => [r.output.id, r.value]));
    expect(byId.stopPrice).toBeCloseTo(98, 6);
    expect(byId.targetPrice).toBeCloseTo(106, 6);
    expect(byId.riskReward).toBeCloseTo(3, 6);
    expect(byId.breakEvenWinRate).toBeCloseTo(25, 6);
  });

  it('matches the blueprint example (2% stop, 9.5% target → 1:4.75)', () => {
    const results = computeSimulation(resolveSimulationOutputs(preset), {
      entry: 100,
      stopPercent: 2,
      targetPercent: 9.5,
    });
    const byId = Object.fromEntries(results.map((r) => [r.output.id, r]));
    expect(byId.riskReward.value).toBeCloseTo(4.75, 6);
    expect(byId.breakEvenWinRate.value).toBeCloseTo(17.3913, 3);
  });

  it('renders UNAVAILABLE (—) when a computed figure is undefined, not a wrong number', () => {
    const results = computeSimulation(resolveSimulationOutputs(preset), {
      entry: 100,
      stopPercent: 0,
      targetPercent: 6,
    });
    const byId = Object.fromEntries(results.map((r) => [r.output.id, r]));
    expect(byId.riskReward.value).toBeNull();
    expect(byId.riskReward.display).toBe('—');
    expect(byId.breakEvenWinRate.value).toBeCloseTo(0, 6);
  });

  it('lets a later output reference an earlier output', () => {
    const outputs = resolveSimulationOutputs(
      block({
        inputs: [{ id: 'x', label: 'X', kind: 'number', value: 4 }],
        outputs: [
          { id: 'sq', label: 'Square', expression: 'x * x', precision: 0 },
          { id: 'plus', label: 'Plus one', expression: 'sq + 1', precision: 0 },
        ],
      }),
    );
    const results = computeSimulation(outputs, { x: 4 });
    expect(results[1].value).toBeCloseTo(17, 6);
  });
});

describe('initialSimulationValues', () => {
  it('seeds each input with its declared value', () => {
    expect(initialSimulationValues(resolveSimulationInputs(preset))).toEqual({
      entry: 100,
      stopPercent: 2,
      targetPercent: 6,
    });
  });
});
