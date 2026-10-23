import { describe, expect, it } from 'vitest';
import {
  filingsCheck,
  identityCheck,
  listingCheck,
  normalizeName,
  officialDomainsForMarket,
  overallState,
  quoteCheck,
} from './verification';

const US = officialDomainsForMarket('US');

describe('normalizeName', () => {
  it('drops corporate suffixes and punctuation', () => {
    expect(normalizeName('Apple Inc.')).toBe('apple');
    expect(normalizeName('Emaar Properties PJSC')).toBe('emaar properties pjsc');
  });
});

describe('identityCheck', () => {
  it('verifies against an official host', () => {
    const check = identityCheck(
      [{ title: 'Apple Inc. (AAPL)', url: 'https://www.sec.gov/edgar/browse/?CIK=320193', snippet: 'Apple Inc. AAPL' }],
      'AAPL',
      'Apple Inc.',
      US,
    );
    expect(check.state).toBe('VERIFIED');
    expect(check.evidence[0].official).toBe(true);
  });

  it('corroborates with two non-official results', () => {
    const check = identityCheck(
      [
        { title: 'AAPL quote', url: 'https://example.com/aapl', snippet: 'Apple AAPL price' },
        { title: 'Apple overview', url: 'https://example.org/apple', snippet: 'Apple Inc AAPL' },
      ],
      'AAPL',
      'Apple Inc.',
      US,
    );
    expect(check.state).toBe('CORROBORATED');
  });

  it('is unavailable with no matching results', () => {
    const check = identityCheck([], 'AAPL', 'Apple Inc.', US);
    expect(check.state).toBe('UNAVAILABLE');
  });
});

describe('listingCheck and filingsCheck', () => {
  it('verifies official listing and filing results', () => {
    const listing = listingCheck([], [
      { title: 'AAPL on Nasdaq', url: 'https://www.nasdaq.com/market-activity/stocks/aapl', snippet: 'AAPL' },
    ], 'AAPL', 'US', US);
    const filings = filingsCheck([], [
      { title: 'AAPL 10-K', url: 'https://www.sec.gov/Archives/aapl-10k', snippet: 'Apple AAPL annual report 10-K' },
    ], 'AAPL', US);
    expect(listing.state).toBe('VERIFIED');
    expect(filings.state).toBe('VERIFIED');
  });
});

describe('quoteCheck', () => {
  it('corroborates a quote from a search snippet without calling it verified', () => {
    const check = quoteCheck(
      [{ title: 'AAPL stock price', url: 'https://example.com/aapl', snippet: 'AAPL is trading at $195.12 today' }],
      'AAPL',
      195,
      US,
    );
    expect(check.state).toBe('CORROBORATED');
  });

  it('does not corroborate a mismatched quote', () => {
    const check = quoteCheck(
      [{ title: 'AAPL stock price', url: 'https://example.com/aapl', snippet: 'AAPL is trading at $150.00 today' }],
      'AAPL',
      195,
      US,
    );
    expect(check.state).toBe('UNVERIFIED');
  });
});

describe('overallState', () => {
  it('requires every check to be verified for VERIFIED', () => {
    expect(overallState([
      { id: 'identity', label: 'i', state: 'VERIFIED', detail: '', evidence: [] },
      { id: 'quote', label: 'q', state: 'CORROBORATED', detail: '', evidence: [] },
    ])).toBe('CORROBORATED');
  });
});
