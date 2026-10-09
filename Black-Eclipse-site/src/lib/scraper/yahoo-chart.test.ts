import { describe, it, expect } from 'vitest';
import { selectChartPrice } from './yahoo-chart';

// Regression for the OGDC-class defect: Yahoo returned a bogus
// `regularMarketPrice` (131.87) while the real latest bar close was 315.91.
describe('selectChartPrice', () => {
  it('uses the meta price when it agrees with the newest bar', () => {
    expect(selectChartPrice(316.0, 315.9)).toBe(316.0);
  });

  it('rejects an implausible meta price and uses the real bar close', () => {
    // OGDC.KA: meta 131.87 vs a real close of 315.91 (~58% off) is not trusted.
    expect(selectChartPrice(131.87, 315.91)).toBe(315.91);
  });

  it('falls back to the bar when meta is missing/zero/NaN', () => {
    expect(selectChartPrice(null, 42)).toBe(42);
    expect(selectChartPrice(undefined, 42)).toBe(42);
    expect(selectChartPrice(0, 42)).toBe(42);
    expect(selectChartPrice(Number.NaN, 42)).toBe(42);
  });

  it('tolerates a small intraday divergence', () => {
    // A 4% divergence is within tolerance → keep meta (the live tick).
    expect(selectChartPrice(104, 100)).toBe(104);
  });

  it('never returns a non-positive value when a real bar exists', () => {
    expect(selectChartPrice(-5, 100)).toBe(100);
  });
});
