import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
  EvalError,
  EVAL_FUNCTIONS,
  evaluateExpression,
  formatSimulationValue,
  parseExpression,
  validateExpression,
} from './evaluate';

interface Case {
  expression: string;
  vars: Record<string, number>;
  expected: number | null;
}

const fixtures = JSON.parse(
  readFileSync(new URL('./__fixtures__/evaluate-cases.json', import.meta.url), 'utf-8'),
) as { cases: Case[] };

describe('evaluateExpression — shared fixtures (parity with Python)', () => {
  for (const { expression, vars, expected } of fixtures.cases) {
    it(`\`${expression}\` → ${expected === null ? 'UNAVAILABLE' : expected}`, () => {
      const result = evaluateExpression(expression, vars);
      if (expected === null) {
        expect(result).toBeNull();
      } else {
        expect(result).not.toBeNull();
        expect(result as number).toBeCloseTo(expected, 9);
      }
    });
  }
});

describe('validateExpression', () => {
  it('accepts a known expression and reports variables + functions', () => {
    const result = validateExpression('clamp(entry * x, 0, 100)', ['entry', 'x']);
    expect(result.ok).toBe(true);
    expect(result.variables.sort()).toEqual(['entry', 'x']);
    expect(result.functions).toEqual(['clamp']);
  });

  it('rejects an unknown function', () => {
    const result = validateExpression('totally_made_up(1)');
    expect(result.ok).toBe(false);
    expect(result.error).toContain('unknown function');
  });

  it('rejects an unknown variable when a known set is supplied', () => {
    const result = validateExpression('a + b', ['a']);
    expect(result.ok).toBe(false);
    expect(result.error).toContain('unknown variable');
  });

  it('rejects an empty expression', () => {
    expect(validateExpression('').ok).toBe(false);
  });
});

describe('parseExpression', () => {
  it('throws a structured EvalError on a syntax error', () => {
    expect(() => parseExpression('2 +')).toThrow(EvalError);
  });
});

describe('EVAL_FUNCTIONS', () => {
  it('is a closed, sorted whitelist', () => {
    expect(EVAL_FUNCTIONS).toEqual([...EVAL_FUNCTIONS].sort());
    expect(EVAL_FUNCTIONS).toContain('clamp');
    expect(EVAL_FUNCTIONS).not.toContain('eval');
  });
});

describe('formatSimulationValue', () => {
  it('renders UNAVAILABLE for null', () => {
    expect(formatSimulationValue(null)).toBe('—');
  });
  it('formats currency and percent', () => {
    expect(formatSimulationValue(1234.5, { format: 'currency', precision: 2 })).toBe('$1,234.50');
    expect(formatSimulationValue(17.3913, { format: 'percent', precision: 1 })).toBe('17.4%');
  });
  it('applies a unit suffix for numbers', () => {
    expect(formatSimulationValue(4.75, { unit: '×', precision: 2 })).toBe('4.75×');
  });
});
