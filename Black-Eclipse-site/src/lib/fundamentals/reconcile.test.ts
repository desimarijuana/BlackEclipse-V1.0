import { describe, it, expect } from 'vitest';
import type { FundamentalPeriod } from './types';
import { reconcilePeriods } from './reconcile';

function period(endDate: string, over: Partial<FundamentalPeriod>): FundamentalPeriod {
  return {
    endDate, fiscalYear: null,
    revenue: null, costOfRevenue: null, grossProfit: null, operatingIncome: null, ebitda: null,
    netIncome: null, eps: null, taxProvision: null, pretaxIncome: null, researchDevelopment: null,
    interestExpense: null, operatingCashFlow: null, capex: null, freeCashFlow: null, dividendsPaid: null,
    depreciation: null, totalAssets: null, totalLiabilities: null, totalEquity: null, totalDebt: null,
    netDebt: null, cash: null, currentAssets: null, currentLiabilities: null, inventory: null,
    accountsReceivable: null, sharesOutstanding: null,
    grossMargin: null, operatingMargin: null, netMargin: null, roe: null, roa: null, roic: null,
    debtToEquity: null, currentRatio: null, quickRatio: null,
    ...over,
  };
}

describe('reconcilePeriods', () => {
  it('is silent when only one source has a metric', () => {
    const c = reconcilePeriods([
      { provider: 'eclipse-filings', periods: [period('2025-06-30', { revenue: 1e9 })] },
      { provider: 'yahoo', periods: [period('2025-06-30', { netIncome: 5e7 })] },
    ]);
    expect(c).toEqual([]);
  });

  it('flags a material disagreement for the same metric+period', () => {
    const c = reconcilePeriods([
      { provider: 'eclipse-filings', periods: [period('2025-06-30', { revenue: 1_000_000_000 })] },
      { provider: 'yahoo', periods: [period('2025-06-30', { revenue: 800_000_000 })] },
    ]);
    expect(c).toHaveLength(1);
    expect(c[0].metric).toBe('revenue');
    expect(c[0].endDate).toBe('2025-06-30');
    expect(c[0].maxDeltaPct).toBeCloseTo(20, 0);
  });

  it('absorbs sub-threshold rounding differences (PSX thousands vs exact rupees)', () => {
    const c = reconcilePeriods([
      { provider: 'eclipse-filings', periods: [period('2025-06-30', { revenue: 1_000_000_000 })] },
      { provider: 'sec-edgar', periods: [period('2025-06-30', { revenue: 1_005_000_000 })] },
    ]);
    expect(c).toEqual([]);
  });

  it('does not compare different periods', () => {
    const c = reconcilePeriods([
      { provider: 'eclipse-filings', periods: [period('2025-06-30', { revenue: 1e9 })] },
      { provider: 'yahoo', periods: [period('2024-06-30', { revenue: 5e8 })] },
    ]);
    expect(c).toEqual([]);
  });

  it('sorts by largest disagreement first', () => {
    const c = reconcilePeriods([
      { provider: 'a' as never, periods: [period('2025-06-30', { revenue: 100, netIncome: 100 })] },
      { provider: 'b' as never, periods: [period('2025-06-30', { revenue: 90, netIncome: 10 })] },
    ]);
    expect(c[0].metric).toBe('netIncome');
    expect(c).toHaveLength(2);
  });
});
