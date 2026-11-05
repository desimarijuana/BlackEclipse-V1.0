import { describe, it, expect } from 'vitest';
import { fmtPrice, fmtDateTime, fmtClock, fmtR, fmtMoney } from './format';

describe('journal formatting', () => {
  it('trims float noise from prices without losing FX precision', () => {
    expect(fmtPrice(3932.2900000000004)).toBe('3932.29');
    expect(fmtPrice(1.11621)).toBe('1.11621');
    expect(fmtPrice(149.123)).toBe('149.123');
    expect(fmtPrice(null)).toBe('—');
    expect(fmtPrice(Number.NaN)).toBe('—');
  });

  it('renders timestamps in UTC with the clock, not only the day', () => {
    expect(fmtDateTime('2026-11-03T14:05:00.000Z')).toBe('2026-11-03 14:05');
    expect(fmtClock('2026-11-03T00:00:00.000Z')).toBe('00:00');
    expect(fmtDateTime(null)).toBe('—');
    expect(fmtDateTime('not-a-date')).toBe('—');
  });

  it('keeps the existing signed R and money formats', () => {
    expect(fmtR(2.345)).toBe('+2.35R');
    expect(fmtR(-1)).toBe('-1.00R');
    expect(fmtMoney(-12.5)).toBe('-$12.50');
  });
});
