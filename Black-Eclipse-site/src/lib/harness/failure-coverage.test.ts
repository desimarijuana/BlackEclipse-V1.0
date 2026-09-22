import { describe, expect, it } from 'vitest';
import {
  makeFailure,
  failureMessage,
  statusForFailure,
  isIdentityFailure,
  type FailureClass,
} from './failure';
import { isCovered, coverageFor, coverageSummary, COVERAGE } from './coverage';

const ALL_CLASSES: FailureClass[] = [
  'ambiguous', 'market_unknown', 'not_found', 'currency_mismatch', 'venue_mismatch',
  'terms_missing', 'not_covered', 'no_data', 'source_failure', 'incomplete',
  'conflict', 'invalid_request',
];

describe('failure contract (B1/B2)', () => {
  it('every class has a distinct, non-empty message', () => {
    const seen = new Set<string>();
    for (const c of ALL_CLASSES) {
      const m = failureMessage(c);
      expect(m.length).toBeGreaterThan(0);
      expect(seen.has(m)).toBe(false);
      seen.add(m);
    }
  });

  it('separates the three availability states (B2)', () => {
    expect(failureMessage('not_covered')).not.toBe(failureMessage('no_data'));
    expect(failureMessage('no_data')).not.toBe(failureMessage('source_failure'));
    expect(failureMessage('source_failure')).toMatch(/fail|unreachable/i);
  });

  it('maps ambiguous/market_unknown to AMBIGUOUS, the rest to UNAVAILABLE', () => {
    expect(statusForFailure('ambiguous')).toBe('AMBIGUOUS');
    expect(statusForFailure('market_unknown')).toBe('AMBIGUOUS');
    expect(statusForFailure('source_failure')).toBe('UNAVAILABLE');
    expect(statusForFailure('terms_missing')).toBe('UNAVAILABLE');
  });

  it('flags identity failures', () => {
    expect(isIdentityFailure('ambiguous')).toBe(true);
    expect(isIdentityFailure('terms_missing')).toBe(true);
    expect(isIdentityFailure('source_failure')).toBe(false);
  });

  it('carries candidate markets on an ambiguous failure', () => {
    const f = makeFailure('ambiguous', undefined, ['US', 'PK']);
    expect(f.candidates).toEqual(['US', 'PK']);
  });
});

describe('declared coverage (C1)', () => {
  it('covers every market in the registry with an ISO currency', () => {
    for (const [market, entry] of Object.entries(COVERAGE)) {
      expect(entry.currency).toMatch(/^[A-Z]{3}$/);
      expect(entry.assetClasses.length).toBeGreaterThan(0);
      expect(entry.sources.length).toBeGreaterThan(0);
      expect(market).toBe(entry.market);
    }
  });

  it('answers coverage questions', () => {
    expect(isCovered('PK', 'equity')).toBe(true);
    expect(isCovered('PK', 'debt')).toBe(true);
    expect(isCovered('PK', 'derivative')).toBe(false);
    expect(isCovered('US', 'derivative')).toBe(true);
    expect(isCovered('CRYPTO', 'crypto')).toBe(true);
    expect(isCovered('ZZ', 'equity')).toBe(false);
  });

  it('exposes a queryable summary', () => {
    const summary = coverageSummary();
    expect(summary.length).toBeGreaterThan(20);
    const pk = coverageFor('PK');
    expect(pk?.currency).toBe('PKR');
  });
});
