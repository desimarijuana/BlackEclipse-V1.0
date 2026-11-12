import { describe, expect, it } from 'vitest';
import { en } from '@/lib/i18n/dictionaries/en';
import {
  evolutionDriftHistoryPath,
  evolutionDriftScopesPath,
  evolutionRotationPath,
  evolutionStateKey,
  metricLabel,
} from './evolution-client';

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

  it('drift proxy paths carry the full policy', () => {
    const history = evolutionDriftHistoryPath({
      scope: 'eclipse-agent', window: 30, baseline: 100,
      threshold: 0.1, minSamples: 10, limit: 12, step: 30,
    });
    expect(history).toContain('/evolution/drift/history?');
    expect(history).toContain('scope=eclipse-agent');
    expect(history).toContain('minSamples=10');
    expect(history).toContain('limit=12');

    const scopes = evolutionDriftScopesPath({ window: 20, baseline: 50, minSamples: 5 });
    expect(scopes).toBe('/evolution/drift/scopes?window=20&baseline=50&minSamples=5');
    expect(evolutionDriftScopesPath()).toBe('/evolution/drift/scopes');
    expect(evolutionDriftScopesPath({ includeGlobal: false }))
      .toBe('/evolution/drift/scopes?includeGlobal=false');
  });

  it('an unmeasurable metric reads "not measured yet", never 0', () => {
    expect(metricLabel('UNKNOWN')).toBe('not measured yet');
    expect(metricLabel(0)).toBe('0');
    expect(metricLabel(0.5)).toBe('0.5');
  });

  it('the rotation preview path carries the quarter and count', () => {
    expect(evolutionRotationPath({ quarter: '2026Q4', count: 4 }))
      .toBe('/evolution/corpus/rotation?quarter=2026Q4&count=4');
    expect(evolutionRotationPath({ quarter: '2026Q4' }))
      .toBe('/evolution/corpus/rotation?quarter=2026Q4');
    expect(evolutionRotationPath()).toBe('/evolution/corpus/rotation');
  });
});
