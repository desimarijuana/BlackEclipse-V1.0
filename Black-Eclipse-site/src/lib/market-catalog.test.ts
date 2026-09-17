import { describe, it, expect } from 'vitest';
import {
  COMMODITY_CATALOG,
  FOREX_CATALOG,
  catalogName,
  commodityDef,
  forexDef,
  isCatalogSymbol,
} from '@/lib/market-catalog';
import {
  DEFAULT_RIBBON_SYMBOLS,
  RIBBON_MAX_SYMBOLS,
  isRibbonCustomized,
  ribbonLabel,
  splitRibbonSymbols,
} from '@/lib/ribbon/store';

describe('market catalog', () => {
  it('resolves commodity and forex symbols case/space-insensitively', () => {
    expect(commodityDef('gc=f')?.name).toBe('Gold');
    expect(commodityDef(' GC=F ')?.unit).toBe('USD/oz');
    expect(forexDef('eurusd=x')?.name).toBe('Euro / US Dollar');
    expect(forexDef('eurusd=x')?.base).toBe('EUR');
  });

  it('returns undefined for non-catalog symbols', () => {
    expect(commodityDef('AAPL')).toBeUndefined();
    expect(forexDef('AAPL')).toBeUndefined();
    expect(isCatalogSymbol('AAPL')).toBe(false);
    expect(isCatalogSymbol('^GSPC')).toBe(false);
  });

  it('classifies catalog symbols and names them', () => {
    expect(isCatalogSymbol('GC=F')).toBe(true);
    expect(isCatalogSymbol('USDJPY=X')).toBe(true);
    expect(catalogName('GC=F')).toBe('Gold');
    expect(catalogName('USDJPY=X')).toBe('US Dollar / Japanese Yen');
    expect(catalogName('AAPL')).toBeUndefined();
  });

  it('has no duplicate symbols within a catalog', () => {
    const commodities = COMMODITY_CATALOG.map(c => c.symbol);
    const forex = FOREX_CATALOG.map(p => p.symbol);
    expect(new Set(commodities).size).toBe(commodities.length);
    expect(new Set(forex).size).toBe(forex.length);
  });
});

describe('ribbon store helpers', () => {
  it('strips Yahoo decorations for the display label', () => {
    expect(ribbonLabel('^GSPC')).toBe('GSPC');
    expect(ribbonLabel('BTC-USD')).toBe('BTC');
    expect(ribbonLabel('EURUSD=X')).toBe('EURUSD');
    expect(ribbonLabel('AAPL')).toBe('AAPL');
  });

  it('splits configured symbols into catalog feeds vs quote lookups', () => {
    const { catalog, quotes } = splitRibbonSymbols(['^GSPC', 'GC=F', 'AAPL', 'EURUSD=X', 'BTC']);
    expect(catalog).toEqual(['GC=F', 'EURUSD=X']);
    expect(quotes).toEqual(['^GSPC', 'AAPL', 'BTC']);
  });

  it('detects a customised list and honours order', () => {
    expect(isRibbonCustomized([...DEFAULT_RIBBON_SYMBOLS])).toBe(false);
    expect(isRibbonCustomized(['^GSPC'])).toBe(true);
    expect(isRibbonCustomized([...DEFAULT_RIBBON_SYMBOLS].reverse())).toBe(true);
  });

  it('ships a default selection within the cap', () => {
    expect(DEFAULT_RIBBON_SYMBOLS.length).toBeGreaterThan(0);
    expect(DEFAULT_RIBBON_SYMBOLS.length).toBeLessThanOrEqual(RIBBON_MAX_SYMBOLS);
  });
});
