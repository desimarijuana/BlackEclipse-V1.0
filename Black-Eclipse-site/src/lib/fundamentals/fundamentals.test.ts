import { describe, it, expect } from 'vitest';
import { cagr, buildGrowth, assembleSnapshot } from './compute';
import { derivePeriodRatios, fiscalYearOf, normalizePeriods } from './normalize';
import { parseYahooFundamentals } from './providers/yahoo';
import { parseSecCompanyFacts } from './providers/sec-edgar';
import { fmtCompact, fmtPercent, fmtMetricValue, fiscalLabel, changeTone, metricTone } from './format';
import type { FundamentalPeriod, ProviderFundamentals } from './types';

// ── Helpers ────────────────────────────────────────────────────────────────

function period(over: Partial<FundamentalPeriod> = {}): FundamentalPeriod {
  return {
    endDate: '2024-12-31',
    fiscalYear: 2024,
    revenue: null, costOfRevenue: null, grossProfit: null, operatingIncome: null,
    ebitda: null, netIncome: null, eps: null, taxProvision: null, pretaxIncome: null,
    researchDevelopment: null, interestExpense: null, operatingCashFlow: null,
    capex: null, freeCashFlow: null, dividendsPaid: null, depreciation: null,
    totalAssets: null, totalLiabilities: null, totalEquity: null, totalDebt: null,
    netDebt: null, cash: null, currentAssets: null, currentLiabilities: null,
    inventory: null, accountsReceivable: null, sharesOutstanding: null,
    grossMargin: null, operatingMargin: null, netMargin: null, roe: null, roa: null,
    roic: null, debtToEquity: null, currentRatio: null, quickRatio: null,
    ...over,
  };
}

// ── CAGR ───────────────────────────────────────────────────────────────────

describe('cagr', () => {
  it('computes compound growth', () => {
    expect(cagr(100, 121, 2)).toBeCloseTo(0.1, 6);
  });
  it('returns null for non-positive start', () => {
    expect(cagr(0, 100, 2)).toBeNull();
    expect(cagr(-5, 100, 2)).toBeNull();
  });
  it('returns null for zero years', () => {
    expect(cagr(100, 200, 0)).toBeNull();
  });
});

// ── Ratio derivation ───────────────────────────────────────────────────────

describe('derivePeriodRatios', () => {
  it('derives margins, returns and liquidity', () => {
    const p = derivePeriodRatios({
      ...period(),
      revenue: 1000, grossProfit: 400, operatingIncome: 200, netIncome: 100,
      totalAssets: 2000, totalEquity: 500, totalDebt: 500,
      currentAssets: 300, currentLiabilities: 150, inventory: 50,
    });
    expect(p.grossMargin).toBeCloseTo(0.4);
    expect(p.operatingMargin).toBeCloseTo(0.2);
    expect(p.netMargin).toBeCloseTo(0.1);
    expect(p.roe).toBeCloseTo(0.2);
    expect(p.roa).toBeCloseTo(0.05);
    expect(p.roic).toBeCloseTo(0.2); // 200 / (500+500)
    expect(p.debtToEquity).toBeCloseTo(1);
    expect(p.currentRatio).toBeCloseTo(2);
    expect(p.quickRatio).toBeCloseTo(250 / 150);
  });

  it('does not divide by zero', () => {
    const p = derivePeriodRatios({ ...period(), netIncome: 10, totalEquity: 0 });
    expect(p.roe).toBeNull();
  });
});

describe('fiscalYearOf', () => {
  it('reads the year from an ISO date', () => {
    expect(fiscalYearOf('2025-09-30')).toBe(2025);
  });
});

// ── Normalization ──────────────────────────────────────────────────────────

describe('normalizePeriods', () => {
  it('sorts oldest first and dedupes by end date', () => {
    const provider: ProviderFundamentals = {
      provider: 'yahoo', symbol: 'X', currency: 'USD', company: {},
      periods: [
        period({ endDate: '2025-12-31', revenue: 2 }),
        period({ endDate: '2023-12-31', revenue: 9 }),
        period({ endDate: '2025-12-31', revenue: 3 }), // later wins
      ],
      retrievedAt: '2026-01-01T00:00:00.000Z',
    };
    const out = normalizePeriods(provider);
    expect(out.map((p) => p.endDate)).toEqual(['2023-12-31', '2025-12-31']);
    expect(out[1].revenue).toBe(3);
  });
});

// ── Yahoo provider parse ───────────────────────────────────────────────────

describe('parseYahooFundamentals', () => {
  it('normalizes bridge output and reads percent fields as fractions', () => {
    const out = parseYahooFundamentals(
      {
        currency: 'USD',
        info: {
          longName: 'Apple Inc.', sector: 'Technology',
          trailingPE: 30, trailingAnnualDividendYield: 0.005,
          heldPercentInstitutions: 0.66, currentPrice: 200, marketCap: 3e12,
        },
        periods: [
          { endDate: '2024-09-30', revenue: 400e9, grossProfit: 180e9, netIncome: 100e9, eps: 6.5 },
        ],
      },
      'AAPL'
    );
    expect(out).not.toBeNull();
    expect(out!.company.name).toBe('Apple Inc.');
    expect(out!.periods).toHaveLength(1);
    expect(out!.valuation?.trailingPE).toBe(30);
    expect(out!.valuation?.dividendYield).toBe(0.005);
    expect(out!.ownership?.institutionalPercent).toBe(0.66);
  });

  it('returns null when there is no data', () => {
    expect(parseYahooFundamentals({ periods: [], info: {} }, 'X')).toBeNull();
  });
});

// ── SEC provider parse ─────────────────────────────────────────────────────

describe('parseSecCompanyFacts', () => {
  it('extracts annual values and derives EBITDA/FCF', () => {
    const facts = {
      entityName: 'Test Co',
      facts: {
        'us-gaap': {
          Revenues: {
            units: { USD: [
              { start: '2023-01-01', end: '2023-12-31', val: 1000, form: '10-K', fp: 'FY', filed: '2024-02-01' },
              { start: '2024-01-01', end: '2024-12-31', val: 1200, form: '10-K', fp: 'FY', filed: '2025-02-01' },
            ] },
          },
          OperatingIncomeLoss: {
            units: { USD: [
              { start: '2024-01-01', end: '2024-12-31', val: 300, form: '10-K', fp: 'FY', filed: '2025-02-01' },
            ] },
          },
          DepreciationDepletionAndAmortization: {
            units: { USD: [
              { start: '2024-01-01', end: '2024-12-31', val: 50, form: '10-K', fp: 'FY', filed: '2025-02-01' },
            ] },
          },
          NetCashProvidedByUsedInOperatingActivities: {
            units: { USD: [
              { start: '2024-01-01', end: '2024-12-31', val: 400, form: '10-K', fp: 'FY', filed: '2025-02-01' },
            ] },
          },
          PaymentsToAcquirePropertyPlantAndEquipment: {
            units: { USD: [
              { start: '2024-01-01', end: '2024-12-31', val: -100, form: '10-K', fp: 'FY', filed: '2025-02-01' },
            ] },
          },
        },
      },
    };
    const out = parseSecCompanyFacts(facts, 'TEST');
    expect(out).not.toBeNull();
    expect(out!.periods).toHaveLength(2);
    const latest = out!.periods[1];
    expect(latest.revenue).toBe(1200);
    expect(latest.ebitda).toBe(350); // 300 + 50
    expect(latest.freeCashFlow).toBe(300); // 400 + (-100)
  });

  it('returns null when nothing usable is present', () => {
    expect(parseSecCompanyFacts({ facts: {} }, 'X')).toBeNull();
  });

  it('unions tags when the preferred tag stops being reported (NVDA case)', () => {
    // The preferred revenue tag stops after FY2022; the fallback continues.
    // The latest period must still carry revenue, not a stale/blank value.
    const facts = {
      facts: {
        'us-gaap': {
          RevenueFromContractWithCustomerExcludingAssessedTax: {
            units: { USD: [
              { start: '2021-02-01', end: '2022-01-30', val: 26914, form: '10-K', fp: 'FY', filed: '2022-03-18' },
            ] },
          },
          Revenues: {
            units: { USD: [
              { start: '2021-02-01', end: '2022-01-30', val: 26914, form: '10-K', fp: 'FY', filed: '2022-03-18' },
              { start: '2025-01-27', end: '2026-01-25', val: 215938, form: '10-K', fp: 'FY', filed: '2026-02-25' },
            ] },
          },
        },
      },
    };
    const out = parseSecCompanyFacts(facts, 'NVDA');
    expect(out).not.toBeNull();
    const latest = out!.periods[out!.periods.length - 1];
    expect(latest.endDate).toBe('2026-01-25');
    expect(latest.revenue).toBe(215938);
  });

  it('ignores sub-annual windows that share a fiscal end date', () => {
    // A 10-K embeds Q4 (91d) and FY (364d) facts ending on the same day.
    const facts = {
      facts: {
        'us-gaap': {
          Revenues: {
            units: { USD: [
              { start: '2025-09-28', end: '2025-12-27', val: 1000, form: '10-K', fp: 'FY', filed: '2026-02-01' },
              { start: '2024-12-29', end: '2025-12-27', val: 9000, form: '10-K', fp: 'FY', filed: '2026-02-01' },
            ] },
          },
        },
      },
    };
    const out = parseSecCompanyFacts(facts, 'TEST');
    expect(out!.periods).toHaveLength(1);
    expect(out!.periods[0].revenue).toBe(9000);
  });
});

// ── Insights ───────────────────────────────────────────────────────────────

describe('synthesizeInsights', () => {
  it('flags elevated leverage and negative margins from real inputs', () => {
    // Ratios are normally derived by normalizePeriods; use it so the snapshot
    // matches the real provider → normalization pipeline.
    const periods = normalizePeriods({
      provider: 'sec-edgar', symbol: 'X', currency: 'USD', company: {},
      periods: [
        period({ endDate: '2023-12-31', revenue: 1000 }),
        period({ endDate: '2024-12-31', revenue: 800, netIncome: -100, totalEquity: 100, totalDebt: 900, ebitda: 100, netDebt: 800 }),
      ],
      retrievedAt: '2026-01-01T00:00:00.000Z',
    });
    const snapshot = assembleSnapshot({
      symbol: 'X', market: 'US', currency: 'USD',
      company: { name: null, sector: null, industry: null, country: null, website: null, description: null, employees: null, exchange: null },
      periods, growth: buildGrowth(periods), quote: null,
      valuation: {
        trailingPE: null, forwardPE: null, peg: null, priceToSales: null, priceToBook: null,
        evToEbitda: null, evToRevenue: null, fcfYield: null, dividendYield: null,
        dividendRate: null, payoutRatio: null, trailingEps: null, forwardEps: null,
      },
      valuationSource: 'derived',
      earnings: { history: [], estimates: [] }, ownership: null, timeline: [],
      primary: 'sec-edgar', contributors: ['sec-edgar'], provenance: 'LIVE',
      retrievedAt: '2026-01-01T00:00:00.000Z', fiscalYearEnd: '2024-12-31',
    });
    const ids = snapshot.insights.map((i) => i.id);
    expect(ids).toContain('leverage');
    expect(ids).toContain('net-margin');
    const margin = snapshot.insights.find((i) => i.id === 'net-margin')!;
    expect(margin.tone).toBe('negative');
    const rev = snapshot.metrics.find((m) => m.key === 'revenueGrowth')!;
    expect(rev.value).toBeCloseTo(-0.2);
  });
});

// ── Formatting ─────────────────────────────────────────────────────────────

describe('format', () => {
  it('formats compact large numbers', () => {
    expect(fmtCompact(4.16e11)).toBe('416.00B');
    expect(fmtCompact(4.9e12)).toBe('4.90T');
    expect(fmtCompact(null)).toBe('—');
  });

  it('treats percent metrics as fractions', () => {
    expect(fmtPercent(0.269)).toBe('26.9%');
    expect(fmtMetricValue(0.269, 'percent')).toBe('26.9%');
    expect(fmtMetricValue(38.5, 'ratio')).toBe('38.50×');
  });

  it('labels fiscal years', () => {
    expect(fiscalLabel('2025-09-30')).toBe('FY2025');
  });

  it('tones changes and polarizes metrics', () => {
    expect(changeTone(0.1)).toBe('up');
    expect(changeTone(-0.1)).toBe('down');
    expect(metricTone({ key: 'debt', label: '', value: 100, unit: 'currency', period: null, yoy: null, source: 'derived', updatedAt: null, polarity: 'lower' })).toBe('down');
    expect(metricTone({ key: 'revenue', label: '', value: 100, unit: 'currency', period: null, yoy: null, source: 'derived', updatedAt: null, polarity: 'higher' })).toBe('up');
  });
});
