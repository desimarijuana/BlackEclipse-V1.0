import { describe, expect, it } from 'vitest';
import {
  caseLabel,
  MAX_SWITCH_CASES,
  parseSwitchCases,
  unwiredRequiredInputs,
  visiblePorts,
} from './node-ports';
import { getNodeDefinition } from './registry';

const switchDef = getNodeDefinition('logic.switch')!;
const mapDef = getNodeDefinition('logic.map')!;

describe('parseSwitchCases', () => {
  it('reads a comma list and trims it', () => {
    expect(parseSwitchCases('buy, sell ,hold')).toEqual(['buy', 'sell', 'hold']);
    expect(parseSwitchCases('')).toEqual([]);
    expect(parseSwitchCases(undefined)).toEqual([]);
  });

  it('reads a JSON array so a case may contain a comma', () => {
    expect(parseSwitchCases('["a,b", "c"]')).toEqual(['a,b', 'c']);
  });

  it('reports invalid JSON as null instead of throwing', () => {
    expect(parseSwitchCases('[a, b')).toBeNull();
    expect(parseSwitchCases('[1, 2]')).toEqual(['1', '2']);
  });

  it('matches the runtime: only a leading [ is JSON, everything else is a list', () => {
    // `_switch_cases` only parses JSON when the text starts with `[`.
    expect(parseSwitchCases('{"a":1}')).toEqual(['{"a":1}']);
  });
});

describe('caseLabel', () => {
  it('uses the value, falls back to the position, and truncates', () => {
    expect(caseLabel('buy', 0)).toBe('buy');
    expect(caseLabel('  ', 2)).toBe('Case 3');
    expect(caseLabel('x'.repeat(30), 0)).toHaveLength(18);
  });
});

describe('visiblePorts — logic.switch', () => {
  it('shows only default/matched when no cases are configured', () => {
    const { outputs } = visiblePorts(switchDef, { type: 'logic.switch', config: { cases: '' } });
    expect(outputs.map((p) => p.id)).toEqual(['default', 'matched']);
  });

  it('only shows the case index when something is wired to it', () => {
    const cases = { type: 'logic.switch', config: { cases: 'buy, sell, hold' } };
    expect(visiblePorts(switchDef, cases).outputs.map((p) => p.id)).not.toContain('caseIndex');
    expect(visiblePorts(switchDef, cases, ['caseIndex']).outputs.map((p) => p.id)).toContain('caseIndex');
  });

  it('shows one labelled output per configured case', () => {
    const { outputs } = visiblePorts(switchDef, {
      type: 'logic.switch',
      config: { cases: 'buy, sell, hold' },
    });
    expect(outputs.map((p) => p.id)).toEqual([
      'case1', 'case2', 'case3', 'default', 'matched',
    ]);
    expect(outputs.slice(0, 3).map((p) => p.name)).toEqual(['buy', 'sell', 'hold']);
    expect(outputs.slice(3).map((p) => p.name)).toEqual(['No match', 'Any match']);
  });

  it('caps the case handles at the declared maximum', () => {
    const cases = Array.from({ length: 12 }, (_, i) => `c${i + 1}`).join(', ');
    const { outputs } = visiblePorts(switchDef, { type: 'logic.switch', config: { cases } });
    expect(outputs.filter((p) => /^case\d+$/.test(p.id))).toHaveLength(MAX_SWITCH_CASES);
  });

  it('keeps a wired case handle even when its case was removed', () => {
    const { outputs } = visiblePorts(
      switchDef,
      { type: 'logic.switch', config: { cases: 'buy, sell' } },
      ['case4'],
    );
    expect(outputs.map((p) => p.id)).toContain('case4');
  });

  it('never changes handle ids or types', () => {
    const { outputs } = visiblePorts(switchDef, {
      type: 'logic.switch',
      config: { cases: 'a' },
    });
    for (const port of outputs) {
      expect(switchDef.outputs.some((declared) => declared.id === port.id)).toBe(true);
      expect(port.kind).toBe(
        switchDef.outputs.find((declared) => declared.id === port.id)!.kind,
      );
    }
  });
});

describe('visiblePorts — other nodes', () => {
  it('returns the declared ports untouched', () => {
    const ports = visiblePorts(mapDef, { type: 'logic.map', config: {} });
    expect(ports.inputs).toBe(mapDef.inputs);
    expect(ports.outputs).toBe(mapDef.outputs);
  });
});

describe('unwiredRequiredInputs', () => {
  it('lists required inputs that are neither wired nor given a literal', () => {
    const missing = unwiredRequiredInputs(mapDef, [], {});
    expect(missing.map((p) => p.id)).toEqual(['items']);
    expect(missing.map((p) => p.name)).toEqual(['Items']);
  });

  it('is satisfied by a wire or by a node literal', () => {
    expect(unwiredRequiredInputs(mapDef, ['items'], {})).toEqual([]);
    expect(unwiredRequiredInputs(mapDef, [], { items: [] })).toEqual([]);
  });

  it('never asks for optional or control ports', () => {
    // `flow.gate`'s second/third run inputs are optional by contract.
    const gate = getNodeDefinition('flow.gate')!;
    expect(unwiredRequiredInputs(gate, [], {}).map((p) => p.id)).toEqual(['in']);
  });
});
