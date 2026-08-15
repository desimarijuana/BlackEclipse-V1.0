import { useMemo } from 'react';
import type {
  StockItem, FundItem, ETFItem, BlueChipItem,
} from './market-data';
import {
  getRegionalFunds, getRegionalEtfs, getRegionalDividendStocks,
} from './market-data';

export interface ScreenerFilterState {
  apiStocks: StockItem[];
  apiEtfs?: ETFItem[];
  stockSearch: string;
  filterExchange: string;
  filterIndex: string;
  filterSector: string;
  filterIndustry: string;
  filterCountry: string;
  filterMarketCap: string;
  filterPE: string;
  filterDividendYield: string;
  filterPrice: string;
  filterChange: string;
  filterVolume: string;
  filterRecommendation: string;
  filterMetricType: string;
  filterType: string;
  screenerTab: string;
  userCountry: string;
  stockSortField: keyof StockItem;
  stockSortOrder: 'asc' | 'desc';
  fundSearch: string;
  fundCategory: string;
  fundSortField: keyof FundItem;
  fundSortOrder: 'asc' | 'desc';
  etfSearch: string;
  etfCategory: string;
  etfSortField: keyof ETFItem;
  etfSortOrder: 'asc' | 'desc';
  dividendSearch: string;
  dividendSortField: keyof BlueChipItem;
  dividendSortOrder: 'asc' | 'desc';
}

function parseCapStr(val: string): number {
  const v = parseFloat(val);
  if (isNaN(v)) return 0;
  if (val.endsWith('T')) return v * 1_000_000;
  if (val.endsWith('B')) return v * 1_000;
  if (val.endsWith('M')) return v;
  return v / 1_000_000;
}

function parseVolStr(val: string): number {
  const v = parseFloat(val);
  if (isNaN(v)) return 0;
  if (val.endsWith('B')) return v * 1_000;
  if (val.endsWith('M')) return v;
  if (val.endsWith('K')) return v / 1_000;
  return v / 1_000_000;
}

function sortBy<T>(items: T[], field: keyof T, order: 'asc' | 'desc'): T[] {
  return [...items].sort((a, b) => {
    const valA = a[field];
    const valB = b[field];
    if (typeof valA === 'string' && typeof valB === 'string') {
      return order === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
    }
    if (typeof valA === 'number' && typeof valB === 'number') {
      return order === 'asc' ? valA - valB : valB - valA;
    }
    return 0;
  });
}

/**
 * Pure filtering + sorting logic for the market screener.
 * Extracted from the (very large) MarketOverviewScreen component so it can be
 * unit-tested and reused by the agentic layer.
 */
export function useScreenerFilters(state: ScreenerFilterState) {
  const {
    apiStocks, stockSearch, filterExchange, filterIndex, filterSector, filterIndustry,
    filterCountry, filterMarketCap, filterPE, filterDividendYield, filterPrice,
    filterChange, filterVolume, filterRecommendation, filterMetricType, filterType,
    screenerTab, userCountry, stockSortField, stockSortOrder,
    fundSearch, fundCategory, fundSortField, fundSortOrder,
    etfSearch, etfCategory, etfSortField, etfSortOrder,
    dividendSearch, dividendSortField, dividendSortOrder,
  } = state;

  const filteredStocks = useMemo(() => {
    const filtered = apiStocks.filter((item) => {
      const matchesSearch =
        item.symbol.toLowerCase().includes(stockSearch.toLowerCase()) ||
        item.name.toLowerCase().includes(stockSearch.toLowerCase());
      const matchesExchange = filterExchange === 'All' || item.exchange === filterExchange;
      const matchesSector = filterSector === 'All' || item.sector === filterSector;
      const matchesIndustry = filterIndustry === 'All' || item.industry === filterIndustry;
      const matchesType = filterType === 'All' || (item.securityType || '').toLowerCase().includes(filterType.toLowerCase());

      if (screenerTab === 'crypto') {
        const capMil = parseCapStr(item.marketCap);
        let matchesCryptoCap = true;
        if (filterMarketCap === 'Mega') matchesCryptoCap = capMil >= 100_000;
        else if (filterMarketCap === 'Large') matchesCryptoCap = capMil >= 10_000 && capMil < 100_000;
        else if (filterMarketCap === 'Mid') matchesCryptoCap = capMil >= 2_000 && capMil < 10_000;
        else if (filterMarketCap === 'Small') matchesCryptoCap = capMil > 0 && capMil < 2_000;

        let matchesCryptoChange = true;
        const chg = item.changePercent;
        if (filterChange === 'Positive') matchesCryptoChange = chg > 0;
        else if (filterChange === 'Negative') matchesCryptoChange = chg < 0;
        else if (filterChange === 'Over2') matchesCryptoChange = chg >= 2;
        else if (filterChange === 'UnderMinus2') matchesCryptoChange = chg <= -2;

        let matchesMetricType = true;
        const circRatio = item.maxSupplyRaw && item.maxSupplyRaw > 0
          ? (item.circulatingSupplyRaw || 0) / item.maxSupplyRaw
          : 1;
        if (filterMetricType === 'Top Liquidity') matchesMetricType = (item.volumeRaw || 0) >= 50_000_000;
        else if (filterMetricType === 'Near ATH') matchesMetricType = (item.athChangePercent || 0) >= -15;
        else if (filterMetricType === 'Most Traded') matchesMetricType = (item.volumeRaw || 0) >= 10_000_000;
        else if (filterMetricType === 'Low Float') matchesMetricType = circRatio > 0 && circRatio < 0.35;
        else if (filterMetricType === 'High Circulating Ratio') matchesMetricType = circRatio >= 0.80;

        return matchesSearch && matchesExchange && matchesSector && matchesIndustry
          && matchesCryptoCap && matchesCryptoChange && matchesMetricType;
      }

      const matchesIndex = filterIndex === 'All' || item.index.includes(filterIndex);

      const countryMap: Record<string, string> = {
        USA: 'US', India: 'IN', Pakistan: 'PK', China: 'CN',
        Taiwan: 'TW', Netherlands: 'NL', Switzerland: 'CH', All: 'All',
      };
      const targetUserCountry = countryMap[userCountry] || userCountry;
      const targetFilterCountry = countryMap[filterCountry] || filterCountry;
      const matchesCountry =
        (filterCountry === 'All' || item.country === targetFilterCountry) &&
        (userCountry === 'All' || item.country === targetUserCountry);

      const capInMillions = parseCapStr(item.marketCap);
      let matchesMarketCap = true;
      if (filterMarketCap === 'Mega') matchesMarketCap = capInMillions >= 100_000;
      else if (filterMarketCap === 'Large') matchesMarketCap = capInMillions >= 10_000 && capInMillions < 100_000;
      else if (filterMarketCap === 'Mid') matchesMarketCap = capInMillions >= 2_000 && capInMillions < 10_000;
      else if (filterMarketCap === 'Small') matchesMarketCap = capInMillions > 0 && capInMillions < 2_000;

      const pe = parseFloat(item.peRatio);
      let matchesPE = true;
      if (isNaN(pe)) {
        if (filterPE !== 'All') matchesPE = false;
      } else {
        if (filterPE === 'Under15') matchesPE = pe < 15;
        else if (filterPE === 'Under20') matchesPE = pe < 20;
        else if (filterPE === 'Under30') matchesPE = pe < 30;
        else if (filterPE === 'Over30') matchesPE = pe > 30;
        else if (filterPE === 'Over50') matchesPE = pe > 50;
      }

      const dy = item.dividendYield;
      let matchesDividend = true;
      if (filterDividendYield === 'None') matchesDividend = dy === 'None';
      else if (filterDividendYield === 'Positive') matchesDividend = dy !== 'None';
      else if (filterDividendYield === 'Over2') matchesDividend = dy !== 'None' && parseFloat(dy) >= 2;
      else if (filterDividendYield === 'Over5') matchesDividend = dy !== 'None' && parseFloat(dy) >= 5;

      const price = item.price;
      let matchesPrice = true;
      if (filterPrice === 'Under10') matchesPrice = price < 10;
      else if (filterPrice === 'Under50') matchesPrice = price < 50;
      else if (filterPrice === 'Under100') matchesPrice = price < 100;
      else if (filterPrice === 'Over100') matchesPrice = price >= 100;
      else if (filterPrice === 'Over500') matchesPrice = price >= 500;

      const change = item.changePercent;
      let matchesChange = true;
      if (filterChange === 'Positive') matchesChange = change > 0;
      else if (filterChange === 'Negative') matchesChange = change < 0;
      else if (filterChange === 'Over2') matchesChange = change >= 2;
      else if (filterChange === 'UnderMinus2') matchesChange = change <= -2;

      const volInMillions = parseVolStr(item.volume);
      let matchesVolume = true;
      if (filterVolume === 'Under1') matchesVolume = volInMillions < 1;
      else if (filterVolume === '1to10') matchesVolume = volInMillions >= 1 && volInMillions <= 10;
      else if (filterVolume === 'Over10') matchesVolume = volInMillions > 10;
      else if (filterVolume === 'Over30') matchesVolume = volInMillions > 30;

      let matchesRec = true;
      if (filterRecommendation === 'StrongBuy') matchesRec = item.recommendation === 'Strong Buy';
      else if (filterRecommendation === 'BuyOrBetter') matchesRec = item.recommendation === 'Buy' || item.recommendation === 'Strong Buy';
      else if (filterRecommendation === 'HoldOrWorse') matchesRec = item.recommendation === 'Hold' || item.recommendation === 'Sell';
      else if (filterRecommendation === 'Sell') matchesRec = item.recommendation === 'Sell';

      return matchesSearch && matchesExchange && matchesIndex && matchesSector && matchesIndustry
        && matchesCountry && matchesMarketCap && matchesPE && matchesDividend
        && matchesPrice && matchesChange && matchesVolume && matchesRec && matchesType;
    });

    return sortBy(filtered, stockSortField, stockSortOrder);
  }, [
    apiStocks, stockSearch, filterExchange, filterIndex, filterSector, filterIndustry,
    filterCountry, filterMarketCap, filterPE, filterDividendYield, filterPrice,
    filterChange, filterVolume, filterRecommendation, filterMetricType, filterType,
    screenerTab, userCountry, stockSortField, stockSortOrder,
  ]);

  const filteredFunds = useMemo(() => {
    const filtered = getRegionalFunds(userCountry).filter((item) => {
      const matchesSearch =
        item.symbol.toLowerCase().includes(fundSearch.toLowerCase()) ||
        item.name.toLowerCase().includes(fundSearch.toLowerCase());
      const matchesCategory = fundCategory === 'All' || item.category === fundCategory;
      return matchesSearch && matchesCategory;
    });
    return sortBy(filtered, fundSortField, fundSortOrder);
  }, [userCountry, fundSearch, fundCategory, fundSortField, fundSortOrder]);

  const filteredETFs = useMemo(() => {
    const filtered = (state.apiEtfs ?? getRegionalEtfs(userCountry)).filter((item) => {
      const matchesSearch =
        item.symbol.toLowerCase().includes(etfSearch.toLowerCase()) ||
        item.name.toLowerCase().includes(etfSearch.toLowerCase());
      const matchesCategory = etfCategory === 'All' || item.category === etfCategory;
      return matchesSearch && matchesCategory;
    });
    return sortBy(filtered, etfSortField, etfSortOrder);
  }, [state.apiEtfs, userCountry, etfSearch, etfCategory, etfSortField, etfSortOrder]);

  const filteredDividendStocks = useMemo(() => {
    const filtered = getRegionalDividendStocks(userCountry).filter((item) =>
      item.symbol.toLowerCase().includes(dividendSearch.toLowerCase()) ||
      item.name.toLowerCase().includes(dividendSearch.toLowerCase())
    );
    return sortBy(filtered, dividendSortField, dividendSortOrder);
  }, [userCountry, dividendSearch, dividendSortField, dividendSortOrder]);

  return {
    filteredStocks,
    filteredFunds,
    filteredETFs,
    filteredDividendStocks,
  };
}
