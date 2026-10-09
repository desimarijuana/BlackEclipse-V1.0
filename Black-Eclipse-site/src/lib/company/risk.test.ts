import { describe, it, expect } from 'vitest';
import type { FundamentalPeriod } from '@/lib/fundamentals/types';
import { computeCompanyRisk } from './risk';
import type { TechnicalSnapshot } from './technical';

function period(over: Partial<FundamentalPeriod>): FundamentalPeriod {
  return {
    endDate: '2025-12-31', fiscalYear: 2025,
    revenue: null, costOfRevenue: null, grossProfit: null, operatingIncome: null,
    ebitda: null, netIncome: null, eps: null, taxProvision: null, pretaxIncome: null,
    researchDevelopment: null, interestExpense: null,
    operatingCashFlow: null, capex: null, freeCashFlow: null, dividendsPaid: null, depreciation: null,
    totalAssets: null, totalLiabilities: null, totalEquity: null, totalDebt: null, netDebt: null,
    cash: null, currentAssets: null, currentLiabilities: null, inventory: null, accountsReceivable: null,
    sharesOutstanding: null,
    grossMargin: null, operatingMargin: null, netMargin: null, roe: null, roa: null, roic: null,
    debtToEquity: null, currentRatio: null, quickRatio: null,
    ...over,
  };
}

const tech = (over: Partial<TechnicalSnapshot> = {}): TechnicalSnapshot => ({
  bars: 120, asOf: '2026-01-01', last: 100,
  sma20: null, sma50: null, sma200: null,
  rsi14: null, rsiState: 'unknown', macd: null, macdSignal: null, macdHist: null, macdState: 'unknown',
  volatilityPct: null, atr14: null, maxDrawdownPct: null,
  return1w: null, return1m: null, return3m: null, volumeTrend: null,
  trend: 'unknown', support: null, resistance: null,
  ...over,
});

describe('computeCompanyRisk', () => {
  it('omits entries whose inputs are missing (never guesses)', () => {
    const entries = computeCompanyRisk({ technical: tech(), periods: [], beta: null, avgVolume: null, insights: [] });
    expect(entries).toHaveLength(0);
  });

  it('tones volatility by documented thresholds', () => {
    const low = computeCompanyRisk({ technical: tech({ volatilityPct: 12 }), periods: [], beta: null, avgVolume: null, insights: [] });
    expect(low.find((e) => e.id === 'volatility')?.tone).toBe('positive');
    const high = computeCompanyRisk({ technical: tech({ volatilityPct: 55 }), periods: [], beta: null, avgVolume: null, insights: [] });
    expect(high.find((e) => e.id === 'volatility')?.tone).toBe('negative');
  });

  it('computes leverage from reported debt and equity', () => {
    const entries = computeCompanyRisk({
      technical: tech(), periods: [period({ totalDebt: 300, totalEquity: 100, ebitda: 50, netDebt: 250 })],
      beta: null, avgVolume: null, insights: [],
    });
    const lev = entries.find((e) => e.id === 'leverage');
    expect(lev?.value).toBe('3.00×');
    expect(lev?.tone).toBe('negative');
    expect(entries.find((e) => e.id === 'net-debt-ebitda')?.value).toBe('5.00×');
  });

  it('flags negative free cash flow', () => {
    const entries = computeCompanyRisk({
      technical: tech(), periods: [period({ freeCashFlow: -2_500_000 })],
      beta: null, avgVolume: null, insights: [],
    });
    expect(entries.find((e) => e.id === 'cash-flow')?.tone).toBe('negative');
  });

  it('computes earnings variability only with enough periods', () => {
    const two = computeCompanyRisk({ technical: tech(), periods: [period({ netIncome: 10 }), period({ netIncome: 20 })], beta: null, avgVolume: null, insights: [] });
    expect(two.find((e) => e.id === 'earnings-variability')).toBeUndefined();
    const three = computeCompanyRisk({ technical: tech(), periods: [period({ netIncome: 10 }), period({ netIncome: 50 }), period({ netIncome: 90 })], beta: null, avgVolume: null, insights: [] });
    expect(three.find((e) => e.id === 'earnings-variability')).toBeDefined();
  });

  it('surfaces warning/negative fundamentals insights as evidence-backed risks', () => {
    const entries = computeCompanyRisk({
      technical: tech(), periods: [], beta: null, avgVolume: null,
      insights: [{ id: 'x', tone: 'warning', title: 'Rising debt', detail: 'Debt up 40% YoY', evidence: ['totalDebt'] }],
    });
    const e = entries.find((x) => x.id === 'insight-x');
    expect(e?.tone).toBe('warning');
    expect(e?.evidence).toBe('Debt up 40% YoY');
  });
});
