import { describe, it, expect } from 'vitest';
import { evaluateCalc } from './calc';
import { detectParamCommand, paramCandidates } from './commands';

describe('evaluateCalc — arithmetic', () => {
  it('evaluates basic expressions with precedence', () => {
    expect(evaluateCalc('12 * 4 + 8')?.value).toBe(56);
    expect(evaluateCalc('2 + 3 * 4')?.value).toBe(14);
    expect(evaluateCalc('(2 + 3) * 4')?.value).toBe(20);
    expect(evaluateCalc('10 / 4')?.value).toBe(2.5);
  });

  it('formats the display string', () => {
    expect(evaluateCalc('12 * 4 + 8')?.display).toBe('56');
    expect(evaluateCalc('10 / 4')?.display).toBe('2.5');
  });

  it('does not treat a bare number as a calculation', () => {
    expect(evaluateCalc('42')).toBeNull();
    expect(evaluateCalc('AAPL')).toBeNull();
  });

  it('rejects division by zero rather than returning Infinity', () => {
    expect(evaluateCalc('5 / 0')).toBeNull();
  });

  it('ignores non-arithmetic queries', () => {
    expect(evaluateCalc('open portfolio')).toBeNull();
    expect(evaluateCalc('')).toBeNull();
  });
});

describe('evaluateCalc — conversion', () => {
  it('converts currencies from the indicative table', () => {
    const r = evaluateCalc('100 usd in eur');
    expect(r?.kind).toBe('conversion');
    expect(r?.value).toBeCloseTo(92, 0);
    // Majors render with their symbol; others with the code.
    expect(r?.display).toMatch(/€|EUR/);
  });

  it('defaults the source to USD', () => {
    expect(evaluateCalc('100 in eur')?.kind).toBe('conversion');
  });

  it('accepts "to"/"into" and uses a symbol for majors', () => {
    expect(evaluateCalc('50 usd to gbp')?.kind).toBe('conversion');
    expect(evaluateCalc('10 usd into jpy')?.display).toContain('¥');
  });

  it('returns null for unknown currencies', () => {
    expect(evaluateCalc('100 usd in zzz')).toBeNull();
  });
});

describe('detectParamCommand', () => {
  it('detects a known verb with an argument', () => {
    const c = detectParamCommand('alert aapl');
    expect(c?.verb).toBe('alert');
    expect(c?.arg).toBe('aapl');
  });

  it('detects the verb with an empty argument', () => {
    expect(detectParamCommand('watch')?.verb).toBe('watch');
  });

  it('returns null for non-commands', () => {
    expect(detectParamCommand('aapl')).toBeNull();
    expect(detectParamCommand('open portfolio')).toBeNull();
    // 'compare' was removed — it has no wired side effect.
    expect(detectParamCommand('compare aapl')).toBeNull();
  });

  it('detects chart as a parameterized verb', () => {
    expect(detectParamCommand('chart aapl')?.verb).toBe('chart');
  });
});

describe('paramCandidates', () => {
  it('suggests curated instruments by prefix', () => {
    const c = paramCandidates('aa');
    expect(c.some((x) => x.value === 'AAPL')).toBe(true);
  });

  it('returns nothing for an empty argument', () => {
    expect(paramCandidates('')).toEqual([]);
  });
});
