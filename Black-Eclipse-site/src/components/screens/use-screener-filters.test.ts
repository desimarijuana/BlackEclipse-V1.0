import { describe, it, expect, vi } from 'vitest';

// The hook only uses useMemo; run the callbacks eagerly so we can test the pure
// filter/sort logic without a React renderer.
vi.mock('react', () => ({ useMemo: (fn: () => unknown) => fn() }));

import { useScreenerFilters, type ScreenerFilterState } from './use-screener-filters';
import type { StockItem } from '@/lib/screener/data';

function stock(partial: Partial<StockItem>): StockItem {
  return {
    symbol: 'X', name: 'X', sector: 'Other', industry: 'Other',
    country: 'US', price: 10, changePercent: 0, volume: '1.0M',
    marketCap: '1.0B', peRatio: 'N/A', dividendYield: 'None', index: 'JDDS',
    recommendation: 'N/A', exchange: 'US', forwardPE: 'N/A', peg: 'N/A',
    ps: 'N/A', pb: 'N/A', evEbitda: 'N/A', grossMargin: 'N/A',
    operatingMargin: 'N/A', netProfitMargin: 'N/A', insiderOwnership: 'N/A',
    institutionalOwnership: 'N/A', shortFloat: 'N/A', rsi14: 'N/A',
    sma20: 'N/A', sma50: 'N/A', sma200: 'N/A',
    ...partial,
  };
}

function state(partial: Partial<ScreenerFilterState>): ScreenerFilterState {
  return {
    apiStocks: [], stockSearch: '', filterExchange: 'All', filterIndex: 'All',
    filterSector: 'All', filterIndustry: 'All', filterCountry: 'All',
    filterMarketCap: 'All', filterPE: 'All', filterDividendYield: 'All',
    filterPrice: 'All', filterChange: 'All', filterVolume: 'All',
    filterRecommendation: 'All', filterMetricType: 'All', filterType: 'All',
    screenerTab: 'stocks', userCountry: 'US',
    stockSortField: 'symbol', stockSortOrder: 'asc',
    fundSearch: '', fundCategory: 'All', fundSortField: 'symbol', fundSortOrder: 'asc',
    etfSearch: '', etfCategory: 'All', etfSortField: 'symbol', etfSortOrder: 'asc',
    dividendSearch: '', dividendSortField: 'symbol', dividendSortOrder: 'asc',
    ...partial,
  };
}

describe('useScreenerFilters — stocks', () => {
  it('multi-select type matches ANY selected type', () => {
    const apiStocks = [
      stock({ symbol: 'A', securityType: 'Stock' }),
      stock({ symbol: 'B', securityType: 'ETF' }),
      stock({ symbol: 'C', securityType: 'Mutual Fund' }),
    ];
    const { filteredStocks } = useScreenerFilters(state({ apiStocks, filterType: 'Stock,ETF' }));
    expect(filteredStocks.map((s) => s.symbol).sort()).toEqual(['A', 'B']);
  });

  it('country filter normalizes display name to code ("United States" == "US")', () => {
    const apiStocks = [
      stock({ symbol: 'A', country: 'US' }),
      stock({ symbol: 'B', country: 'United States' }),
      stock({ symbol: 'C', country: 'CA' }),
    ];
    const { filteredStocks } = useScreenerFilters(state({ apiStocks, filterCountry: 'United States' }));
    expect(filteredStocks.map((s) => s.symbol).sort()).toEqual(['A', 'B']);
  });

  it('does not drop foreign-domiciled rows just because of the selected market', () => {
    const apiStocks = [
      stock({ symbol: 'A', country: 'US' }),
      stock({ symbol: 'B', country: 'Israel' }),
    ];
    const { filteredStocks } = useScreenerFilters(state({ apiStocks, userCountry: 'USA' }));
    expect(filteredStocks.map((s) => s.symbol).sort()).toEqual(['A', 'B']);
  });

  it('change Positive excludes exactly 0', () => {
    const apiStocks = [
      stock({ symbol: 'UP', changePercent: 1.2 }),
      stock({ symbol: 'FLAT', changePercent: 0 }),
      stock({ symbol: 'DOWN', changePercent: -1.0 }),
    ];
    const { filteredStocks } = useScreenerFilters(state({ apiStocks, filterChange: 'Positive' }));
    expect(filteredStocks.map((s) => s.symbol)).toEqual(['UP']);
  });

  it('sector filter matches synonym labels via normalization', () => {
    const apiStocks = [
      stock({ symbol: 'A', sector: 'Financial Services' }),
      stock({ symbol: 'B', sector: 'Financials' }),
      stock({ symbol: 'C', sector: 'Technology' }),
    ];
    const { filteredStocks } = useScreenerFilters(state({ apiStocks, filterSector: 'Financials' }));
    expect(filteredStocks.map((s) => s.symbol).sort()).toEqual(['A', 'B']);
  });

  it('Unclassified sector filter matches null and unclassified rows', () => {
    const apiStocks = [
      stock({ symbol: 'A', sector: 'Unclassified' }),
      stock({ symbol: 'B', sector: '' }),
      stock({ symbol: 'C', sector: 'Technology' }),
    ];
    const { filteredStocks } = useScreenerFilters(state({ apiStocks, filterSector: 'Unclassified' }));
    expect(filteredStocks.map((s) => s.symbol).sort()).toEqual(['A', 'B']);
  });

  it('preserves server order when stocksServerSorted is true', () => {
    const apiStocks = [
      stock({ symbol: 'BBB' }),
      stock({ symbol: 'AAA' }),
      stock({ symbol: 'CCC' }),
    ];
    const { filteredStocks } = useScreenerFilters(state({
      apiStocks, stocksServerSorted: true, stockSortField: 'symbol', stockSortOrder: 'asc',
    }));
    expect(filteredStocks.map((s) => s.symbol)).toEqual(['BBB', 'AAA', 'CCC']);
  });
});
