import { describe, expect, it } from 'vitest';
import {
  MAX_RUN_INPUT_BYTES,
  describeRunInput,
  parseRunInputText,
  validateRunInput,
} from './run-input';

describe('run input', () => {
  it('treats empty text as "no input"', () => {
    expect(parseRunInputText('')).toEqual({ ok: true, value: undefined });
    expect(parseRunInputText('  \n ')).toEqual({ ok: true, value: undefined });
  });

  it('parses JSON objects, arrays and primitives', () => {
    expect(parseRunInputText('{"symbol":"AAPL"}')).toEqual({ ok: true, value: { symbol: 'AAPL' } });
    expect(parseRunInputText('[1,2]')).toEqual({ ok: true, value: [1, 2] });
    expect(parseRunInputText('42')).toEqual({ ok: true, value: 42 });
    expect(parseRunInputText('null')).toEqual({ ok: true, value: null });
  });

  it('rejects invalid JSON', () => {
    const result = parseRunInputText('{symbol: AAPL}');
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toMatch(/valid JSON/);
  });

  it('rejects a payload above the size cap', () => {
    const result = validateRunInput({ text: 'x'.repeat(MAX_RUN_INPUT_BYTES + 1) });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toMatch(/bytes or fewer/);
  });

  it('accepts undefined and describes the fallback', () => {
    expect(validateRunInput(undefined)).toEqual({ ok: true, value: undefined });
    expect(describeRunInput(undefined)).toBe('configured payload');
    expect(describeRunInput({ symbol: 'AAPL' })).toBe('{"symbol":"AAPL"}');
  });
});
