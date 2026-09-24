import { describe, it, expect } from 'vitest';
import { ttlForInterval, DAILY_HISTORY_TTL_MS } from './price-history-ttl';

describe('ttlForInterval', () => {
  it('gives intraday intervals a short lifetime', () => {
    expect(ttlForInterval('1m')).toBe(30_000);
    expect(ttlForInterval('5m')).toBe(60_000);
    expect(ttlForInterval('15m')).toBeLessThan(DAILY_HISTORY_TTL_MS);
    expect(ttlForInterval('30m')).toBeLessThan(DAILY_HISTORY_TTL_MS);
    expect(ttlForInterval('60m')).toBeLessThan(DAILY_HISTORY_TTL_MS);
  });

  it('keeps daily and above on the long default', () => {
    expect(ttlForInterval('1d')).toBe(DAILY_HISTORY_TTL_MS);
    expect(ttlForInterval('1wk')).toBe(DAILY_HISTORY_TTL_MS);
    expect(ttlForInterval('1mo')).toBe(DAILY_HISTORY_TTL_MS);
    expect(ttlForInterval('anything-unknown')).toBe(DAILY_HISTORY_TTL_MS);
  });

  it('never returns a non-positive or sub-second TTL', () => {
    for (const i of ['1m', '5m', '15m', '30m', '60m', '1d', '1wk', '1mo', 'x']) {
      expect(ttlForInterval(i)).toBeGreaterThanOrEqual(30_000);
    }
  });
});
