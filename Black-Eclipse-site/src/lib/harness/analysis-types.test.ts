import { describe, expect, it } from 'vitest';
import {
  coerceComputedResult,
  provenanceStatusKey,
  renderComputedValue,
} from './analysis-types';

// The invariant this phase exists to protect: a computed number can never be
// shown as retrieved, and a computed number with no provenance renders
// UNAVAILABLE — never a bare value. No React testing library is installed; the
// logic lives in `analysis-types.ts`, so the assertion belongs there.

describe('computed vs retrieved', () => {
  it('chooses a distinct status word per kind', () => {
    expect(provenanceStatusKey({ kind: 'computed', label: 'L', detail: 'D' })).toBe('analysis.computed');
    expect(provenanceStatusKey({ kind: 'retrieved', label: 'L', detail: 'D' })).toBe('analysis.retrieved');
    expect(provenanceStatusKey(null)).toBe('analysis.unavailable');
  });

  it('renders a computed value only with a computed provenance', () => {
    expect(renderComputedValue(42, { kind: 'computed', label: 'L', detail: 'D' })).toEqual({
      status: 'computed',
      value: 42,
    });
  });

  it('fails closed: a value with no provenance renders unavailable', () => {
    expect(renderComputedValue(42, null)).toEqual({ status: 'unavailable', value: null });
  });

  it('coerces a malformed provenance to null (which renders unavailable)', () => {
    const result = coerceComputedResult({ status: 'ok', provenance: { kind: 'bogus' }, outputs: {} });
    expect(result?.provenance).toBeNull();
    expect(provenanceStatusKey(result?.provenance ?? null)).toBe('analysis.unavailable');
  });

  it('ignores a blob that is not a computed result', () => {
    expect(coerceComputedResult(null)).toBeNull();
    expect(coerceComputedResult({ status: 'nope' })).toBeNull();
  });

  it('keeps a computed result through coercion', () => {
    const result = coerceComputedResult({
      status: 'ok',
      provenance: { kind: 'computed', label: 'Worked out by Eclipse', detail: 'Q1 vs Q2' },
      outputs: { changePct: 20 },
      artifacts: [{ name: 'out.json', path: 'p', sha256: 'a'.repeat(64), bytes: 3, mediaType: 'application/json' }],
    });
    expect(result?.provenance?.kind).toBe('computed');
    expect(result?.outputs.changePct).toBe(20);
    expect(result?.artifacts).toHaveLength(1);
  });
});
