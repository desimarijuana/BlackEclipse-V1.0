import { describe, expect, it } from 'vitest';
import { evaluateCoverage, normalizeSymbol, splitSymbols, type StoredSeriesLike } from './preflight';

const series: StoredSeriesLike[] = [
  { symbol: 'BTC-USD', interval: '1d', n: 2400, start: '2019-01-01', end: '2026-10-27', provider: 'jdds' },
  { symbol: 'BTC-USD', interval: '1h', n: 50000, start: '2021-01-01', end: '2026-10-27' },
  { symbol: 'ETH-USD', interval: '1d', n: 2000, start: '2020-01-01', end: '2026-10-27' },
];

describe('data preflight', () => {
  it('normalises the ways a user writes a symbol', () => {
    expect(normalizeSymbol(' btc/usd ')).toBe('BTCUSD');
    expect(normalizeSymbol('BTC-USD')).toBe('BTCUSD');
    expect(normalizeSymbol('btc_usd')).toBe('BTCUSD');
  });

  it('splits and upper-cases a comma separated symbol list', () => {
    expect(splitSymbols(' btc-usd, eth-usd ,, ')).toEqual(['BTC-USD', 'ETH-USD']);
  });

  it('reports ready coverage with bars and a date range', () => {
    const result = evaluateCoverage(series, ['BTC-USD'], '1d');
    expect(result.state).toBe('ready');
    expect(result.headline).toContain('Bars found');
    expect(result.detail).toContain('2,400 bars');
    expect(result.detail).toContain('2019-01-01');
  });

  it('reports partial coverage and keeps the covered half', () => {
    const result = evaluateCoverage(series, ['BTC-USD', 'AAPL'], '1d');
    expect(result.state).toBe('partial');
    expect(result.symbols.find((s) => s.symbol === 'BTC-USD')?.state).toBe('ready');
    expect(result.symbols.find((s) => s.symbol === 'AAPL')?.state).toBe('missing');
  });

  it('suggests the stored intervals when the requested one is absent', () => {
    const result = evaluateCoverage(series, ['BTC-USD'], '4h');
    expect(result.state).toBe('missing');
    const btc = result.symbols[0];
    expect(btc.alternatives.map((alt) => alt.interval)).toEqual(['1h', '1d']);
    expect(result.headline).toContain('No stored 4h bars');
  });

  it('treats an unreadable catalogue as unknown, not as no data', () => {
    const result = evaluateCoverage(null, ['BTC-USD'], '1d');
    expect(result.state).toBe('unknown');
    expect(result.detail).toContain('may still work');
  });

  it('asks for a symbol instead of guessing', () => {
    const result = evaluateCoverage(series, [], '1d');
    expect(result.state).toBe('unknown');
    expect(result.headline).toContain('at least one symbol');
  });

  it('matches symbol case-insensitively', () => {
    expect(evaluateCoverage(series, ['btc-usd'], '1D').state).toBe('ready');
  });
});
