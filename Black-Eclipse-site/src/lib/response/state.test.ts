import { describe, expect, it } from 'vitest';
import { parseResponsePayload } from './contract';
import { computeEnvelopeValues, initialEnvelopeValues } from './state';

function state(raw: unknown) {
  return parseResponsePayload(raw).state;
}
function computed(raw: unknown) {
  return parseResponsePayload(raw).computed;
}

describe('initialEnvelopeValues', () => {
  it('reads each state var default', () => {
    const vars = state({ state: [{ id: 'x', value: 4 }, { id: 'y', value: 2 }], blocks: [] });
    expect(initialEnvelopeValues(vars)).toEqual({ x: 4, y: 2 });
  });
});

describe('computeEnvelopeValues', () => {
  it('evaluates computed over state and earlier computed (ordered)', () => {
    const raw = {
      state: [{ id: 'x', value: 4 }],
      computed: [{ id: 'double', expression: 'x * 2' }, { id: 'plus', expression: 'double + 1' }],
      blocks: [],
    };
    const out = computeEnvelopeValues(state(raw), computed(raw), { x: 4 });
    expect(out.double).toBe(8);
    expect(out.plus).toBe(9);
  });

  it('omits a computed whose expression cannot resolve (division by zero)', () => {
    const raw = {
      state: [{ id: 'x', value: 0 }],
      computed: [{ id: 'ratio', expression: '1 / x' }],
      blocks: [],
    };
    const out = computeEnvelopeValues(state(raw), computed(raw), { x: 0 });
    expect(out.ratio).toBeUndefined();
  });

  it('applies user overrides to state', () => {
    const raw = { state: [{ id: 'x', value: 1 }], computed: [{ id: 'sq', expression: 'x * x' }], blocks: [] };
    const out = computeEnvelopeValues(state(raw), computed(raw), { x: 5 });
    expect(out.sq).toBe(25);
  });
});
