import { describe, expect, it } from 'vitest';
import { parseStooqCsv, stooqSymbol } from './stooq-chart';

describe('stooqSymbol', () => {
  it('maps US tickers to the Stooq suffix', () => {
    expect(stooqSymbol('AAPL', 'US')).toBe('aapl.us');
    expect(stooqSymbol('^SPX', 'US')).toBe('^spx');
    expect(stooqSymbol('AAPL', 'IN')).toBeNull();
  });
});

describe('parseStooqCsv', () => {
  it('parses real OHLCV rows and sorts them', () => {
    const bars = parseStooqCsv(
      'Date,Open,High,Low,Close,Volume\n2026-10-22,190,196,189,195,1000\n2026-10-21,188,191,187,190,900\n',
    );
    expect(bars).toHaveLength(2);
    expect(bars[0].date).toBe('2026-10-21');
    expect(bars[1].close).toBe(195);
    expect(bars[1].volume).toBe(1000);
  });

  it('returns nothing for an error payload', () => {
    expect(parseStooqCsv('Exceeded the daily hits limit')).toEqual([]);
  });
});
