import { describe, expect, it } from 'vitest';
import type { EarningsEntry, FundamentalPeriod } from '@/lib/fundamentals/types';
import {
  buildDrawdown,
  buildEarningsSurprise,
  buildPriceTrend,
  buildRelativePerformance,
  buildValuationBand,
  type PriceClosePoint,
} from './charts';

function series(start: string, values: number[]): PriceClosePoint[] {
  const startMs = Date.parse(`${start}T00:00:00Z`);
  return values.map((close, index) => ({
    date: new Date(startMs + index * 86_400_000).toISOString().slice(0, 10),
    close,
  }));
}

function period(endDate: string, eps: number): FundamentalPeriod {
  return {
    endDate,
    fiscalYear: Number(endDate.slice(0, 4)),
    revenue: null, costOfRevenue: null, grossProfit: null, operatingIncome: null,
    ebitda: null, netIncome: null, eps, taxProvision: null, pretaxIncome: null,
    researchDevelopment: null, interestExpense: null, operatingCashFlow: null,
    capex: null, freeCashFlow: null, dividendsPaid: null, depreciation: null,
    totalAssets: null, totalLiabilities: null, totalEquity: null, totalDebt: null,
    netDebt: null, cash: null, currentAssets: null, currentLiabilities: null,
    inventory: null, accountsReceivable: null, sharesOutstanding: null,
    grossMargin: null, operatingMargin: null, netMargin: null, roe: null, roa: null,
    roic: null, debtToEquity: null, currentRatio: null, quickRatio: null,
  };
}

describe('buildRelativePerformance', () => {
  it('rebases both series to zero on common dates', () => {
    const stock = series('2026-01-01', Array.from({ length: 40 }, (_, i) => 100 + i * 0.5));
    const benchmark = series('2026-01-01', Array.from({ length: 40 }, (_, i) => 200 + i * 0.5));

    const chart = buildRelativePerformance(stock, benchmark, { symbol: '^GSPC', label: 'S&P 500' }, 6, 'TEST');

    expect(chart.state).toBe('READY');
    expect(chart.provenance.state).toBe('HISTORICAL');
    expect(chart.series[0].values[0]).toBe(0);
    expect(chart.series[1].values[0]).toBe(0);
    expect(chart.series[0].values.at(-1)).toBeCloseTo(19.5, 1);
    expect(chart.series[1].values.at(-1)).toBeCloseTo(9.75, 1);
  });

  it('is unavailable when there is no overlapping benchmark history', () => {
    const stock = series('2026-01-01', [100, 101, 102]);
    const chart = buildRelativePerformance(stock, [], { symbol: '^GSPC', label: 'S&P 500' });
    expect(chart.state).toBe('UNAVAILABLE');
    expect(chart.reason).toMatch(/not available/i);
  });
});

describe('buildValuationBand', () => {
  it('uses the close at each fiscal year-end, not today’s price', () => {
    const bars = [
      { date: '2023-12-29', close: 150 },
      { date: '2024-12-31', close: 180 },
    ];
    const chart = buildValuationBand(
      [period('2023-12-29', 5), period('2024-12-31', 6)],
      bars,
      'SEC EDGAR',
      'filing',
    );

    expect(chart.state).toBe('READY');
    expect(chart.series[0].values).toEqual([30, 30]);
    expect(chart.provenance.sources[0].tier).toBe('filing');
  });

  it('excludes loss-making years', () => {
    const chart = buildValuationBand(
      [period('2023-12-31', -1), period('2024-12-31', 5)],
      series('2023-12-20', [100, 100, 100]),
      'SEC EDGAR',
      'filing',
    );
    expect(chart.state).toBe('UNAVAILABLE');
    expect(chart.reason).toMatch(/profitable/i);
  });
});

describe('buildPriceTrend', () => {
  it('renders real closes with a provider source', () => {
    const chart = buildPriceTrend(
      series('2026-01-01', [100, 101, 103]),
      { id: 'yahoo', label: 'Yahoo Finance', tier: 'provider' },
      'TEST',
      'USD',
    );
    expect(chart.state).toBe('READY');
    expect(chart.unit).toBe('price');
    expect(chart.series[0].values).toEqual([100, 101, 103]);
    expect(chart.provenance.sources[0].tier).toBe('provider');
  });

  it('is unavailable without a price series', () => {
    const chart = buildPriceTrend([], { id: 'none', label: 'None', tier: 'none' });
    expect(chart.state).toBe('UNAVAILABLE');
    expect(chart.reason).toMatch(/price history/i);
  });
});

describe('buildDrawdown', () => {
  it('tracks decline from the running high', () => {
    const chart = buildDrawdown(
      series('2026-01-01', [100, 120, 90, 60]),
      { id: 'yahoo', label: 'Yahoo Finance', tier: 'provider' },
    );
    expect(chart.state).toBe('READY');
    expect(chart.series[0].values).toEqual([0, 0, -25, -50]);
    expect(chart.provenance.state).toBe('DERIVED');
  });
});

describe('buildEarningsSurprise', () => {
  it('computes actual-versus-estimate percentages', () => {
    const history: EarningsEntry[] = [
      { date: '2025-03-31', actual: 1.1, estimate: 1 },
      { date: '2025-06-30', actual: 0.9, estimate: 1 },
      { date: '2025-09-30', actual: null, estimate: 1 },
    ];
    const chart = buildEarningsSurprise(history, 'Yahoo Finance', 'provider');

    expect(chart.state).toBe('READY');
    expect(chart.series[0].values).toEqual([10, -10]);
    expect(chart.provenance.state).toBe('DERIVED');
  });

  it('is unavailable without actual/estimate pairs', () => {
    const chart = buildEarningsSurprise([], 'Yahoo Finance', 'provider');
    expect(chart.state).toBe('UNAVAILABLE');
  });
});
