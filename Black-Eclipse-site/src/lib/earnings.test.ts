import { describe, expect, it } from 'vitest';
import { parseEarningsCsv } from './earnings';

describe('parseEarningsCsv', () => {
  it('parses the Alpha Vantage EARNINGS_CALENDAR shape', () => {
    const csv = [
      'symbol,name,reportDate,fiscalDateEnding,estimate,currency,timeOfTheDay',
      'AAPL,"Apple Inc",2026-09-24,2026-09-30,1.45,USD,AMC',
      'MSFT,"Microsoft Corporation",2026-09-25,,2.90,USD,bmo',
    ].join('\n');
    const rows = parseEarningsCsv(csv);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ symbol: 'AAPL', name: 'Apple Inc', date: '2026-09-24', time: 'AMC' });
    expect(rows[1]).toMatchObject({ symbol: 'MSFT', date: '2026-09-25', time: 'BMO' });
    expect(rows[0].epsEstimate).toBe(1.45);
    expect(rows[1].epsEstimate).toBe(2.9);
  });

  it('handles quoted names with embedded commas', () => {
    const csv = [
      'symbol,name,reportDate,timeOfTheDay',
      'ABC,"Acme, Inc.",2026-09-24,',
    ].join('\n');
    const rows = parseEarningsCsv(csv);
    expect(rows[0].name).toBe('Acme, Inc.');
    expect(rows[0].time).toBeNull();
  });

  it('maps the real Alpha Vantage pre-market / post-market session values', () => {
    const csv = [
      'symbol,name,reportDate,fiscalDateEnding,estimate,currency,timeOfTheDay',
      'MSFT,"Microsoft, Inc.",2026-09-25,2026-06-30,2.9,USD,pre-market',
      'ABVX,ABIVAX SA,2026-09-21,2026-06-30,-1.08,USD,post-market',
    ].join('\n');
    const rows = parseEarningsCsv(csv);
    expect(rows[0].time).toBe('BMO');
    expect(rows[1].time).toBe('AMC');
    expect(rows[0].epsEstimate).toBe(2.9);
  });

  it('returns [] for a non-CSV / empty payload', () => {
    expect(parseEarningsCsv('')).toEqual([]);
    expect(parseEarningsCsv('symbol,name')).toEqual([]);
    expect(parseEarningsCsv('{"Information":"rate limit"}')).toEqual([]);
  });

  it('drops rows without a symbol or date, and nulls missing EPS', () => {
    const csv = [
      'symbol,name,reportDate,estimatedEPS',
      ',NoSymbol,2026-09-24,1',
      'NOE,No Date,,2',
      'OK,Fine,2026-09-24,-',
    ].join('\n');
    const rows = parseEarningsCsv(csv);
    // 'symbol,name' header doesn't match reportDate? It does → both bad rows dropped.
    expect(rows.map(r => r.symbol)).toEqual(['OK']);
    expect(rows[0].epsEstimate).toBeNull();
  });
});
