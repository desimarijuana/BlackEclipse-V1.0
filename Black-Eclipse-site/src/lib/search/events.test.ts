import { describe, it, expect, beforeEach } from 'vitest';
import { resolveEvent, __setEventsForTest } from './events';

// Inject a fake calendar so tests are deterministic and offline.
beforeEach(() => {
  __setEventsForTest([
    { id: 'e1', date: new Date(Date.now() + 2 * 86400000).toISOString(), country: 'US', title: 'Nonfarm Payrolls (NFP)', importance: 'high', actual: null, forecast: null, previous: null },
    { id: 'e2', date: new Date(Date.now() + 5 * 86400000).toISOString(), country: 'US', title: 'Consumer Price Index (CPI)', importance: 'high', actual: null, forecast: null, previous: null },
    { id: 'e3', date: new Date(Date.now() + 9 * 86400000).toISOString(), country: 'US', title: 'FOMC Interest Rate Decision', importance: 'high', actual: null, forecast: null, previous: null },
  ]);
});

describe('resolveEvent', () => {
  it('resolves "next NFP" to the NFP event', () => {
    const ev = resolveEvent('next NFP');
    expect(ev).not.toBeNull();
    expect(ev?.title).toMatch(/payroll|nfp/i);
    expect(ev?.destination.tab).toBe('economics');
    expect(ev?.destination.subroute).toBe('economics.calendar');
  });

  it('resolves CPI to the CPI event', () => {
    const ev = resolveEvent('CPI this month');
    expect(ev?.title).toMatch(/cpi|consumer price/i);
  });

  it('resolves FOMC', () => {
    const ev = resolveEvent('FOMC');
    expect(ev?.title).toMatch(/fomc|interest rate/i);
  });

  it('returns null for non-event queries', () => {
    expect(resolveEvent('AAPL')).toBeNull();
    expect(resolveEvent('portfolio')).toBeNull();
  });
});
