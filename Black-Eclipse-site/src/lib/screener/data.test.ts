import { describe, it, expect } from 'vitest';
import {
  INDEX_DATA, SECTOR_PERFORMANCE, ETFS_DATA, NEW_STOCKS_DATA, BLUE_CHIPS_DATA,
  TOP_GAINERS, TOP_LOSERS, getSimulatedDashboard,
  getRegionalEtfs, getRegionalNewListings, getRegionalBlueChips, getRegionalFunds, getRegionalDividendStocks,
} from './data';

describe('market-data', () => {
  it('has index data for the default market', () => {
    expect(INDEX_DATA.length).toBeGreaterThan(0);
    expect(INDEX_DATA[0]).toHaveProperty('symbol');
    expect(INDEX_DATA[0]).toHaveProperty('price');
  });

  it('has sector performance data', () => {
    expect(SECTOR_PERFORMANCE.length).toBeGreaterThan(0);
  });

  it('has ETF, IPO, and blue chip data', () => {
    expect(ETFS_DATA.length).toBeGreaterThan(0);
    expect(NEW_STOCKS_DATA.length).toBeGreaterThan(0);
    expect(BLUE_CHIPS_DATA.length).toBeGreaterThan(0);
  });

  it('has top gainers and losers', () => {
    expect(TOP_GAINERS.length).toBeGreaterThan(0);
    expect(TOP_LOSERS.length).toBeGreaterThan(0);
  });

  it('getSimulatedDashboard returns indices, sectors, and shifters for CRYPTO', () => {
    const dash = getSimulatedDashboard('CRYPTO');
    expect(dash.indices.length).toBeGreaterThan(0);
    expect(dash.sectors.length).toBeGreaterThan(0);
    expect(dash.shifters.gainers.length).toBeGreaterThan(0);
    expect(dash.shifters.losers.length).toBeGreaterThan(0);
  });

  it('getSimulatedDashboard returns data for USA', () => {
    const dash = getSimulatedDashboard('USA');
    expect(dash.indices.length).toBeGreaterThan(0);
    expect(dash.sectors.length).toBeGreaterThan(0);
  });

  it('regional getters fall back to USA for unknown countries', () => {
    expect(getRegionalEtfs('Mars')).toEqual(getRegionalEtfs('USA'));
    expect(getRegionalNewListings('Mars')).toEqual(getRegionalNewListings('USA'));
    expect(getRegionalBlueChips('Mars')).toEqual(getRegionalBlueChips('USA'));
    expect(getRegionalFunds('Mars')).toEqual(getRegionalFunds('USA'));
    expect(getRegionalDividendStocks('Mars')).toEqual(getRegionalDividendStocks('USA'));
  });
});
