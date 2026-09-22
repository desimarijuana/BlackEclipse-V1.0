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

  it('does NOT silently narrow a generic measure even with a geography (#3)', () => {
    const us = resolveMacroSeries('POLICY_RATE', 'US');
    expect(us.ok).toBe(false);
    if (us.ok) return;
    expect(us.reason).toBe('ambiguous');
    // The candidates are the distinct policy measures (target upper/lower/
    // effective/reverse-repo), never one silently-chosen series.
    expect((us.candidates ?? []).length).toBeGreaterThan(1);
  });

  it('resolves an explicit canonical series id', () => {
    expect(resolveMacroSeries('US:FRED:DFEDTARU').ok).toBe(true);
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

// -- #1: generic aliases never SILENTLY pick one of several measures ---------
describe('generic macro aliases (#1)', () => {
  // Aliases whose meaning spans more than one measure. These must be AMBIGUOUS.
  const MULTI_MEANING = ['CPI', 'INFLATION', 'POLICY_RATE', 'INTEREST_RATE'];

  it('a multi-meaning alias is AMBIGUOUS with named candidates (US)', () => {
    const failures: string[] = [];
    for (const alias of MULTI_MEANING) {
      const r = resolveMacroSeries(alias, 'US');
      if (r.ok) failures.push(`${alias} silently resolved to ${r.identity.id}`);
      else if (r.reason !== 'ambiguous') failures.push(`${alias} -> ${r.reason}, not ambiguous`);
      else if ((r.candidates ?? []).length < 2) failures.push(`${alias} gave < 2 candidates`);
    }
    expect(failures).toEqual([]);
  });

  it('CPI is AMBIGUOUS (headline index vs core index)', () => {
    const r = resolveMacroSeries('CPI', 'US');
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.reason).toBe('ambiguous');
    expect((r.candidates ?? []).length).toBeGreaterThan(1);
  });

  it('a unique-meaning alias resolves to exactly one series', () => {
    const r = resolveMacroSeries('UNEMPLOYMENT', 'US');
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.identity.measure).toBe('unemployment_rate');
  });

  it('a recognised concept with no series is NOT_COVERED (PMI)', () => {
    const r = resolveMacroSeries('PMI', 'US');
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.reason).toBe('not_covered');
  });

  it('an unregistered id is NOT_COVERED (never a silent pass-through)', () => {
    const r = resolveMacroSeries('SOME_RANDOM_SERIES', 'US');
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.reason).toBe('not_covered');
  });

  it('an index series carries its base so the number is meaningful', () => {
    const r = resolveMacroSeries('US:FRED:CPIAUCSL');
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.identity.unit).toBe('index');
    expect(r.identity.unitBase).toBe('1982-84=100');
  });
});
