import { describe, expect, it } from 'vitest';
import { resolveMacroSeries, defaultSourceForGeography } from './macro-identity';

// ── A8: macro series identity ───────────────────────────────────────────────
describe('resolveMacroSeries (A8)', () => {
  it('resolves a canonical series id', () => {
    const r = resolveMacroSeries('US:FRED:DFEDTARU');
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.identity.measure).toBe('fed_funds_target_upper');
    expect(r.identity.geography).toBe('US');
  });

  it('distinguishes the policy target from the reverse-repo ceiling', () => {
    const target = resolveMacroSeries('US:FRED:DFEDTARU');
    const rrp = resolveMacroSeries('US:FRED:RRPONTSYD');
    expect(target.ok && rrp.ok).toBe(true);
    if (!target.ok || !rrp.ok) return;
    expect(target.identity.measure).not.toBe(rrp.identity.measure);
    expect(target.identity.frequency).toBe('daily');
  });

  it('never defaults a generic measure to the US series', () => {
    const r = resolveMacroSeries('POLICY_RATE');
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.reason).toBe('ambiguous');
    expect(r.candidates?.some((c) => c.startsWith('US:'))).toBe(true);
  });

  it('scopes a generic measure once a geography is given', () => {
    const us = resolveMacroSeries('POLICY_RATE', 'US');
    expect(us.ok).toBe(true);
    if (us.ok) expect(us.identity.geography).toBe('US');
  });

  it('routes a non-US series to a non-US source', () => {
    const ecb = resolveMacroSeries('EA:ECB:DEPOSIT');
    expect(ecb.ok).toBe(true);
    if (!ecb.ok) return;
    expect(ecb.identity.sourceId).not.toBe('fred-analytics');
    expect(ecb.identity.geography).toBe('EA');
  });

  it('reports not_covered for a generic measure with no registered series', () => {
    const r = resolveMacroSeries('POLICY_RATE', 'PK');
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.reason).toBe('not_covered');
  });

  it('carries adjustment + frequency so SA/NSA cannot collide', () => {
    const sa = resolveMacroSeries('US:FRED:CPIAUCSL');
    expect(sa.ok).toBe(true);
    if (sa.ok) {
      expect(sa.identity.adjustment).toBe('sa');
      expect(sa.identity.frequency).toBe('monthly');
    }
  });

  it('exposes a default source per geography for coverage checks', () => {
    expect(defaultSourceForGeography('US')).toBe('fred-analytics');
    expect(defaultSourceForGeography('EA')).toBe('ecb');
    expect(defaultSourceForGeography('ZZ')).toBeNull();
  });
});
