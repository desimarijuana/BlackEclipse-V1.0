import { describe, expect, it } from 'vitest';
import { en } from '@/lib/i18n/dictionaries/en';
import { evolutionStateKey, metricLabel } from './evolution-client';

// The invariant this phase exists to protect: an unmeasurable metric reads "not
// measured yet", never a fabricated zero, and every candidate state has a plain
// sentence. The state word is chosen in ONE place (`evolutionStateKey`).

const STATES = [
  'inert', 'proposed', 'refused', 'evaluating', 'evaluated_ok',
  'evaluated_bad', 'canaried', 'activated', 'rolled_back', 'dismissed',
] as const;

describe('evolution surface', () => {
  it('every candidate state resolves to a plain sentence key', () => {
    for (const state of STATES) {
      const key = evolutionStateKey(state) as keyof typeof en;
      expect(en[key], state).toBeTruthy();
    }
  });

  it('an unmeasurable metric reads "not measured yet", never 0', () => {
    expect(metricLabel('UNKNOWN')).toBe('not measured yet');
    expect(metricLabel(0)).toBe('0');
    expect(metricLabel(0.5)).toBe('0.5');
  });
});
