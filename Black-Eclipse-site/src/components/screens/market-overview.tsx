'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { 
  ArrowUpRight, ArrowDownRight, ArrowRight, Search, 
  Sparkles, Star, BarChart3, 
  Layers, Award, TrendingUp, Sliders, X, Coins, ChevronDown,
  Info, Briefcase, Building2, Globe, RefreshCw
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { TradingViewChart } from './tradingview-chart';
import { cn } from '@/lib/utils';
import { TopLoader } from '@/components/ui/top-loader';
import { Skeleton, SkeletonHeader, SkeletonIndexCard, SkeletonPanel, SkeletonTable } from '@/components/ui/skeleton';
import {
  IndexCard, SectorPerformance, ShifterItem, StockItem, FundItem, ETFItem, BlueChipItem,
  INDEX_DATA, SECTOR_PERFORMANCE, TOP_GAINERS, TOP_LOSERS,
} from './market-data';
import { useScreenerFilters } from './use-screener-filters';

function TableSkeleton({ cols = 11, rows = 6 }: { cols?: number; rows?: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, idx) => (
        <tr key={idx} className="border-b border-border/10">
          {Array.from({ length: cols }).map((_, cIdx) => (
            <td key={cIdx} className="p-3.5">
              <Skeleton className="h-4 w-3/4 mx-auto" />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

interface MarketOverviewScreenProps {
  onAnalyzeTicker: (ticker: string, customContextPrompt?: string) => void;
  onSelectChartSymbol?: (symbol: string) => void;
  embedded?: boolean;
  onMarketStatusChange?: (isBullish: boolean) => void;
}

export function MarketOverviewScreen({ onAnalyzeTicker, onSelectChartSymbol, embedded = false, onMarketStatusChange }: MarketOverviewScreenProps) {

  const handleSymbolClick = (symbol: string, name: string, extra?: Partial<StockItem>) => {
    setSelectedAnalysisStock({
        symbol,
        name,
        peRatio: extra?.peRatio || 'N/A',
        marketCap: extra?.marketCap || 'N/A',
        dividendYield: extra?.dividendYield || 'N/A',
        shortFloat: extra?.shortFloat || 'N/A',
        sector: extra?.sector || '',
        industry: extra?.industry || '',
        country: extra?.country || '',
        price: extra?.price || 0,
        changePercent: extra?.changePercent || 0,
        volume: extra?.volume || 'N/A',
        index: extra?.index || '',
        recommendation: extra?.recommendation || '',
        exchange: extra?.exchange || '',
        forwardPE: extra?.forwardPE || 'N/A',
        peg: extra?.peg || 'N/A',
        ps: extra?.ps || 'N/A',
        pb: extra?.pb || 'N/A',
        evEbitda: extra?.evEbitda || 'N/A',
        grossMargin: extra?.grossMargin || 'N/A',
        operatingMargin: extra?.operatingMargin || 'N/A',
        netProfitMargin: extra?.netProfitMargin || 'N/A',
        insiderOwnership: extra?.insiderOwnership || 'N/A',
        institutionalOwnership: extra?.institutionalOwnership || 'N/A',
        rsi14: extra?.rsi14 || 'N/A',
        sma20: extra?.sma20 || 'N/A',
        sma50: extra?.sma50 || 'N/A',
        sma200: extra?.sma200 || 'N/A',
        circulatingSupply: extra?.circulatingSupply || 'N/A',
        totalSupply: extra?.totalSupply || 'N/A',
        maxSupply: extra?.maxSupply || 'N/A',
        ath: extra?.ath || 'N/A',
        atl: extra?.atl || 'N/A',
        rank: extra?.rank || 9999,
        athChangePercent: extra?.athChangePercent || 0,
        atlChangePercent: extra?.atlChangePercent || 0,
        athDate: extra?.athDate || "",
        atlDate: extra?.atlDate || "",
        marketCapRaw: extra?.marketCapRaw || 0,
        volumeRaw: extra?.volumeRaw || 0,
        circulatingSupplyRaw: extra?.circulatingSupplyRaw || 0,
        maxSupplyRaw: extra?.maxSupplyRaw || 0,
      });
  };
  
  // Screener state
  const [stockSearch, setStockSearch] = useState('');
  const [stockSortField, setStockSortField] = useState<keyof StockItem>('symbol');
  const [stockSortOrder, setStockSortOrder] = useState<'asc' | 'desc'>('asc');

  // Finviz-style advanced filter states
  const [filterExchange, setFilterExchange] = useState('All');
  const [filterIndex, setFilterIndex] = useState('All');
  const [filterSector, setFilterSector] = useState('All');
  const [filterIndustry, setFilterIndustry] = useState('All');
  const [filterCountry, setFilterCountry] = useState('All');
  const [filterMarketCap, setFilterMarketCap] = useState('All');
  const [filterPE, setFilterPE] = useState('All');
  const [filterDividendYield, setFilterDividendYield] = useState('All');
  const [filterPrice, setFilterPrice] = useState('All');
  const [filterChange, setFilterChange] = useState('All');
  const [filterVolume, setFilterVolume] = useState('All');
  const [filterRecommendation, setFilterRecommendation] = useState('All');
  const [filterType, setFilterType] = useState('All');
  // Multi-select asset types (e.g. ['Stock', 'REIT']). When non-empty, overrides filterType.
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [typeMenuOpen, setTypeMenuOpen] = useState(false);

  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);
  // Removed selectedStock state
  const [selectedAnalysisStock, setSelectedAnalysisStock] = useState<StockItem | null>(null);
  const [filterMetricType, setFilterMetricType] = useState('All');
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);
  // Selectable region for stocks: 'USA' (US), 'PK' (Pakistan), or 'CRYPTO'.
  const [userCountry, setUserCountry] = useState<string>('GLOBAL');
  const [apiStocks, setApiStocks] = useState<StockItem[]>([]);
  const [loadingApi, setLoadingApi] = useState(false);
  const [filterOptions, setFilterOptions] = useState<{ sectors: string[]; industries: string[]; types: string[]; countries: string[] }>({ sectors: [], industries: [], types: [], countries: [] });

  // Unified dynamic metrics states loaded from region-specific backend queries
  const [indexData, setIndexData] = useState<IndexCard[]>(INDEX_DATA);
  const [sectorPerformance, setSectorPerformance] = useState<SectorPerformance[]>(SECTOR_PERFORMANCE);
  const [topGainers, setTopGainers] = useState<ShifterItem[]>(TOP_GAINERS);
  const [topLosers, setTopLosers] = useState<ShifterItem[]>(TOP_LOSERS);

  // Determine if the overall market is bullish (green index sum) or bearish (red index sum)
  const isMarketBullish = useMemo(() => {
    if (!indexData || indexData.length === 0) return true;
    const totalChange = indexData.reduce((acc, idx) => acc + idx.changePercent, 0);
    return totalChange >= 0;
  }, [indexData]);

  // Sync market status with layout container
  useEffect(() => {
    if (onMarketStatusChange) {
      onMarketStatusChange(isMarketBullish);
    }
  }, [isMarketBullish, onMarketStatusChange]);

  // Active view tab inside dashboard ('stocks' | 'etfs' | 'funds' | 'dividend_stocks' | 'crypto')
  const [screenerTab, setScreenerTab] = useState<'stocks' | 'etfs' | 'funds' | 'dividend_stocks' | 'crypto' | 'markets'>('markets');
  const [loadingTab, setLoadingTab] = useState(false);

  const handleTabChange = (tab: 'stocks' | 'etfs' | 'funds' | 'dividend_stocks' | 'crypto' | 'markets') => {
    setScreenerTab(tab);
    setLoadingTab(true);
    setFilterExchange('All');
    setFilterIndex('All');
    setFilterSector('All');
    setFilterIndustry('All');
    setFilterCountry('All');
    setFilterMarketCap('All');
    setFilterPE('All');
    setFilterDividendYield('All');
    setFilterPrice('All');
    setFilterChange('All');
    setFilterVolume('All');
    setFilterRecommendation('All');
    setFilterMetricType('All');
    // Stocks tab defaults to equities (which carry sector/industry data).
    setFilterType(tab === 'stocks' ? 'Stock' : 'All');
    setSelectedTypes([]);
    setExpandedSymbol(null);
    setStockSearch('');
  };

  // Select a market (GLOBAL / US / PK / CRYPTO / ...).
  //   GLOBAL → show the global markets overview (all indices).
  //   any country → switch to that country's stock screener.
  const handleMarketSelect = (market: string) => {
    setUserCountry(market);
    if (market === 'GLOBAL') {
      handleTabChange('markets');
      return;
    }
    if (market === 'CRYPTO') {
      handleTabChange('crypto');
      return;
    }
    if (screenerTab === 'markets' || screenerTab === 'crypto') {
      handleTabChange('stocks');
    }
  };

  const [currentPage, setCurrentPage] = useState(1);
  const [totalStocks, setTotalStocks] = useState(0);
  const [limit, setLimit] = useState(20);

  // Cache of already-fetched pages keyed by page number, so paging backward/
  // forward (especially into prefetched pages) is instant. Cleared whenever the
  // market or filter context changes (see the reset effect below).
  const [pageCache, setPageCache] = useState<Record<number, StockItem[]>>({});

  // Combined Sector/Industry selection: a single dropdown that sets either
  // the sector or the industry filter depending on which list the value is in.
  const handleSectorIndustryChange = (value: string) => {
    if (value === 'All') {
      setFilterSector('All');
      setFilterIndustry('All');
      return;
    }
    if (filterOptions.sectors.includes(value)) {
      setFilterSector(value);
      setFilterIndustry('All');
    } else {
      setFilterIndustry(value);
      setFilterSector('All');
    }
  };

  // The value shown in the combined dropdown: prefer sector if set, else industry.
  const sectorIndustryValue = filterSector !== 'All' ? filterSector : filterIndustry !== 'All' ? filterIndustry : 'All';

  // Reset page + drop prefetch cache on country, limit, search, sector, or tab changes
  React.useEffect(() => {
    setCurrentPage(1);
    setPageCache({});
  }, [userCountry, limit, stockSearch, filterSector, filterIndustry, filterType, filterMarketCap, filterPE, filterPrice, filterChange, filterVolume, filterCountry, screenerTab]);

  const [loadingDashboard, setLoadingDashboard] = useState(false);

  const [dataUpdatedTime, setDataUpdatedTime] = useState<string | null>(null);
  const [dataSource, setDataSource] = useState<string>('live');

  const getQueryCountry = React.useCallback(() => {
    if (screenerTab === 'crypto') return 'CRYPTO';
    // The Markets/GLOBAL view has no stock universe; default to US stocks.
    if (userCountry === 'GLOBAL' || userCountry === 'All') return 'US';
    return userCountry;
  }, [screenerTab, userCountry]);

  // Live dashboard metrics (index quotes, sector performance, shifters) from
  // /api/indices — refreshed whenever the selected market changes. Falls back
  // to the static demo data if the endpoint is unreachable.
  React.useEffect(() => {
    if (screenerTab === 'markets') return;
    let cancelled = false;
    (async () => {
      try {
        const qc = getQueryCountry();
        const res = await fetch(`/api/indices?market=${encodeURIComponent(qc)}`);
        const data = await res.json();
        if (!cancelled && data) {
          if (Array.isArray(data.indices) && data.indices.length > 0) {
            setIndexData(data.indices);
          }
          if (Array.isArray(data.sectors) && data.sectors.length > 0) {
            setSectorPerformance(data.sectors);
          }
          if (data.shifters) {
            if (Array.isArray(data.shifters.gainers) && data.shifters.gainers.length > 0) {
              setTopGainers(data.shifters.gainers);
            }
            if (Array.isArray(data.shifters.losers) && data.shifters.losers.length > 0) {
              setTopLosers(data.shifters.losers);
            }
          }
        }
      } catch (err) {
        console.error('Failed to load dashboard metrics:', err);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screenerTab, userCountry]);

  const fallbackToDemo = React.useCallback((qc: string) => {
    const demoStocks = getFallbackStocks(qc);
    setApiStocks(demoStocks);
    setTotalStocks(demoStocks.length);
    setDataSource('demo');
    setDataUpdatedTime(new Date().toISOString());
  }, []);

  // Load stocks and dashboard metadata based on user's country/tab.
  // Reads from JDDS via /api/stocks; falls back to demo data if empty/unreachable.
  // Server-side pagination: only the current page is fetched, never the whole universe.
  // Fetched pages are cached so paging back is instant, and the next page is
  // prefetched in the background based on the selected region.
  const fetchPage = React.useCallback(async (page: number): Promise<{ stocks: StockItem[]; total: number; filterOptions?: { sectors: string[]; industries: string[]; types: string[]; countries: string[] } } | null> => {
    const qc = getQueryCountry();
    const params = new URLSearchParams({ country: qc });
    params.set('page', String(page));
    params.set('limit', String(limit));
    if (filterType !== 'All') params.set('type', filterType);
    if (filterSector !== 'All') params.set('sector', filterSector);
    if (filterIndustry !== 'All') params.set('industry', filterIndustry);
    if (filterCountry !== 'All') params.set('countryFilter', filterCountry);
    if (filterMarketCap !== 'All') params.set('marketCap', filterMarketCap);
    if (filterPE !== 'All') params.set('pe', filterPE);
    if (filterPrice !== 'All') params.set('price', filterPrice);
    if (filterChange !== 'All') params.set('change', filterChange);
    if (filterVolume !== 'All') params.set('volume', filterVolume);
    if (stockSearch.trim()) params.set('search', stockSearch.trim());

    try {
      const res = await fetch(`/api/stocks?${params.toString()}`);
      const data = await res.json();
      if (data && data.stocks && data.stocks.length > 0) {
        return { stocks: data.stocks, total: data.pagination?.total ?? data.stocks.length, filterOptions: data.filterOptions };
      }
      return null;
    } catch (err) {
      console.error('Failed to load from JDBC, using demo:', err);
      return null;
    }
  }, [getQueryCountry, limit, filterType, filterSector, filterIndustry, filterCountry, filterMarketCap, filterPE, filterPrice, filterChange, filterVolume, stockSearch]);

  const refreshStocks = React.useCallback(async (qc: string, silent = false) => {
    // Stale-while-revalidate: only block on a skeleton when we have nothing to
    // show yet. Otherwise keep the current data visible while refreshing.
    if (!silent && apiStocks.length === 0) {
      setLoadingApi(true);
      setLoadingDashboard(true);
    }
    try {
      // Serve from cache instantly if this page was already fetched.
      if (pageCache[currentPage]) {
        setApiStocks(pageCache[currentPage]);
        if (!silent && apiStocks.length === 0) {
          setLoadingApi(false);
          setLoadingDashboard(false);
        }
      } else {
        const data = await fetchPage(currentPage);
        if (data) {
          setApiStocks(data.stocks);
          setTotalStocks(data.total);
          setDataSource('jdds');
          setDataUpdatedTime(new Date().toISOString());
          if (data.filterOptions) setFilterOptions(data.filterOptions);
          // Cache the fetched page.
          setPageCache((prev) => ({ ...prev, [currentPage]: data.stocks }));
        } else {
          fallbackToDemo(qc);
        }
      }
      // Prefetch the next page for the selected region in the background so
      // paging forward is instant. Never blocks the current render.
      const nextPage = currentPage + 1;
      if (!pageCache[nextPage]) {
        fetchPage(nextPage).then((data) => {
          if (data && data.stocks.length > 0) {
            setPageCache((prev) => ({ ...prev, [nextPage]: data.stocks }));
          }
        });
      }
    } catch (err) {
      console.error('Failed to load from JD, using demo:', err);
      if (!silent && apiStocks.length === 0) fallbackToDemo(qc);
    } finally {
      if (!silent && apiStocks.length === 0) {
        setLoadingApi(false);
        setLoadingDashboard(false);
      }
      setLoadingTab(false);
    }
  }, [fallbackToDemo, fetchPage, currentPage, pageCache, apiStocks.length]);

  React.useEffect(() => {
    // Global markets view shows all indices, not one country's screener.
    if (screenerTab === 'markets') {
      setLoadingTab(false);
      return;
    }
    // GLOBAL country falls back to US stocks via getQueryCountry.
    if (userCountry === 'GLOBAL' && screenerTab !== 'stocks' && screenerTab !== 'crypto') {
      setLoadingTab(false);
      return;
    }
    // Debounce so rapid filter/search changes coalesce into one request.
    const timer = setTimeout(() => {
      refreshStocks(getQueryCountry());
    }, stockSearch ? 300 : 0);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userCountry, screenerTab, currentPage, limit, filterType, filterSector, filterIndustry, filterCountry, filterMarketCap, filterPE, filterPrice, filterChange, filterVolume, stockSearch]);

  // Automatic yfinance price backfill: whenever a region's screener is shown,
  // pull live prices for the WHOLE market from yfinance so every row on the
  // page (and the rest of the universe) is populated without a manual
  // "Refresh Prices" click. Runs once per country selection; the refresh
  // endpoint chunk-batches large universes server-side.
  const [autoRefreshedMarket, setAutoRefreshedMarket] = useState<string | null>(null);
  const [autoRefreshBusy, setAutoRefreshBusy] = useState(false);
  React.useEffect(() => {
    const qc = getQueryCountry();
    // Skip global markets overview & the demo/empty fallback.
    if (userCountry === 'GLOBAL' || screenerTab === 'markets') return;
    if (!apiStocks.length) return;
    if (autoRefreshedMarket === qc || autoRefreshBusy) return;
    // Refresh when prices are missing OR stale (older than 15 min). The old
    // guard only checked for a missing price, so markets seeded with static
    // CSV prices (CN/DE/CA/HK/FR...) never refreshed — they stayed frozen at
    // the import-day snapshot. Now we refresh on staleness so every country
    // click re-pulls live prices.
    const STALE_MS = 1000 * 60 * 15;
    const needsPrice = apiStocks.some((s) => {
      if (s.priceMissing || !s.price || s.price <= 0) return true;
      if (!s.updatedAt) return true; // no timestamp → assume stale
      return Date.now() - new Date(s.updatedAt).getTime() > STALE_MS;
    });
    if (!needsPrice) {
      setAutoRefreshedMarket(qc);
      return;
    }
    let cancelled = false;
    setAutoRefreshBusy(true);
    (async () => {
      try {
        const res = await fetch('/api/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ market: qc }),
        });
        const data = await res.json();
        if (!cancelled && data && data.success && data.ok > 0) {
          // Live prices now persisted → reload silently so the page reflects them.
          await refreshStocks(qc, true);
        }
        if (!cancelled) setAutoRefreshedMarket(qc);
      } catch {
        if (!cancelled) setAutoRefreshedMarket(qc);
      } finally {
        if (!cancelled) setAutoRefreshBusy(false);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiStocks, currentPage, userCountry, screenerTab, getQueryCountry]);

  // Global markets overview: load available markets + asset counts so the
  // Markets tab shows real data instead of an "unavailable" placeholder.
  const [globalMarkets, setGlobalMarkets] = useState<{ id: string; country: string; exchange: string; isCrypto: boolean; enabled: boolean; assetCount: number; pricedCount: number }[]>([]);
  const [loadingGlobalMarkets, setLoadingGlobalMarkets] = useState(false);
  React.useEffect(() => {
    if (screenerTab !== 'markets') return;
    let cancelled = false;
    (async () => {
      setLoadingGlobalMarkets(true);
      try {
        const res = await fetch('/api/markets');
        const data = await res.json();
        if (!cancelled && data && Array.isArray(data.markets)) {
          setGlobalMarkets(data.markets);
        }
      } catch (err) {
        console.error('Failed to load markets overview:', err);
      } finally {
        if (!cancelled) setLoadingGlobalMarkets(false);
        setLoadingTab(false);
      }
    })();
    return () => { cancelled = true; };
  }, [screenerTab]);



  // Dynamic fallback generator to ensure screen is always populated
  function getFallbackStocks(country: string): StockItem[] {
    const list = [
      { symbol: 'AAPL', name: 'Apple Inc.', sector: 'Technology', industry: 'Consumer Electronics', country: 'USA', price: 189.84, changePercent: 1.25, volume: '52.4M', marketCap: '2.97T', peRatio: '28.4', dividendYield: '0.52%', index: 'S&P 500', recommendation: 'Strong Buy', exchange: 'NASDAQ', forwardPE: '26.1', peg: '2.4', ps: '7.8', pb: '38.2', evEbitda: '21.4', grossMargin: '44.3%', operatingMargin: '29.8%', netProfitMargin: '25.6%', insiderOwnership: '0.07%', institutionalOwnership: '61.4%', shortFloat: '1.2%', rsi14: '54.2', sma20: '+1.2%', sma50: '+3.4%', sma200: '+12.1%' },
      { symbol: 'MSFT', name: 'Microsoft Corp.', sector: 'Technology', industry: 'Software - Infrastructure', country: 'USA', price: 429.20, changePercent: -0.42, volume: '22.8M', marketCap: '3.19T', peRatio: '35.6', dividendYield: '0.70%', index: 'S&P 500', recommendation: 'Buy', exchange: 'NASDAQ', forwardPE: '31.2', peg: '2.8', ps: '12.4', pb: '15.6', evEbitda: '25.2', grossMargin: '68.9%', operatingMargin: '43.2%', netProfitMargin: '35.4%', insiderOwnership: '0.05%', institutionalOwnership: '72.1%', shortFloat: '0.8%', rsi14: '48.5', sma20: '-0.5%', sma50: '+2.1%', sma200: '+18.5%' },
      { symbol: 'NVDA', name: 'NVIDIA Corp.', sector: 'Technology', industry: 'Semiconductors', country: 'USA', price: 1096.50, changePercent: 4.60, volume: '44.2M', marketCap: '2.70T', peRatio: '72.1', dividendYield: '0.04%', index: 'S&P 500', recommendation: 'Strong Buy', exchange: 'NASDAQ', forwardPE: '35.4', peg: '1.2', ps: '32.1', pb: '54.8', evEbitda: '45.1', grossMargin: '76.2%', operatingMargin: '62.4%', netProfitMargin: '53.1%', insiderOwnership: '4.20%', institutionalOwnership: '68.2%', shortFloat: '1.1%', rsi14: '74.2', sma20: '+8.4%', sma50: '+22.5%', sma200: '+85.2%' },
      { symbol: 'BTC', name: 'Bitcoin', sector: 'Layer 1', industry: 'Layer 1', country: 'CRYPTO', price: 67840.00, changePercent: 2.14, volume: '28.4B', marketCap: '1.3T', peRatio: 'N/A', dividendYield: 'None', index: 'Crypto', recommendation: 'Buy', exchange: 'BINANCE', forwardPE: 'N/A', peg: 'N/A', ps: 'N/A', pb: 'N/A', evEbitda: 'N/A', grossMargin: '100%', operatingMargin: '100%', netProfitMargin: '100%', insiderOwnership: '0%', institutionalOwnership: '5%', shortFloat: '0%', rsi14: '58.2', sma20: '+2.4%', sma50: '+12.8%', sma200: '+45.2%' },
      { symbol: 'ETH', name: 'Ethereum', sector: 'Layer 1', industry: 'Layer 1', country: 'CRYPTO', price: 3500.20, changePercent: 2.41, volume: '14.2B', marketCap: '420B', peRatio: 'N/A', dividendYield: 'None', index: 'Crypto', recommendation: 'Strong Buy', exchange: 'BINANCE', forwardPE: 'N/A', peg: 'N/A', ps: 'N/A', pb: 'N/A', evEbitda: 'N/A', grossMargin: '100%', operatingMargin: '100%', netProfitMargin: '100%', insiderOwnership: '0%', institutionalOwnership: '12%', shortFloat: '0%', rsi14: '62.4', sma20: '+3.5%', sma50: '+14.2%', sma200: '+52.1%' },
      { symbol: 'SOL', name: 'Solana', sector: 'Layer 1', industry: 'Layer 1', country: 'CRYPTO', price: 168.40, changePercent: 3.82, volume: '3.8B', marketCap: '76B', peRatio: 'N/A', dividendYield: 'None', index: 'Crypto', recommendation: 'Strong Buy', exchange: 'BINANCE', forwardPE: 'N/A', peg: 'N/A', ps: 'N/A', pb: 'N/A', evEbitda: 'N/A', grossMargin: '100%', operatingMargin: '100%', netProfitMargin: '100%', insiderOwnership: '0%', institutionalOwnership: '8%', shortFloat: '0%', rsi14: '68.5', sma20: '+8.2%', sma50: '+22.4%', sma200: '+88.4%' },
      { symbol: 'BNB', name: 'Binance Coin', sector: 'Exchange Tokens', industry: 'Exchange Tokens', country: 'CRYPTO', price: 585.50, changePercent: -1.20, volume: '1.5B', marketCap: '86B', peRatio: 'N/A', dividendYield: 'None', index: 'Crypto', recommendation: 'Hold', exchange: 'BINANCE', forwardPE: 'N/A', peg: 'N/A', ps: 'N/A', pb: 'N/A', evEbitda: 'N/A', grossMargin: '100%', operatingMargin: '100%', netProfitMargin: '100%', insiderOwnership: '0%', institutionalOwnership: '3%', shortFloat: '0%', rsi14: '45.2', sma20: '-2.1%', sma50: '+4.2%', sma200: '+32.1%' }
    ];
    if (country === 'All') return list;
    const resolved = country === 'CRYPTO' || country === 'Crypto' ? 'CRYPTO' : 'USA';
    return list.filter(item => item.country === resolved);
  }



  const [advFilters, setAdvFilters] = useState<Record<string, string>>({
    shortFloat: 'All', optionShort: 'All', earningsDate: 'All', avgVolume: 'All', relVolume: 'All', currentVolume: 'All', trades: 'All', targetPrice: 'All', ipoDate: 'All', sharesOutstanding: 'All', float: 'All', theme: 'All', subTheme: 'All',
    forwardPE: 'All', peg: 'All', ps: 'All', pb: 'All', priceCash: 'All', priceFreeCashFlow: 'All', evEbitda: 'All', evSales: 'All', dividendGrowth: 'All', epsGrowthThisYear: 'All', epsGrowthNextYear: 'All', epsGrowthQtrOverQtr: 'All', epsGrowthTTM: 'All', epsGrowthPast3Years: 'All', epsGrowthPast5Years: 'All', epsGrowthNext5Years: 'All', salesGrowthQtrOverQtr: 'All', salesGrowthTTM: 'All', salesGrowthPast3Years: 'All', salesGrowthPast5Years: 'All', earningsSurprise: 'All', returnOnAssets: 'All', returnOnEquity: 'All', returnOnInvestedCapital: 'All', currentRatio: 'All', quickRatio: 'All', ltDebtEquity: 'All', debtEquity: 'All', grossMargin: 'All', operatingMargin: 'All', netProfitMargin: 'All', payoutRatio: 'All', insiderOwnership: 'All', insiderTransactions: 'All', institutionalOwnership: 'All', institutionalTransactions: 'All',
    performance: 'All', performance2: 'All', volatility: 'All', rsi14: 'All', gap: 'All', sma20: 'All', sma50: 'All', sma200: 'All', changeFromOpen: 'All', highLow20: 'All', highLow50: 'All', highLow52w: 'All', highLowAllTime: 'All', pattern: 'All', candlestick: 'All', beta: 'All', atr: 'All', afterHoursClose: 'All', afterHoursChange: 'All',
    etfCategory: 'All', etfAssetType: 'All', etfType: 'All', etfSectorTheme: 'All', etfRegion: 'All', etfBondType: 'All', etfAvgMaturity: 'All', etfQuantType: 'All', etfCommodityType: 'All', etfEsgType: 'All', etfDividendType: 'All', etfStructureType: 'All', etfActivePassive: 'All', etfInverseLeveraged: 'All', etfGrowthValue: 'All', etfMarketCap: 'All', etfDevelopedEmerging: 'All', etfCurrency: 'All', etfIndexWeighting: 'All', etfSponsor: 'All', etfNetExpenseRatio: 'All', etfNetFundFlows: 'All', etfAnnualizedReturn: 'All', etfNavPercent: 'All', etfTags: 'All', etfHeldBy: 'All'
  });

  // Fund state
  const [fundSearch, setFundSearch] = useState('');
  const [fundCategory, setFundCategory] = useState('All');
  const [fundSortField, setFundSortField] = useState<keyof FundItem>('symbol');
  const [fundSortOrder, setFundSortOrder] = useState<'asc' | 'desc'>('asc');
  const [apiFunds, setApiFunds] = useState<FundItem[]>([]);
  const [totalFunds, setTotalFunds] = useState(0);

  // ETF state
  const [etfSearch, setEtfSearch] = useState('');
  const [etfCategory, setEtfCategory] = useState('All');
  const [etfSortField, setEtfSortField] = useState<keyof ETFItem>('symbol');
  const [etfSortOrder, setEtfSortOrder] = useState<'asc' | 'desc'>('asc');
  const [apiEtfs, setApiEtfs] = useState<ETFItem[]>([]);
  const [totalEtfs, setTotalEtfs] = useState(0);

  // Fetch real ETF data from JDDS when the ETFs tab is active.
  React.useEffect(() => {
    if (screenerTab !== 'etfs') return;
    let cancelled = false;
    (async () => {
      setLoadingTab(true);
      try {
        const params = new URLSearchParams({ country: userCountry === 'PK' ? 'PK' : 'US', type: 'ETF', limit: '500' });
        if (etfCategory !== 'All') params.set('industry', etfCategory);
        if (etfSearch.trim()) params.set('search', etfSearch.trim());
        const res = await fetch(`/api/stocks?${params.toString()}`);
        const data = await res.json();
        if (!cancelled && data && Array.isArray(data.stocks)) {
          const mapped: ETFItem[] = data.stocks.map((s: any) => ({
            symbol: s.symbol,
            name: s.name,
            category: s.industry || 'General',
            price: s.price || 0,
            changePercent: s.changePercent || 0,
            volume: s.volume || 'N/A',
            aum: s.marketCap || 'N/A',
            expenseRatio: 'N/A',
          }));
          setApiEtfs(mapped);
          setTotalEtfs(data.pagination?.total ?? mapped.length);
        }
      } catch (err) {
        console.error('Failed to load ETFs from JDDS', err);
      } finally {
        if (!cancelled) setLoadingTab(false);
      }
    })();
    return () => { cancelled = true; };
  }, [screenerTab, etfCategory, etfSearch, userCountry]);

  // Fetch real Mutual Fund data from JDDS when the funds tab is active.
  React.useEffect(() => {
    if (screenerTab !== 'funds') return;
    let cancelled = false;
    (async () => {
      setLoadingTab(true);
      try {
        const params = new URLSearchParams({ country: userCountry === 'PK' ? 'PK' : 'US', type: 'Mutual Fund', limit: '500' });
        if (fundSearch.trim()) params.set('search', fundSearch.trim());
        const res = await fetch(`/api/stocks?${params.toString()}`);
        const data = await res.json();
        if (!cancelled && data && Array.isArray(data.stocks)) {
          const mapped: FundItem[] = data.stocks.map((s: any) => ({
            symbol: s.symbol,
            name: s.name,
            category: s.industry || 'General',
            nav: s.price || 0,
            changePercent: s.changePercent || 0,
            ytdReturn: 0,
            expenseRatio: 0,
            rating: 0,
            aum: s.marketCap || 'N/A',
          }));
          setApiFunds(mapped);
          setTotalFunds(data.pagination?.total ?? mapped.length);
        }
      } catch (err) {
        console.error('Failed to load funds from JDDS', err);
      } finally {
        if (!cancelled) setLoadingTab(false);
      }
    })();
    return () => { cancelled = true; };
  }, [screenerTab, fundSearch, userCountry]);

  // Dividend states
  const [dividendSearch, setDividendSearch] = useState('');
  const [dividendSortField, setDividendSortField] = useState<keyof BlueChipItem>('symbol');
  const [dividendSortOrder, setDividendSortOrder] = useState<'asc' | 'desc'>('asc');


  const handleAction = (ticker: string) => {
    onAnalyzeTicker(ticker);
  };

  const exportToPDF = async () => {
    const { default: jsPDF } = await import('jspdf');
    const { default: autoTable } = await import('jspdf-autotable');
    const doc = new jsPDF();
    
    // Title
    doc.setFont("helvetica", "bold");
    doc.setFontSize(16);
    doc.text(`Black Eclipse Market Report - ${screenerTab.replace('_', ' ').toUpperCase()}`, 14, 15);
    
    // Subtitle / Date
    doc.setFont("helvetica", "normal");
    doc.setFontSize(10);
    const regionText = screenerTab === 'crypto' ? 'Global' : userCountry;
    doc.text(`Generated on: ${new Date().toLocaleString()} (Region: ${regionText})`, 14, 22);

    let headers: string[] = [];
    let rows: (string | number)[][] = [];

    if (screenerTab === 'stocks') {
      headers = ['Ticker', 'Company', 'Industry', 'Country', 'Market Cap', 'P/E', 'Price', 'Change %'];
      rows = filteredStocks.map(s => [
        s.symbol, s.name, s.industry, s.country, s.marketCap, s.peRatio, `$${s.price.toFixed(2)}`, `${s.changePercent >= 0 ? '+' : ''}${s.changePercent.toFixed(2)}%`
      ]);
    } else if (screenerTab === 'crypto') {
      headers = ['Ticker', 'Token Name', 'Category', 'Market Cap', 'Price (USDT)', '24h Change'];
      rows = filteredStocks.map(s => [
        s.symbol, s.name, s.sector, s.marketCap, `$${s.price >= 1 ? s.price.toFixed(2) : s.price.toFixed(6)}`, `${s.changePercent >= 0 ? '+' : ''}${s.changePercent.toFixed(2)}%`
      ]);
    }

    autoTable(doc, {
      startY: 28,
      head: [headers],
      body: rows,
      theme: 'grid',
      headStyles: { fillColor: [15, 118, 110] }, // Primary Teal
      styles: { fontSize: 8, cellPadding: 2 },
    });

    const fileRegion = screenerTab === 'crypto' ? 'crypto' : userCountry.toLowerCase();
    doc.save(`black-eclipse-${screenerTab}-${fileRegion}.pdf`);
  };

  // Filter & sort logic (extracted to a pure hook for testability + reuse)
  const {
    filteredStocks,
    filteredFunds,
    filteredETFs,
    filteredDividendStocks,
  } = useScreenerFilters({
    apiStocks, apiEtfs, apiFunds, stockSearch, filterExchange, filterIndex, filterSector, filterIndustry,
    filterCountry, filterMarketCap, filterPE, filterDividendYield, filterPrice,
    filterChange, filterVolume, filterRecommendation, filterMetricType, filterType,
    screenerTab, userCountry, stockSortField, stockSortOrder,
    fundSearch, fundCategory, fundSortField, fundSortOrder,
    etfSearch, etfCategory, etfSortField, etfSortOrder,
    dividendSearch, dividendSortField, dividendSortOrder,
  });

  // Refresh live prices from yfinance into JDDS for the current market.
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMsg, setRefreshMsg] = useState<string | null>(null);
  const handleRefreshPrices = React.useCallback(async () => {
    const marketId = getQueryCountry();
    setRefreshing(true);
    setRefreshMsg(null);
    try {
      // Refresh the symbols currently shown on this page so the user sees
      // live prices immediately.
      const pageSymbols = filteredStocks
        .slice((currentPage - 1) * limit, currentPage * limit)
        .map((s) => s.symbol);
      const res = await fetch('/api/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ market: marketId, symbols: pageSymbols }),
      });
      const data = await res.json();
      if (data.success) {
        setRefreshMsg(`Refreshed ${data.ok} prices from yfinance.`);
        await refreshStocks(marketId, true);
      } else {
        setRefreshMsg(data.error || 'Refresh failed.');
      }
    } catch {
      setRefreshMsg('Refresh failed.');
    } finally {
      setRefreshing(false);
    }
  }, [getQueryCountry, refreshStocks, filteredStocks, currentPage, limit]);

  const toggleStockSort = (field: keyof StockItem) => {
    if (stockSortField === field) {
      setStockSortOrder(prev => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setStockSortField(field);
      setStockSortOrder('asc');
    }
  };

  const toggleFundSort = (field: keyof FundItem) => {
    if (fundSortField === field) {
      setFundSortOrder(prev => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setFundSortField(field);
      setFundSortOrder('asc');
    }
  };

  const toggleEtfSort = (field: keyof ETFItem) => {
    if (etfSortField === field) {
      setEtfSortOrder(prev => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setEtfSortField(field);
      setEtfSortOrder('asc');
    }
  };

  const toggleDividendSort = (field: keyof BlueChipItem) => {
    if (dividendSortField === field) {
      setDividendSortOrder(prev => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setDividendSortField(field);
      setDividendSortOrder('asc');
    }
  };

  if (loadingApi) {
    return (
      <>
        <TopLoader />
        <div className={cn(
          "w-full max-w-7xl mx-auto px-4 md:px-8 py-6 space-y-6 pb-20",
          !embedded && "flex-1 overflow-y-auto h-full scrollbar-hide bg-transparent"
        )}>
          {!embedded && <SkeletonHeader />}

          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 md:gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <SkeletonIndexCard key={i} />
            ))}
          </div>

          <div className="grid lg:grid-cols-3 gap-6">
            <SkeletonPanel className="lg:col-span-2 h-64" />
            <SkeletonPanel className="h-64" />
          </div>

          <SkeletonTable rows={5} />
        </div>
      </>
    );
  }

  return (
    <>
      {(loadingApi || loadingTab || loadingDashboard) && <TopLoader />}
      <div className={cn(
        "w-full max-w-7xl mx-auto px-4 md:px-8 py-6 space-y-8 pb-20 relative bg-transparent",
        !embedded && "flex-1 overflow-y-auto h-full scrollbar-hide"
      )}>
      
      {/* Page Title Header */}
      {!embedded && (
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 animate-fade-in-up border-b border-border/20 pb-6 mb-4">
          <div>
            <h1 className="font-serif text-3xl md:text-4xl font-medium tracking-tight text-foreground flex items-center gap-3">
              <BarChart3 className="text-primary w-8 h-8 animate-pulse" />
              Market Screener
            </h1>
            <p className="text-muted-foreground text-sm mt-2">
              Real-time asset indices, sector breakdowns, high-fidelity stock databases, and automated AI analysis.
            </p>
          </div>
          
          <div className="flex items-center gap-2 bg-accent/40 p-1.5 rounded-3xl border border-border/40 backdrop-blur-md shrink-0 self-start md:self-auto">
            <span className="text-[10px] uppercase font-bold text-muted-foreground/80 px-2 tracking-wider">Market:</span>
            <select
              value={userCountry === 'CRYPTO' ? 'CRYPTO' : (userCountry === 'GLOBAL' && screenerTab === 'stocks') ? 'USA' : userCountry}
              onChange={e => handleMarketSelect(e.target.value)}
              className="bg-background border border-border/60 hover:border-primary/50 rounded-3xl px-3 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary outline-none transition-all cursor-pointer font-semibold"
              title="Select country to load market data"
            >
              <option value="GLOBAL">Global Market</option>
              <option value="USA">United States</option>
              <option value="CN">China</option>
              <option value="TW">Taiwan</option>
              <option value="HK">Hong Kong</option>
              <option value="JP">Japan</option>
              <option value="KR">South Korea</option>
              <option value="IN">India</option>
              <option value="PK">Pakistan (PSX)</option>
              <option value="SG">Singapore</option>
              <option value="MY">Malaysia</option>
              <option value="AU">Australia</option>
              <option value="UK">United Kingdom</option>
              <option value="DE">Germany</option>
              <option value="FR">France</option>
              <option value="NL">Netherlands</option>
              <option value="CA">Canada</option>
              <option value="BR">Brazil</option>
              <option value="MX">Mexico</option>
              <option value="SA">Saudi Arabia</option>
              <option value="AE">UAE</option>
              <option value="ZA">South Africa</option>
              <option value="EG">Egypt</option>
              <option value="NG">Nigeria</option>
              <option value="RU">Russia</option>
              <option value="TR">Turkey</option>
              <option value="ID">Indonesia</option>
              <option value="TH">Thailand</option>
              <option value="VN">Vietnam</option>
              <option value="CRYPTO">Global Crypto</option>
            </select>
            <Button
              size="sm"
              onClick={handleRefreshPrices}
              disabled={refreshing || userCountry === 'GLOBAL'}
              className="cursor-pointer shrink-0"
              title="Fetch live prices from yfinance into JDDS"
            >
              <RefreshCw className={cn("w-3.5 h-3.5 mr-1", refreshing && 'animate-spin')} />
              {refreshing ? 'Refreshing...' : 'Refresh Prices'}
            </Button>
          </div>
          {refreshMsg && (
            <div className="text-[10px] text-muted-foreground font-mono mt-1 text-right">
              {refreshMsg}
            </div>
          )}
        </div>
      )}

      {/* Index Tickers Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 md:gap-4 animate-fade-in-up [animation-delay:100ms]">
        {loadingDashboard ? (
          Array.from({ length: 6 }).map((_, i) => (
            <SkeletonIndexCard key={i} />
          ))
        ) : (
          indexData.map((idxCard) => {
            const isPositive = idxCard.changePercent >= 0;
            return (
              <div 
                key={idxCard.symbol}
                onClick={() => {
                  if (onSelectChartSymbol) {
                    onSelectChartSymbol(idxCard.symbol);
                  } else {
                    handleAction(idxCard.symbol);
                  }
                }}
                className="p-3.5 rounded-2xl bg-[#0f0f0f]/60 dark:bg-[#0f0f0f]/60 bg-white/70 backdrop-blur-xl border border-white/10 dark:border-white/5 hover:border-primary/50 transition-all duration-300 flex flex-col justify-between group cursor-pointer"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-muted-foreground font-semibold uppercase">{idxCard.name}</span>
                    <span className="text-[10px] font-mono font-bold bg-accent/40 px-1.5 py-0.5 rounded text-foreground">{idxCard.symbol}</span>
                  </div>
                  <div className="mt-2 flex items-baseline gap-1">
                    <span className="font-mono text-base font-bold text-foreground">
                      {idxCard.price.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                  <div className={`text-[10px] font-mono font-semibold flex items-center gap-0.5 mt-0.5 ${
                    isPositive ? 'text-emerald-400' : 'text-rose-400'
                  }`}>
                    {isPositive ? <ArrowUpRight size={10} /> : <ArrowDownRight size={10} />}
                    {isPositive ? '+' : ''}{idxCard.changePercent}%
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Split: Sectors Overview & Gainers/Losers */}
      <div className="grid lg:grid-cols-3 gap-6 animate-fade-in-up [animation-delay:200ms]">
        
        {/* Sector Overview List */}
        <div className="lg:col-span-2 p-5 rounded-2xl bg-[#0f0f0f]/60 dark:bg-[#0f0f0f]/60 bg-white/70 backdrop-blur-xl border border-white/10 dark:border-white/5 flex flex-col">
          <div className="flex items-center gap-2 mb-4">
            <Layers className="text-primary w-5 h-5" />
            <h2 className="font-serif text-lg font-semibold tracking-tight text-foreground">Sectors Daily Return Breakdown</h2>
          </div>

          <div className="grid md:grid-cols-2 gap-4 flex-1">
            {loadingDashboard ? (
              Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="flex flex-col justify-center gap-2">
                  <Skeleton className="h-3 w-1/3" />
                  <Skeleton className="h-1.5 w-full rounded-full" />
                </div>
              ))
            ) : (
              sectorPerformance.map(sector => {
                const isPositive = sector.change >= 0;
                return (
                  <div key={sector.name} className="flex flex-col justify-center text-xs">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="font-semibold text-muted-foreground truncate max-w-[170px]">{sector.name}</span>
                      <span className={`font-mono font-bold ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {isPositive ? '+' : ''}{sector.change}%
                      </span>
                    </div>
                    {/* Slider Return Progress bar */}
                    <div className="w-full h-1.5 bg-accent/40 rounded-full overflow-hidden relative border border-border/10">
                      <div 
                        className={`h-full rounded-full transition-all duration-500 ${
                          isPositive ? 'bg-emerald-500/70 shadow-[0_0_8px_rgba(16,185,129,0.3)]' : 'bg-rose-500/70 shadow-[0_0_8px_rgba(239,68,68,0.3)]'
                        }`}
                        style={{ 
                          width: `${Math.min(Math.abs(sector.change) * 35, 100)}%`,
                          marginLeft: isPositive ? '0' : 'auto'
                        }}
                      />
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Top Gainers & Losers Tabbed Split Pane */}
        <div className="p-5 rounded-2xl bg-[#0f0f0f]/60 dark:bg-[#0f0f0f]/60 bg-white/70 backdrop-blur-xl border border-white/10 dark:border-white/5 flex flex-col">
          <div className="flex items-center justify-between mb-4 border-b border-border/20 pb-2">
            <div className="flex items-center gap-2">
              <Award className="text-primary w-5 h-5" />
              <h2 className="font-serif text-base font-semibold tracking-tight">Market Shifters</h2>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 h-full">
            {loadingDashboard ? (
              <>
                <div className="space-y-2">
                  <Skeleton className="h-3 w-20" />
                  {Array.from({ length: 3 }).map((_, i) => (
                    <Skeleton key={i} className="h-10 w-full rounded-xl" />
                  ))}
                </div>
                <div className="space-y-2">
                  <Skeleton className="h-3 w-20" />
                  {Array.from({ length: 3 }).map((_, i) => (
                    <Skeleton key={i} className="h-10 w-full rounded-xl" />
                  ))}
                </div>
              </>
            ) : (
              <>
                {/* Gainers List */}
                <div className="space-y-2">
                  <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-widest flex items-center gap-1 mb-2">
                    ▲ Top Gainers
                  </span>
                  {topGainers.map(item => (
                    <div 
                      key={item.symbol}
                      onClick={() => {
                        if (onSelectChartSymbol) {
                          onSelectChartSymbol(item.symbol);
                        } else {
                          handleAction(item.symbol);
                        }
                      }}
                      className="p-2 bg-emerald-500/5 hover:bg-emerald-500/10 border border-emerald-500/10 rounded-xl flex flex-col text-left transition-colors cursor-pointer"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-[11px] font-bold text-foreground">{item.symbol}</span>
                        <span className="font-mono text-[10px] text-emerald-400 font-semibold">+{item.changePercent}%</span>
                      </div>
                      <span className="text-[9px] text-muted-foreground truncate">{item.name}</span>
                    </div>
                  ))}
                </div>

                {/* Losers List */}
                <div className="space-y-2">
                  <span className="text-[10px] font-bold text-rose-400 uppercase tracking-widest flex items-center gap-1 mb-2">
                    ▼ Top Losers
                  </span>
                  {topLosers.map(item => (
                    <div 
                      key={item.symbol}
                      onClick={() => {
                        if (onSelectChartSymbol) {
                          onSelectChartSymbol(item.symbol);
                        } else {
                          handleAction(item.symbol);
                        }
                      }}
                      className="p-2 bg-rose-500/5 hover:bg-rose-500/10 border border-rose-500/10 rounded-xl flex flex-col text-left transition-colors cursor-pointer"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-[11px] font-bold text-foreground">{item.symbol}</span>
                        <span className="font-mono text-[10px] text-rose-400 font-semibold">{item.changePercent}%</span>
                      </div>
                      <span className="text-[9px] text-muted-foreground truncate">{item.name}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
      {/* Main Screening Tables Master-Detail Grid Container */}
      <div className="w-full">
        <div className="w-full flex flex-col">
          {/* Main Screening Tables Card */}
          <div className="p-6 md:p-8 rounded-3xl bg-[#0f0f0f]/60 dark:bg-[#0f0f0f]/60 bg-white/70 backdrop-blur-xl border border-white/10 dark:border-white/5 flex flex-col animate-fade-in-up [animation-delay:300ms] gap-6 shadow-2xl shadow-black/20">
            
            {/* Dynamic Warning Banner for Delayed/Fallback Data */}
            {dataSource === 'fallback' && (
              <div className="bg-emerald-500/5 border border-emerald-500/10 backdrop-blur-md rounded-2xl p-3.5 flex items-center justify-between animate-fade-in text-emerald-400">
                <div className="flex items-center gap-3">
                  <Info className="w-4 h-4 text-emerald-400 shrink-0" />
                  <div className="text-xs font-semibold">
                    Market data feeds are currently running on a slight delay. Displaying the latest available records from the terminal cache.
                    {dataUpdatedTime && (
                      <span className="text-muted-foreground/80 ml-1.5 font-normal text-emerald-500/70">
                        (Last updated: {new Date(dataUpdatedTime).toLocaleTimeString()})
                      </span>
                    )}
                  </div>
                </div>
                <span className="text-[9px] bg-emerald-500/15 px-2 py-0.5 rounded font-mono font-bold">CACHE DATA</span>
              </div>
            )}
        
        {/* Tab Selection Row - Spacious and Clean */}
        <div className="flex items-center justify-between border-b border-border/15 pb-2 mb-1 flex-wrap gap-2">
          <div className="flex items-center gap-1.5 bg-accent/30 p-1.5 rounded-3xl overflow-x-auto max-w-full scrollbar-none flex-nowrap shrink-0 w-full md:w-auto">
            {screenerTab === 'crypto' ? (
              <span className="px-4 py-2 rounded-3xl text-xs font-bold text-primary flex items-center gap-1.5">
                <Coins className="w-3.5 h-3.5" /> Global Crypto
              </span>
            ) : (
              <>
                <button
                  onClick={() => handleTabChange('markets')}
                  className={`screener-tab px-4 py-2 rounded-3xl text-xs font-bold tracking-tight transition-all duration-200 cursor-pointer flex items-center gap-1.5 shrink-0 ${
                    screenerTab === 'markets'
                      ? 'bg-accent text-foreground' 
                      : 'text-muted-foreground hover:text-foreground hover:bg-accent/40'
                  }`}
                >
                  <Globe className="w-3.5 h-3.5" /> Markets
                </button>
                <button
                  onClick={() => handleTabChange('stocks')}
                  className={`screener-tab px-4 py-2 rounded-3xl text-xs font-bold tracking-tight transition-all duration-200 cursor-pointer flex items-center gap-1.5 shrink-0 ${
                    screenerTab === 'stocks' && (filterType === 'All' || filterType === 'Stock')
                      ? 'bg-accent text-foreground' 
                      : 'text-muted-foreground hover:text-foreground hover:bg-accent/40'
                  }`}
                >
                  <TrendingUp className="w-3.5 h-3.5" /> Stocks
                </button>
                <button
                  onClick={() => handleTabChange('etfs')}
                  className={`screener-tab px-4 py-2 rounded-3xl text-xs font-bold tracking-tight transition-all duration-200 cursor-pointer flex items-center gap-1.5 shrink-0 ${
                    screenerTab === 'etfs' 
                      ? 'bg-accent text-foreground' 
                      : 'text-muted-foreground hover:text-foreground hover:bg-accent/40'
                  }`}
                >
                  <Briefcase className="w-3.5 h-3.5" /> ETFs
                </button>
                <button
                  onClick={() => handleTabChange('funds')}
                  className={`screener-tab px-4 py-2 rounded-3xl text-xs font-bold tracking-tight transition-all duration-200 cursor-pointer flex items-center gap-1.5 shrink-0 ${
                    screenerTab === 'funds' 
                      ? 'bg-accent text-foreground' 
                      : 'text-muted-foreground hover:text-foreground hover:bg-accent/40'
                  }`}
                >
                  <Layers className="w-3.5 h-3.5" /> Mutual Funds
                </button>
                <button
                  onClick={() => { handleTabChange('stocks'); setFilterType('REIT'); }}
                  className={`screener-tab px-4 py-2 rounded-3xl text-xs font-bold tracking-tight transition-all duration-200 cursor-pointer flex items-center gap-1.5 shrink-0 ${
                    screenerTab === 'stocks' && filterType === 'REIT'
                      ? 'bg-accent text-foreground' 
                      : 'text-muted-foreground hover:text-foreground hover:bg-accent/40'
                  }`}
                >
                  <Building2 className="w-3.5 h-3.5" /> REITs
                </button>
                <button
                  onClick={() => { handleTabChange('stocks'); setFilterType('Listed Debt'); }}
                  className={`screener-tab px-4 py-2 rounded-3xl text-xs font-bold tracking-tight transition-all duration-200 cursor-pointer flex items-center gap-1.5 shrink-0 ${
                    screenerTab === 'stocks' && filterType === 'Listed Debt'
                      ? 'bg-accent text-foreground' 
                      : 'text-muted-foreground hover:text-foreground hover:bg-accent/40'
                  }`}
                >
                  <Coins className="w-3.5 h-3.5" /> Bonds
                </button>
              </>
            )}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {loadingApi && <span className="text-[10px] text-muted-foreground/80 animate-pulse bg-accent/20 px-2.5 py-1 rounded-xl font-mono">Syncing Exchange...</span>}
          </div>
        </div>

        {/* Dedicated SPACIOUS Filter Action Bar - Solves Congestion */}
        <div className="flex items-center justify-between bg-accent/10 border border-border/20 rounded-3xl p-4 md:p-5 flex-wrap gap-4">
          {screenerTab === 'stocks' && (
            <div className="flex flex-col-reverse sm:flex-row sm:items-center justify-between w-full gap-4">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setShowAdvancedFilters(!showAdvancedFilters)}
                  className={`filter-toggle px-4 py-2.5 rounded-xl text-xs font-bold tracking-tight transition-all duration-200 cursor-pointer flex items-center gap-2 border h-10 shrink-0 ${
                    showAdvancedFilters
                      ? 'bg-accent text-foreground border-border'
                      : 'text-muted-foreground border-border bg-background/50 hover:border-primary/50 hover:text-foreground hover:bg-accent/40'
                  }`}
                >
                  <Sliders className="w-3.5 h-3.5 text-inherit" /> Advanced Filters
                </button>
              </div>
              <div className="flex items-center gap-4 flex-wrap flex-1 max-w-2xl justify-end">
                {/* Search Input */}
                <div className="relative w-64 min-w-[200px]">
                  <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground w-4 h-4" />
                  <input
                    type="text"
                    placeholder="Search stocks by ticker or name..."
                    value={stockSearch}
                    onChange={e => setStockSearch(e.target.value)}
                    className="w-full bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-10 pr-4 py-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary placeholder:text-muted-foreground/50 transition-all font-mono"
                  />
                </div>
                {/* Type Selector (multi-select dropdown) */}
                <div className="relative min-w-[200px]">
                  <button
                    type="button"
                    onClick={() => setTypeMenuOpen((v) => !v)}
                    className="w-full appearance-none bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-3.5 pr-9 py-2.5 text-xs font-semibold text-foreground focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer transition-all flex items-center justify-between gap-2"
                  >
                    <span className="truncate">
                      {selectedTypes.length > 0 ? selectedTypes.join(', ') : 'All Types'}
                    </span>
                    <ChevronDown className={`w-3.5 h-3.5 text-muted-foreground shrink-0 transition-transform ${typeMenuOpen ? 'rotate-180' : ''}`} />
                  </button>
                  {typeMenuOpen && (
                    <>
                      <div className="fixed inset-0 z-40" onClick={() => setTypeMenuOpen(false)} />
                      <div className="absolute z-50 mt-1 w-56 max-h-72 overflow-y-auto rounded-xl border border-border/40 bg-popover p-1 shadow-xl">
                        <div className="px-2 py-1.5 text-[10px] uppercase tracking-wider text-muted-foreground font-mono">Asset Types</div>
                        <label className="flex items-center gap-2 rounded-md px-2 py-1.5 text-xs cursor-pointer hover:bg-accent/40">
                          <input
                            type="checkbox"
                            checked={selectedTypes.length === 0}
                            onChange={() => { setSelectedTypes([]); setFilterType('All'); }}
                            className="accent-[#7aff78]"
                          />
                          All Types
                        </label>
                        <div className="my-1 h-px bg-border/40" />
                        {filterOptions.types.map((t) => (
                          <label key={t} className="flex items-center gap-2 rounded-md px-2 py-1.5 text-xs cursor-pointer hover:bg-accent/40">
                            <input
                              type="checkbox"
                              checked={selectedTypes.includes(t)}
                              onChange={(e) => {
                                const next = e.target.checked
                                  ? [...selectedTypes, t]
                                  : selectedTypes.filter((x) => x !== t);
                                setSelectedTypes(next);
                                setFilterType(next.length > 0 ? next.join(',') : 'All');
                              }}
                              className="accent-[#7aff78]"
                            />
                            {t}
                          </label>
                        ))}
                      </div>
                    </>
                  )}
                </div>
                {/* Sector/Industry Selector */}
                <div className="relative min-w-[180px]">
                  <select
                    value={sectorIndustryValue}
                    onChange={e => handleSectorIndustryChange(e.target.value)}
                    className="w-full appearance-none bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-3.5 pr-9 py-2.5 text-xs font-semibold text-foreground focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer transition-all"
                  >
                    <option value="All">All Sectors / Industries</option>
                    <optgroup label="Sectors">
                      {filterOptions.sectors.map((s) => (
                        <option key={`s-${s}`} value={s}>{s}</option>
                      ))}
                    </optgroup>
                    <optgroup label="Industries">
                      {filterOptions.industries.map((ind) => (
                        <option key={`i-${ind}`} value={ind}>{ind}</option>
                      ))}
                    </optgroup>
                  </select>
                  <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground w-3.5 h-3.5 pointer-events-none" />
                </div>
              </div>
            </div>
          )}

          {screenerTab === 'crypto' && (
            <div className="flex flex-col-reverse sm:flex-row sm:items-center justify-between w-full gap-4">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setShowAdvancedFilters(!showAdvancedFilters)}
                  className={`filter-toggle px-4 py-2.5 rounded-xl text-xs font-bold tracking-tight transition-all duration-200 cursor-pointer flex items-center gap-2 border h-10 shrink-0 ${
                    showAdvancedFilters
                      ? 'bg-accent text-foreground border-border'
                      : 'text-muted-foreground border-border bg-background/50 hover:border-primary/50 hover:text-foreground hover:bg-accent/40'
                  }`}
                >
                  <Sliders className="w-3.5 h-3.5 text-inherit" /> Filters
                </button>
              </div>
              <div className="flex items-center gap-4 flex-wrap flex-1 max-w-2xl justify-end">
                {/* Search Input */}
                <div className="relative w-64 min-w-[200px]">
                  <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground w-4 h-4" />
                  <input
                    type="text"
                    placeholder="Search crypto by symbol or name..."
                    value={stockSearch}
                    onChange={e => setStockSearch(e.target.value)}
                    className="w-full bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-10 pr-4 py-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary placeholder:text-muted-foreground/50 transition-all font-mono"
                  />
                </div>
                {/* Category Selector */}
                <div className="relative min-w-[160px]">
                  <select
                    value={filterSector}
                    onChange={e => setFilterSector(e.target.value)}
                    className="w-full appearance-none bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-3.5 pr-9 py-2.5 text-xs font-semibold text-foreground focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer transition-all"
                  >
                    <option value="All">All Categories</option>
                    <option value="Layer 1">Layer 1</option>
                    <option value="Layer 2">Layer 2</option>
                    <option value="DeFi">DeFi</option>
                    <option value="Meme Coins">Meme Coins</option>
                    <option value="Gaming">Gaming</option>
                    <option value="AI">AI / Data</option>
                    <option value="DePIN">DePIN</option>
                    <option value="Privacy">Privacy</option>
                    <option value="Payment">Payment</option>
                    <option value="Exchange Tokens">Exchange Tokens</option>
                    <option value="Stablecoins">Stablecoins</option>
                  </select>
                  <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground w-3.5 h-3.5 pointer-events-none" />
                </div>
                {/* Metric Selector / Quick Filters */}
                <div className="relative min-w-[180px]">
                  <select
                    value={filterMetricType}
                    onChange={e => setFilterMetricType(e.target.value)}
                    className="w-full appearance-none bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-3.5 pr-9 py-2.5 text-xs font-semibold text-foreground focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer transition-all"
                  >
                    <option value="All">All Metrics (Filters)</option>
                    <option value="Top Liquidity">Top Liquidity</option>
                    <option value="Near ATH">Near ATH</option>
                    <option value="Most Traded">Most Traded</option>
                    <option value="Low Float">Low Float</option>
                    <option value="High Circulating Ratio">High Circulating Ratio</option>
                  </select>
                  <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground w-3.5 h-3.5 pointer-events-none" />
                </div>
              </div>
            </div>
          )}

          {screenerTab === 'etfs' && (
            <div className="flex flex-col-reverse sm:flex-row sm:items-center justify-between w-full gap-4">
              <div className="flex items-center gap-3">
                <span className="text-xs font-bold text-foreground font-serif">ETF Directory</span>
                <button
                  onClick={() => setShowAdvancedFilters(!showAdvancedFilters)}
                  className={`px-4 py-2.5 rounded-xl text-xs font-bold tracking-tight transition-all duration-200 cursor-pointer flex items-center gap-2 border h-10 shrink-0 ${
                    showAdvancedFilters
                      ? 'bg-primary text-primary-foreground border-primary shadow-md shadow-primary/25'
                      : 'text-muted-foreground border-border bg-background/50 hover:border-primary/50 hover:text-foreground hover:bg-accent/40'
                  }`}
                >
                  <Sliders className="w-3.5 h-3.5 text-inherit" /> Advanced Filters
                </button>
              </div>
              <div className="flex items-center gap-4 flex-wrap flex-1 max-w-2xl justify-end">
                <div className="relative w-64 min-w-[200px]">
                  <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground w-4 h-4" />
                  <input
                    type="text"
                    placeholder="Search ETFs..."
                    value={etfSearch}
                    onChange={e => setEtfSearch(e.target.value)}
                    className="w-full bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-10 pr-4 py-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary placeholder:text-muted-foreground/50 transition-all font-mono"
                  />
                </div>
                <div className="relative min-w-[160px]">
                  <select
                    value={etfCategory}
                    onChange={e => setEtfCategory(e.target.value)}
                    className="w-full appearance-none bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-3.5 pr-9 py-2.5 text-xs font-semibold text-foreground focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer transition-all"
                  >
                    <option value="All">All Categories</option>
                    {Array.from(new Set(apiEtfs.map((e) => e.category).filter(Boolean))).sort().map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground w-3.5 h-3.5 pointer-events-none" />
                </div>
              </div>
            </div>
          )}

          {screenerTab === 'funds' && (
            <div className="flex flex-col-reverse sm:flex-row sm:items-center justify-between w-full gap-4">
              <div className="flex items-center gap-3">
                <span className="text-xs font-bold text-foreground font-serif">Mutual Funds</span>
                <button
                  onClick={() => setShowAdvancedFilters(!showAdvancedFilters)}
                  className={`px-4 py-2.5 rounded-xl text-xs font-bold tracking-tight transition-all duration-200 cursor-pointer flex items-center gap-2 border h-10 shrink-0 ${
                    showAdvancedFilters
                      ? 'bg-primary text-primary-foreground border-primary shadow-md shadow-primary/25'
                      : 'text-muted-foreground border-border bg-background/50 hover:border-primary/50 hover:text-foreground hover:bg-accent/40'
                  }`}
                >
                  <Sliders className="w-3.5 h-3.5 text-inherit" /> Advanced Filters
                </button>
              </div>
              <div className="flex items-center gap-4 flex-wrap flex-1 max-w-2xl justify-end">
                <div className="relative w-64 min-w-[200px]">
                  <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground w-4 h-4" />
                  <input
                    type="text"
                    placeholder="Search Funds..."
                    value={fundSearch}
                    onChange={e => setFundSearch(e.target.value)}
                    className="w-full bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-10 pr-4 py-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary placeholder:text-muted-foreground/50 transition-all font-mono"
                  />
                </div>
                <div className="relative min-w-[180px]">
                  <select
                    value={fundCategory}
                    onChange={e => setFundCategory(e.target.value)}
                    className="w-full appearance-none bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-3.5 pr-9 py-2.5 text-xs font-semibold text-foreground focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer transition-all"
                  >
                    <option value="All">All Categories</option>
                    {Array.from(new Set(apiFunds.map((f) => f.category).filter(Boolean))).sort().map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground w-3.5 h-3.5 pointer-events-none" />
                </div>
              </div>
            </div>
          )}

          {screenerTab === 'dividend_stocks' && (
            <div className="flex flex-col-reverse sm:flex-row sm:items-center justify-between w-full gap-4">
              <div className="flex items-center gap-3">
                <span className="text-xs font-bold text-foreground font-serif">High Dividend Yield Stocks</span>
                <button
                  onClick={() => setShowAdvancedFilters(!showAdvancedFilters)}
                  className={`px-4 py-2.5 rounded-xl text-xs font-bold tracking-tight transition-all duration-200 cursor-pointer flex items-center gap-2 border h-10 shrink-0 ${
                    showAdvancedFilters
                      ? 'bg-primary text-primary-foreground border-primary shadow-md shadow-primary/25'
                      : 'text-muted-foreground border-border bg-background/50 hover:border-primary/50 hover:text-foreground hover:bg-accent/40'
                  }`}
                >
                  <Sliders className="w-3.5 h-3.5 text-inherit" /> Advanced Filters
                </button>
              </div>
              <div className="relative w-64 min-w-[200px]">
                <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground w-4 h-4" />
                <input
                  type="text"
                  placeholder="Search Dividends..."
                  value={dividendSearch}
                  onChange={e => setDividendSearch(e.target.value)}
                  className="w-full bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-10 pr-4 py-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary placeholder:text-muted-foreground/50 transition-all font-mono"
                />
              </div>
            </div>
          )}

          {screenerTab === 'markets' && (
            <div className="flex flex-col-reverse sm:flex-row sm:items-center justify-between w-full gap-4">
              <div className="flex items-center gap-3">
                <span className="text-xs font-bold text-foreground font-serif">Select a Market</span>
              </div>
              <div className="flex items-center gap-4 flex-wrap flex-1 max-w-2xl justify-end">
                <div className="relative w-64 min-w-[200px]">
                  <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground w-4 h-4" />
                  <input
                    type="text"
                    placeholder="Search markets..."
                    value={stockSearch}
                    onChange={e => setStockSearch(e.target.value)}
                    className="w-full bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-10 pr-4 py-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary placeholder:text-muted-foreground/50 transition-all font-mono"
                  />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Advanced Filters Panel - Clean, organized layout */}
        {screenerTab === 'stocks' && showAdvancedFilters && (
          <div className="w-full bg-card/35 border border-border/30 rounded-3xl p-4 md:p-5 backdrop-blur-2xl animate-fade-in text-xs shadow-lg">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-border/20">
              <div className="flex items-center gap-2">
                <Sliders className="w-4 h-4 text-primary" />
                <span className="font-semibold text-sm text-foreground">Advanced Filters</span>
                <span className="text-[10px] text-muted-foreground/70 font-mono">(applied across the full universe)</span>
              </div>
              <button 
                onClick={() => {
                  setFilterExchange('All'); setFilterIndex('All'); setFilterSector('All');
                  setFilterIndustry('All'); setFilterCountry('All'); setFilterMarketCap('All');
                  setFilterPE('All'); setFilterDividendYield('All'); setFilterPrice('All');
                  setFilterChange('All'); setFilterVolume('All'); setFilterRecommendation('All');
                  setFilterType('All'); setSelectedTypes([]);
                }}
                className="text-[10px] text-muted-foreground hover:text-rose-400 font-mono font-bold uppercase tracking-wider transition-colors cursor-pointer flex items-center gap-1"
              >
                <X className="w-3 h-3" /> Reset All
              </button>
            </div>
            
            {/* 3-column grid for filters */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              {/* Type (multi-select dropdown) */}
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-muted-foreground/80 tracking-widest font-mono">Type</span>
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setTypeMenuOpen((v) => !v)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-primary/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer flex items-center justify-between gap-2"
                  >
                    <span className="truncate">
                      {selectedTypes.length > 0 ? selectedTypes.join(', ') : 'Any Type'}
                    </span>
                    <ChevronDown className={`w-3 h-3 text-muted-foreground shrink-0 transition-transform ${typeMenuOpen ? 'rotate-180' : ''}`} />
                  </button>
                  {typeMenuOpen && (
                    <>
                      <div className="fixed inset-0 z-40" onClick={() => setTypeMenuOpen(false)} />
                      <div className="absolute z-50 mt-1 w-56 max-h-72 overflow-y-auto rounded-xl border border-border/40 bg-popover p-1 shadow-xl">
                        <div className="px-2 py-1.5 text-[10px] uppercase tracking-wider text-muted-foreground font-mono">Asset Types</div>
                        <label className="flex items-center gap-2 rounded-md px-2 py-1.5 text-xs cursor-pointer hover:bg-accent/40">
                          <input
                            type="checkbox"
                            checked={selectedTypes.length === 0}
                            onChange={() => { setSelectedTypes([]); setFilterType('All'); }}
                            className="accent-[#7aff78]"
                          />
                          Any Type
                        </label>
                        <div className="my-1 h-px bg-border/40" />
                        {filterOptions.types.map((t) => (
                          <label key={t} className="flex items-center gap-2 rounded-md px-2 py-1.5 text-xs cursor-pointer hover:bg-accent/40">
                            <input
                              type="checkbox"
                              checked={selectedTypes.includes(t)}
                              onChange={(e) => {
                                const next = e.target.checked
                                  ? [...selectedTypes, t]
                                  : selectedTypes.filter((x) => x !== t);
                                setSelectedTypes(next);
                                setFilterType(next.length > 0 ? next.join(',') : 'All');
                              }}
                              className="accent-[#7aff78]"
                            />
                            {t}
                          </label>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              </div>

              {/* Sector / Industry */}
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-primary/80 tracking-widest font-mono">Sector / Industry</span>
                <div className="relative">
                  <select value={sectorIndustryValue} onChange={e => handleSectorIndustryChange(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-primary/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
                    <option value="All">Any Sector / Industry</option>
                    <optgroup label="Sectors">
                      {filterOptions.sectors.map((s) => (
                        <option key={`s-${s}`} value={s}>{s}</option>
                      ))}
                    </optgroup>
                    <optgroup label="Industries">
                      {filterOptions.industries.map((ind) => (
                        <option key={`i-${ind}`} value={ind}>{ind}</option>
                      ))}
                    </optgroup>
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                </div>
              </div>

              {/* Market Cap */}
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-muted-foreground/80 tracking-widest font-mono">Market Cap</span>
                <div className="relative">
                  <select value={filterMarketCap} onChange={e => setFilterMarketCap(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-primary/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
                    <option value="All">Any Cap</option>
                    <option value="Mega">Mega ($100B+)</option>
                    <option value="Large">Large ($10B–$100B)</option>
                    <option value="Mid">Mid ($2B–$10B)</option>
                    <option value="Small">Small (&lt;$2B)</option>
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                </div>
              </div>

              {/* Country */}
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-muted-foreground/80 tracking-widest font-mono">Country</span>
                <div className="relative">
                  <select value={filterCountry} onChange={e => setFilterCountry(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-primary/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
                    <option value="All">Any Country</option>
                    {filterOptions.countries.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                </div>
              </div>

              {/* P/E Ratio */}
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-muted-foreground/80 tracking-widest font-mono">P/E Ratio</span>
                <div className="relative">
                  <select value={filterPE} onChange={e => setFilterPE(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-primary/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
                    <option value="All">Any P/E</option>
                    <option value="Under15">Under 15</option>
                    <option value="Under20">Under 20</option>
                    <option value="Under30">Under 30</option>
                    <option value="Over30">Over 30</option>
                    <option value="Over50">Over 50</option>
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                </div>
              </div>

              {/* Price */}
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-muted-foreground/80 tracking-widest font-mono">Price</span>
                <div className="relative">
                  <select value={filterPrice} onChange={e => setFilterPrice(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-primary/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
                    <option value="All">Any Price</option>
                    <option value="Under10">Under $10</option>
                    <option value="Under50">Under $50</option>
                    <option value="Under100">Under $100</option>
                    <option value="Over100">Over $100</option>
                    <option value="Over500">Over $500</option>
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                </div>
              </div>

              {/* 24h Change */}
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-muted-foreground/80 tracking-widest font-mono">Change %</span>
                <div className="relative">
                  <select value={filterChange} onChange={e => setFilterChange(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-primary/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
                    <option value="All">Any Change</option>
                    <option value="Positive">Positive (&gt;0%)</option>
                    <option value="Negative">Negative (&lt;0%)</option>
                    <option value="Over2">Strong (+2%+)</option>
                    <option value="UnderMinus2">Falling (-2%+)</option>
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Crypto filters panel */}
        {screenerTab === 'crypto' && showAdvancedFilters && (
          <div className="w-full bg-card/35 border border-border/30 rounded-3xl p-4 md:p-5 backdrop-blur-2xl animate-fade-in text-xs shadow-lg">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-border/20">
              <div className="flex items-center gap-2">
                <Sliders className="w-4 h-4 text-primary" />
                <span className="font-semibold text-sm text-foreground">Crypto Filters</span>
              </div>
              <button onClick={() => { setFilterMarketCap('All'); setFilterChange('All'); setFilterSector('All'); }}
                className="text-[10px] text-muted-foreground hover:text-rose-400 font-mono font-bold uppercase tracking-wider transition-colors cursor-pointer flex items-center gap-1">
                <X className="w-3 h-3" /> Reset
              </button>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-primary/80 tracking-widest font-mono">Category</span>
                <div className="relative">
                  <select value={filterSector} onChange={e => setFilterSector(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-primary/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
                    <option value="All">All Categories</option>
                    <option value="Layer 1">Layer 1</option>
                    <option value="Layer 2">Layer 2</option>
                    <option value="DeFi">DeFi</option>
                    <option value="Meme Coins">Meme Coins</option>
                    <option value="Gaming">Gaming</option>
                    <option value="AI">AI / Data</option>
                    <option value="DePIN">DePIN</option>
                    <option value="Privacy">Privacy</option>
                    <option value="Payment">Payment</option>
                    <option value="Exchange Tokens">Exchange Tokens</option>
                    <option value="Stablecoins">Stablecoins</option>
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-muted-foreground/80 tracking-widest font-mono">Market Cap</span>
                <div className="relative">
                  <select value={filterMarketCap} onChange={e => setFilterMarketCap(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-primary/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
                    <option value="All">Any Cap</option>
                    <option value="Mega">Mega ($100B+)</option>
                    <option value="Large">Large ($10B–$100B)</option>
                    <option value="Mid">Mid ($2B–$10B)</option>
                    <option value="Small">Small (&lt;$2B)</option>
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-muted-foreground/80 tracking-widest font-mono">24h Change</span>
                <div className="relative">
                  <select value={filterChange} onChange={e => setFilterChange(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-primary/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
                    <option value="All">Any Change</option>
                    <option value="Positive">Positive (&gt;0%)</option>
                    <option value="Negative">Negative (&lt;0%)</option>
                    <option value="Over2">Strong (+2%+)</option>
                    <option value="UnderMinus2">Falling (-2%+)</option>
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ETF advanced filters panel */}
        {screenerTab === 'etfs' && showAdvancedFilters && (
          <div className="w-full bg-card/35 border border-border/30 rounded-3xl p-4 md:p-5 backdrop-blur-2xl animate-fade-in text-xs shadow-lg">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-border/20">
              <div className="flex items-center gap-2">
                <Sliders className="w-4 h-4 text-primary" />
                <span className="font-semibold text-sm text-foreground">ETF Filters</span>
              </div>
              <button
                onClick={() => { setEtfCategory('All'); }}
                className="text-[10px] text-muted-foreground hover:text-rose-400 font-mono font-bold uppercase tracking-wider transition-colors cursor-pointer flex items-center gap-1"
              >
                <X className="w-3 h-3" /> Reset
              </button>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-primary/80 tracking-widest font-mono">Category</span>
                <div className="relative">
                  <select value={etfCategory} onChange={e => setEtfCategory(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-primary/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
                    <option value="All">All Categories</option>
                    {Array.from(new Set(apiEtfs.map((e) => e.category).filter(Boolean))).sort().map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-muted-foreground/80 tracking-widest font-mono">Change %</span>
                <div className="relative">
                  <select value={filterChange} onChange={e => setFilterChange(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-primary/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
                    <option value="All">Any Change</option>
                    <option value="Positive">Positive (&gt;0%)</option>
                    <option value="Negative">Negative (&lt;0%)</option>
                    <option value="Over2">Strong (+2%+)</option>
                    <option value="UnderMinus2">Falling (-2%+)</option>
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-muted-foreground/80 tracking-widest font-mono">Price</span>
                <div className="relative">
                  <select value={filterPrice} onChange={e => setFilterPrice(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-primary/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
                    <option value="All">Any Price</option>
                    <option value="Under10">Under $10</option>
                    <option value="Under50">Under $50</option>
                    <option value="Under100">Under $100</option>
                    <option value="Over100">Over $100</option>
                    <option value="Over500">Over $500</option>
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Funds advanced filters panel */}
        {screenerTab === 'funds' && showAdvancedFilters && (
          <div className="w-full bg-card/35 border border-border/30 rounded-3xl p-4 md:p-5 backdrop-blur-2xl animate-fade-in text-xs shadow-lg">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-border/20">
              <div className="flex items-center gap-2">
                <Sliders className="w-4 h-4 text-primary" />
                <span className="font-semibold text-sm text-foreground">Fund Filters</span>
              </div>
              <button
                onClick={() => { setFundCategory('All'); }}
                className="text-[10px] text-muted-foreground hover:text-rose-400 font-mono font-bold uppercase tracking-wider transition-colors cursor-pointer flex items-center gap-1"
              >
                <X className="w-3 h-3" /> Reset
              </button>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-primary/80 tracking-widest font-mono">Category</span>
                <div className="relative">
                  <select value={fundCategory} onChange={e => setFundCategory(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-primary/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
                    <option value="All">All Categories</option>
                    {Array.from(new Set(apiFunds.map((f) => f.category).filter(Boolean))).sort().map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-muted-foreground/80 tracking-widest font-mono">Change %</span>
                <div className="relative">
                  <select value={filterChange} onChange={e => setFilterChange(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-primary/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
                    <option value="All">Any Change</option>
                    <option value="Positive">Positive (&gt;0%)</option>
                    <option value="Negative">Negative (&lt;0%)</option>
                    <option value="Over2">Strong (+2%+)</option>
                    <option value="UnderMinus2">Falling (-2%+)</option>
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-muted-foreground/80 tracking-widest font-mono">YTD Return</span>
                <div className="relative">
                  <select value={filterChange} onChange={e => setFilterChange(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-primary/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
                    <option value="All">Any Return</option>
                    <option value="Positive">Positive</option>
                    <option value="Negative">Negative</option>
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Dividend advanced filters panel */}
        {screenerTab === 'dividend_stocks' && showAdvancedFilters && (
          <div className="w-full bg-card/35 border border-border/30 rounded-3xl p-4 md:p-5 backdrop-blur-2xl animate-fade-in text-xs shadow-lg">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-border/20">
              <div className="flex items-center gap-2">
                <Sliders className="w-4 h-4 text-primary" />
                <span className="font-semibold text-sm text-foreground">Dividend Filters</span>
              </div>
              <button
                onClick={() => { setFilterDividendYield('All'); }}
                className="text-[10px] text-muted-foreground hover:text-rose-400 font-mono font-bold uppercase tracking-wider transition-colors cursor-pointer flex items-center gap-1"
              >
                <X className="w-3 h-3" /> Reset
              </button>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-primary/80 tracking-widest font-mono">Dividend Yield</span>
                <div className="relative">
                  <select value={filterDividendYield} onChange={e => setFilterDividendYield(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-primary/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
                    <option value="All">Any Yield</option>
                    <option value="Positive">Positive</option>
                    <option value="Over2">Over 2%</option>
                    <option value="Over5">Over 5%</option>
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-muted-foreground/80 tracking-widest font-mono">Change %</span>
                <div className="relative">
                  <select value={filterChange} onChange={e => setFilterChange(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-primary/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
                    <option value="All">Any Change</option>
                    <option value="Positive">Positive (&gt;0%)</option>
                    <option value="Negative">Negative (&lt;0%)</option>
                    <option value="Over2">Strong (+2%+)</option>
                    <option value="UnderMinus2">Falling (-2%+)</option>
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Active Filter Badges */}
        {(filterSector !== 'All' || filterMarketCap !== 'All' || filterPE !== 'All' ||
          filterDividendYield !== 'All' || filterChange !== 'All' || filterVolume !== 'All' ||
          filterIndustry !== 'All' || filterType !== 'All') && (
          <div className="flex items-center gap-2 flex-wrap p-3 rounded-xl border border-primary/20 bg-primary/5 text-[11px]">
            <span className="text-[10px] font-bold text-primary/70 uppercase tracking-wider font-mono">Active:</span>
            {filterSector !== 'All' && <span className="bg-primary/10 border border-primary/25 text-primary px-2 py-0.5 rounded-lg font-mono font-bold">{filterSector}</span>}
            {filterMarketCap !== 'All' && <span className="bg-primary/10 border border-primary/25 text-primary px-2 py-0.5 rounded-lg font-mono font-bold">Cap: {filterMarketCap}</span>}
            {filterPE !== 'All' && <span className="bg-primary/10 border border-primary/25 text-primary px-2 py-0.5 rounded-lg font-mono font-bold">P/E: {filterPE}</span>}
            {filterDividendYield !== 'All' && <span className="bg-primary/10 border border-primary/25 text-primary px-2 py-0.5 rounded-lg font-mono font-bold">Div: {filterDividendYield}</span>}
            {filterChange !== 'All' && <span className="bg-primary/10 border border-primary/25 text-primary px-2 py-0.5 rounded-lg font-mono font-bold">Δ: {filterChange}</span>}
            {filterVolume !== 'All' && <span className="bg-primary/10 border border-primary/25 text-primary px-2 py-0.5 rounded-lg font-mono font-bold">Vol: {filterVolume}</span>}
            {filterIndustry !== 'All' && <span className="bg-primary/10 border border-primary/25 text-primary px-2 py-0.5 rounded-lg font-mono font-bold">Industry: {filterIndustry}</span>}
            {filterType !== 'All' && <span className="bg-primary/10 border border-primary/25 text-primary px-2 py-0.5 rounded-lg font-mono font-bold">Type: {filterType}</span>}
            <button
              onClick={() => {
                setFilterSector('All'); setFilterMarketCap('All'); setFilterPE('All');
                setFilterDividendYield('All'); setFilterChange('All'); setFilterVolume('All');
                setFilterIndustry('All'); setFilterExchange('All'); setFilterIndex('All');
                setFilterCountry('All'); setFilterPrice('All'); setFilterRecommendation('All');
                setFilterType('All'); setSelectedTypes([]);
              }}
              className="ml-auto text-[10px] text-rose-400 hover:text-rose-300 font-mono font-bold uppercase tracking-wider transition-colors cursor-pointer flex items-center gap-1"
            >
              <X className="w-3 h-3" /> Clear
            </button>
          </div>
        )}



        {/* Screening Table Renderings - Zero Horizontal Scrolling due to responsive cols */}
        {screenerTab === 'markets' && (
          <div className="w-full overflow-x-auto custom-scrollbar bg-[#0f0f0f]/40 dark:bg-[#0f0f0f]/40 bg-white/50 backdrop-blur-xl border border-white/10 dark:border-white/5 rounded-2xl shadow-md">
            <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-white/5">
              <div className="flex items-center gap-2">
                <Globe className="text-primary w-4 h-4" />
                <span className="text-xs font-bold text-foreground uppercase tracking-wider font-mono">Global Markets</span>
              </div>
            </div>
            {loadingGlobalMarkets ? (
              <div className="py-10 text-center text-muted-foreground text-xs">Loading markets...</div>
            ) : globalMarkets.length === 0 ? (
              <div className="py-10 text-center text-muted-foreground text-xs">
                No markets loaded yet. Select a market above to view its screener and prices will be pulled automatically.
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 p-3">
                {globalMarkets.map((m) => (
                  <button
                    key={m.id}
                    onClick={() => handleMarketSelect(m.isCrypto ? 'CRYPTO' : m.id)}
                    className="text-left p-4 rounded-2xl bg-[#0f0f0f]/50 hover:bg-[#0f0f0f]/80 border border-white/10 dark:border-white/5 hover:border-primary/50 transition-all duration-300 cursor-pointer flex flex-col gap-1.5 group"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-serif font-semibold text-sm text-foreground truncate">{m.country}</span>
                      {m.isCrypto && (
                        <span className="text-[9px] font-bold text-primary bg-primary/10 border border-primary/20 rounded-full px-2 py-0.5 font-mono">CRYPTO</span>
                      )}
                    </div>
                    <span className="text-[10px] text-muted-foreground font-mono">{m.exchange}</span>
                    <div className="mt-1 flex items-center gap-3 text-[10px] font-mono">
                      <span className="text-foreground/80 font-bold">{m.pricedCount.toLocaleString()}</span>
                      <span className="text-muted-foreground/70">/ {m.assetCount.toLocaleString()} assets priced</span>
                    </div>
                    <div className="w-full h-1.5 bg-accent/40 rounded-full overflow-hidden mt-1">
                      <div
                        className="h-full bg-primary rounded-full transition-all duration-500"
                        style={{ width: `${m.assetCount > 0 ? Math.min(100, (m.pricedCount / m.assetCount) * 100) : 0}%` }}
                      />
                    </div>
                    <span className="text-[9px] text-primary/80 font-semibold mt-1 opacity-0 group-hover:opacity-100 transition-opacity uppercase tracking-wider">
                      Open screener →
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {screenerTab === 'stocks' && (
          <>
            <div className="w-full overflow-x-auto custom-scrollbar bg-[#0f0f0f]/40 dark:bg-[#0f0f0f]/40 bg-white/50 backdrop-blur-xl border border-white/10 dark:border-white/5 rounded-2xl shadow-md">
              <table className="w-full text-left border-collapse text-[11px]">
                <thead>
                  <tr className="border-b border-white/5 text-muted-foreground/80 text-[10px] uppercase tracking-wider font-mono font-semibold bg-white/[0.01]">
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground font-mono transition-colors whitespace-nowrap" onClick={() => toggleStockSort('symbol')}>
                      Ticker {stockSortField === 'symbol' && (stockSortOrder === 'asc' ? '▲' : '▼')}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('name')}>
                      Company {stockSortField === 'name' && (stockSortOrder === 'asc' ? '▲' : '▼')}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden md:table-cell whitespace-nowrap" onClick={() => toggleStockSort('securityType')}>
                      Type {stockSortField === 'securityType' && (stockSortOrder === 'asc' ? '▲' : '▼')}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden lg:table-cell whitespace-nowrap" onClick={() => toggleStockSort('industry')}>
                      Industry {stockSortField === 'industry' && (stockSortOrder === 'asc' ? '▲' : '▼')}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden lg:table-cell whitespace-nowrap" onClick={() => toggleStockSort('country')}>
                      Country {stockSortField === 'country' && (stockSortOrder === 'asc' ? '▲' : '▼')}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors hidden sm:table-cell whitespace-nowrap" onClick={() => toggleStockSort('marketCap')}>
                      Market Cap {stockSortField === 'marketCap' && (stockSortOrder === 'asc' ? '▲' : '▼')}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors hidden sm:table-cell whitespace-nowrap" onClick={() => toggleStockSort('peRatio')}>
                      P/E {stockSortField === 'peRatio' && (stockSortOrder === 'asc' ? '▲' : '▼')}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('price')}>
                      Price {stockSortField === 'price' && (stockSortOrder === 'asc' ? '▲' : '▼')}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('changePercent')}>
                      Change {stockSortField === 'changePercent' && (stockSortOrder === 'asc' ? '▲' : '▼')}
                    </th>
                    <th className="py-3 px-4 text-center whitespace-nowrap">AI Analyst</th>
                  </tr>
                </thead>
                <tbody>
                  {(loadingTab || (loadingApi && filteredStocks.length === 0)) ? (
                    <TableSkeleton cols={10} rows={8} />
                  ) : filteredStocks.length === 0 ? (
                    <tr>
                      <td colSpan={10} className="p-6 text-center text-muted-foreground font-medium whitespace-nowrap ">
                        No matching stocks found.
                      </td>
                    </tr>
                  ) : (
                    filteredStocks.map((stock) => {
                      const isPositive = stock.changePercent >= 0;
                      return (
                        <tr 
                          key={stock.symbol}
                          onClick={() => handleSymbolClick(stock.symbol, stock.name, stock)}
                          className="border-b border-white/5 hover:bg-white/[0.02] transition-colors cursor-pointer group"
                        >
                          <td 
                            onClick={(e) => {
                              e.stopPropagation();
                              handleSymbolClick(stock.symbol, stock.name, stock);
                            }}
                            className="py-1 px-2 border border-border/30 font-bold font-mono text-primary hover:underline whitespace-nowrap"
                          >
                            {stock.symbol}
                          </td>
                          <td className="py-3 px-4 text-foreground/85 whitespace-nowrap">{stock.name}</td>
                          <td className="py-3 px-4 text-foreground/75 hidden md:table-cell whitespace-nowrap">
                            <span className="bg-primary/5 text-primary border border-primary/10 rounded-full px-2 py-0.5 text-[9px] font-bold">
                              {stock.securityType || 'N/A'}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-foreground/75 hidden lg:table-cell whitespace-nowrap">{stock.industry}</td>
                          <td className="py-3 px-4 text-foreground/75 hidden lg:table-cell whitespace-nowrap">{stock.country}</td>
                          <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden sm:table-cell whitespace-nowrap">{stock.marketCap}</td>
                          <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden sm:table-cell whitespace-nowrap">{stock.peRatio}</td>
                          <td className="py-3 px-4 text-right font-mono font-bold text-foreground whitespace-nowrap">
                            {stock.priceMissing || !stock.price || stock.price <= 0 ? (
                              <span className="inline-flex items-center gap-1.5">
                                <Skeleton className="h-3.5 w-16 inline-block" />
                                <span className="text-[9px] text-muted-foreground/60 animate-pulse">fetching...</span>
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1.5">
                                ${stock.price.toFixed(2)}
                                {stock.priceSource === 'csv' && (
                                  <span
                                    className="text-[8px] uppercase font-bold px-1 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20"
                                    title="Imported historical / API price"
                                  >
                                    CSV
                                  </span>
                                )}
                              </span>
                            )}
                          </td>
                          <td className={cn(
                            "py-1 px-2 border border-border/30 text-right font-mono font-bold whitespace-nowrap",
                            isPositive ? 'text-emerald-400' : 'text-rose-400'
                          )}>
                            {stock.priceMissing || !stock.price || stock.price <= 0 ? (
                              <Skeleton className="h-3.5 w-12 inline-block" />
                            ) : (
                              `${isPositive ? '+' : ''}${stock.changePercent.toFixed(2)}%`
                            )}
                          </td>
                          <td className="py-3 px-4 text-center whitespace-nowrap" onClick={e => e.stopPropagation()}>
                            <Button
                              size="sm"
                              onClick={() => handleAction(stock.symbol)}
                              className="inline-flex items-center gap-1 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 hover:border-primary/40 px-2 rounded-lg py-0.5 h-auto text-[9px] font-semibold transition-all hover:scale-105 cursor-pointer"
                            >
                              <Sparkles size={10} className="mr-1 inline animate-pulse" /> Analyze
                            </Button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            <div className="flex items-center justify-between border-t border-border/10 pt-5 px-2 flex-wrap gap-4">
              <div className="flex items-center gap-4 text-[11px] text-muted-foreground font-medium">
                <div>
                  Showing <span className="font-semibold font-mono text-foreground">{totalStocks > 0 ? ((currentPage - 1) * limit) + 1 : 0}</span> to{' '}
                  <span className="font-semibold font-mono text-foreground">{Math.min(currentPage * limit, totalStocks)}</span> of{' '}
                  <span className="font-semibold font-mono text-foreground">{totalStocks}</span> stocks
                </div>
                <div className="flex items-center gap-2 bg-accent/20 px-3 py-1.5 rounded-xl border border-border/30">
                  <span className="text-[10px] uppercase font-bold text-muted-foreground/80">Show:</span>
                  <select
                    value={limit}
                    onChange={(e) => setLimit(Number(e.target.value))}
                    className="bg-transparent text-[11px] font-bold text-foreground font-mono focus:outline-none cursor-pointer"
                  >
                    <option value={20} className="bg-card text-foreground">20</option>
                    <option value={50} className="bg-card text-foreground">50</option>
                    <option value={100} className="bg-card text-foreground">100</option>
                  </select>
                </div>
              </div>
              {totalStocks > limit && (
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                    disabled={currentPage === 1}
                    className="px-3 py-1 text-[11px] font-semibold h-7 border-border bg-background/50 hover:bg-accent disabled:opacity-50"
                  >
                    Previous
                  </Button>
                  <div className="text-[11px] font-mono font-bold px-2.5 py-0.5 bg-accent/30 rounded-lg">
                    Page {currentPage} of {Math.ceil(totalStocks / limit)}
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentPage(prev => Math.min(prev + 1, Math.ceil(totalStocks / limit)))}
                    disabled={currentPage >= Math.ceil(totalStocks / limit)}
                    className="px-3 py-1 text-[11px] font-semibold h-7 border-border bg-background/50 hover:bg-accent disabled:opacity-50"
                  >
                    Next
                  </Button>
                </div>
              )}
            </div>
          </>
        )}

        {screenerTab === 'crypto' && (
          <>
            <div className="w-full overflow-x-auto custom-scrollbar bg-[#0f0f0f]/40 dark:bg-[#0f0f0f]/40 bg-white/50 backdrop-blur-xl border border-white/10 dark:border-white/5 rounded-2xl shadow-md">
              <table className="w-full text-left border-collapse text-[11px]">
                <thead>
                  <tr className="border-b border-white/5 text-muted-foreground/80 text-[10px] uppercase tracking-wider font-mono font-semibold bg-white/[0.01]">
                    <th className="py-3 px-4 text-center whitespace-nowrap cursor-pointer hover:text-foreground transition-colors" onClick={() => toggleStockSort('rank')}>
                      Rank {stockSortField === 'rank' && (stockSortOrder === 'asc' ? '▲' : '▼')}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground font-mono transition-colors whitespace-nowrap" onClick={() => toggleStockSort('symbol')}>
                      Symbol {stockSortField === 'symbol' && (stockSortOrder === 'asc' ? '▲' : '▼')}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('name')}>
                      Asset Name {stockSortField === 'name' && (stockSortOrder === 'asc' ? '▲' : '▼')}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('sector')}>
                      Category {stockSortField === 'sector' && (stockSortOrder === 'asc' ? '▲' : '▼')}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('price')}>
                      Price {stockSortField === 'price' && (stockSortOrder === 'asc' ? '▲' : '▼')}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('changePercent')}>
                      24H Change {stockSortField === 'changePercent' && (stockSortOrder === 'asc' ? '▲' : '▼')}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('marketCap')}>
                      Market Cap {stockSortField === 'marketCap' && (stockSortOrder === 'asc' ? '▲' : '▼')}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('volume')}>
                      24H Volume {stockSortField === 'volume' && (stockSortOrder === 'asc' ? '▲' : '▼')}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('circulatingSupply')}>
                      Circulating Supply {stockSortField === 'circulatingSupply' && (stockSortOrder === 'asc' ? '▲' : '▼')}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('maxSupply')}>
                      Max Supply {stockSortField === 'maxSupply' && (stockSortOrder === 'asc' ? '▲' : '▼')}
                    </th>
                    <th className="py-3 px-4 text-center cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('ath')}>
                      ATH Distance {stockSortField === 'ath' && (stockSortOrder === 'asc' ? '▲' : '▼')}
                    </th>
                    <th className="py-3 px-4 text-center whitespace-nowrap">AI Analyst</th>
                  </tr>
                </thead>
                <tbody>
                  {(loadingTab || (loadingApi && filteredStocks.length === 0)) ? (
                    <TableSkeleton cols={12} rows={8} />
                  ) : filteredStocks.length === 0 ? (
                    <tr>
                      <td colSpan={12} className="p-6 text-center text-muted-foreground font-medium whitespace-nowrap ">
                        No matching cryptocurrencies found.
                      </td>
                    </tr>
                  ) : (
                    (() => {
                      const maxMarketCapRaw = Math.max(...filteredStocks.map(s => s.marketCapRaw || 0), 1);
                      return filteredStocks.map((stock) => {
                        const isPositive = stock.changePercent >= 0;
                        const formatCryptoPrice = (val: number) => {
                          if (val === 0) return '0.00';
                          if (val < 0.0001) return val.toFixed(8);
                          if (val < 0.01) return val.toFixed(6);
                          if (val < 1) return val.toFixed(4);
                          if (val >= 1000) return val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                          return val.toFixed(2);
                        };
                        
                        const circPercent = stock.maxSupplyRaw && stock.maxSupplyRaw > 0
                          ? ((stock.circulatingSupplyRaw || 0) / stock.maxSupplyRaw * 100).toFixed(1) + '%'
                          : '100.0%';

                        const athDist = stock.athChangePercent || 0;
                        let athBadgeText = 'Mid Range';
                        let athColorClass = 'text-amber-400 bg-amber-500/10 border-amber-500/25';
                        let AthIcon = ArrowRight;
                        if (athDist >= -10) {
                          athBadgeText = 'Near ATH';
                          athColorClass = 'text-emerald-400 bg-emerald-500/10 border-emerald-500/25';
                          AthIcon = ArrowUpRight;
                        } else if (athDist <= -50) {
                          athBadgeText = 'Deep Discount';
                          athColorClass = 'text-rose-400 bg-rose-500/10 border-rose-500/25';
                          AthIcon = ArrowDownRight;
                        }

                        const isExpanded = expandedSymbol === stock.symbol;

                        return (
                          <React.Fragment key={stock.symbol}>
                            <tr 
                              onClick={() => setExpandedSymbol(isExpanded ? null : stock.symbol)}
                              className="border-b border-white/5 hover:bg-white/[0.02] transition-colors cursor-pointer group"
                            >
                              <td className="py-3 px-4 text-muted-foreground text-center font-mono">
                                #{stock.rank || 999}
                              </td>
                              <td 
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleSymbolClick(stock.symbol, stock.name, stock);
                                }}
                                className="py-2 px-2 border border-border/30 font-bold font-mono text-primary hover:underline whitespace-nowrap"
                              >
                                {stock.symbol}
                              </td>
                              <td 
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleSymbolClick(stock.symbol, stock.name, stock);
                                }}
                                className="py-2 px-2 border border-border/30 text-foreground/85 truncate max-w-[130px] whitespace-nowrap hover:underline"
                              >
                                {stock.name}
                              </td>
                              <td className="py-3 px-4 text-foreground/75 whitespace-nowrap">
                                <span className="bg-primary/5 text-primary border border-primary/10 rounded-full px-2 py-0.5 text-[9px] font-bold">
                                  {stock.sector}
                                </span>
                              </td>
                              <td className="py-3 px-4 text-right font-mono font-bold text-foreground whitespace-nowrap">
                                {stock.priceMissing || !stock.price || stock.price <= 0 ? (
                                  <span className="inline-flex items-center gap-1.5">
                                    <Skeleton className="h-3.5 w-16 inline-block" />
                                    <span className="text-[9px] text-muted-foreground/60 animate-pulse">fetching...</span>
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center gap-1.5">
                                    ${formatCryptoPrice(stock.price)}
                                    {stock.priceSource === 'csv' && (
                                      <span
                                        className="text-[8px] uppercase font-bold px-1 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20"
                                        title="Imported historical / API price"
                                      >
                                        CSV
                                      </span>
                                    )}
                                  </span>
                                )}
                              </td>
                              <td className={cn(
                                "py-2 px-2 border border-border/30 text-right font-mono font-bold whitespace-nowrap",
                                isPositive ? 'text-emerald-400' : 'text-rose-400'
                              )}>
                                {stock.priceMissing || !stock.price || stock.price <= 0 ? (
                                  <Skeleton className="h-3.5 w-12 inline-block" />
                                ) : (
                                  `${isPositive ? '+' : ''}${stock.changePercent.toFixed(2)}%`
                                )}
                              </td>
                              <td className="py-3 px-4 font-mono text-foreground/75 whitespace-nowrap">
                                <div className="flex flex-col gap-1 w-24 ml-auto">
                                  <div className="text-right">{stock.marketCap}</div>
                                  <div className="w-full h-1 bg-accent/40 rounded-full overflow-hidden">
                                    <div 
                                      className="h-full bg-primary rounded-full" 
                                      style={{ width: `${Math.min(100, ((stock.marketCapRaw || 0) / maxMarketCapRaw) * 100)}%` }} 
                                    />
                                  </div>
                                </div>
                              </td>
                              <td className="py-3 px-4 text-right font-mono text-foreground/75 whitespace-nowrap">
                                {stock.volume || 'N/A'}
                              </td>
                              <td className="py-3 px-4 text-right font-mono text-foreground/75 whitespace-nowrap">
                                {stock.circulatingSupply || 'N/A'}
                              </td>
                              <td className="py-3 px-4 text-right font-mono text-foreground/75 whitespace-nowrap">
                                {stock.maxSupply || 'N/A'}
                              </td>
                              <td className="py-3 px-4 text-center whitespace-nowrap">
                                <span className={cn("inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[9px] font-bold border", athColorClass)}>
                                  <AthIcon className="w-3 h-3 text-inherit" /> {athBadgeText} ({athDist.toFixed(1)}%)
                                </span>
                              </td>
                              <td className="py-3 px-4 text-center whitespace-nowrap" onClick={e => e.stopPropagation()}>
                                <Button
                                  size="sm"
                                  onClick={() => {
                                    const customContext = `${stock.symbol} currently trades ${Math.abs(stock.athChangePercent || 0).toFixed(1)}% below its all-time high while maintaining a ${stock.marketCap} market capitalization and ${stock.volumeRaw ? '$' + (stock.volumeRaw / 1e6).toFixed(1) + 'M' : 'N/A'} daily volume. Circulating supply stands at ${circPercent} of maximum issuance, suggesting most dilution has already occurred.`;
                                    onAnalyzeTicker(stock.symbol, customContext);
                                  }}
                                  className="inline-flex items-center gap-1 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 hover:border-primary/40 px-2 rounded-lg py-0.5 h-auto text-[9px] font-semibold transition-all hover:scale-105 cursor-pointer"
                                >
                                  <Sparkles size={10} className="mr-1 inline animate-pulse" /> Analyze
                                </Button>
                              </td>
                            </tr>

                            {isExpanded && (
                              <tr className="bg-accent/10">
                                <td colSpan={12} className="p-4 ">
                                  <div className="flex flex-wrap items-center gap-6 justify-center md:justify-start">
                                    <div className="flex flex-col gap-1 bg-background/40 border border-border/20 rounded-xl p-3 min-w-[150px]">
                                      <span className="text-[9px] uppercase font-bold text-muted-foreground tracking-wider font-mono">Liquidity</span>
                                      <span className="text-xs font-mono font-bold text-foreground">24H Volume:</span>
                                      <span className="text-sm font-mono font-black text-primary">{stock.volume || 'N/A'}</span>
                                    </div>
                                    <div className="flex flex-col gap-1 bg-background/40 border border-border/20 rounded-xl p-3 min-w-[180px]">
                                      <span className="text-[9px] uppercase font-bold text-muted-foreground tracking-wider font-mono">Supply Status</span>
                                      <span className="text-xs font-mono font-bold text-foreground">Circulating / Max:</span>
                                      <span className="text-xs font-mono text-foreground">{stock.circulatingSupply || 'N/A'} / {stock.maxSupply || 'N/A'}</span>
                                    </div>
                                    <div className="flex flex-col gap-1 bg-background/40 border border-border/20 rounded-xl p-3 min-w-[150px]">
                                      <span className="text-[9px] uppercase font-bold text-muted-foreground tracking-wider font-mono">Scarcity Indicator</span>
                                      <span className="text-xs font-mono font-bold text-foreground">Supply Mined:</span>
                                      <span className="text-sm font-mono font-black text-emerald-400">{circPercent} mined</span>
                                    </div>
                                  </div>
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
                        );
                      });
                    })()
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            <div className="flex items-center justify-between border-t border-border/10 pt-5 px-2 flex-wrap gap-4">
              <div className="flex items-center gap-4 text-[11px] text-muted-foreground font-medium">
                <div>
                  Showing <span className="font-semibold font-mono text-foreground">{totalStocks > 0 ? ((currentPage - 1) * limit) + 1 : 0}</span> to{' '}
                  <span className="font-semibold font-mono text-foreground">{Math.min(currentPage * limit, totalStocks)}</span> of{' '}
                  <span className="font-semibold font-mono text-foreground">{totalStocks}</span> tokens
                </div>
                <div className="flex items-center gap-2 bg-accent/20 px-3 py-1.5 rounded-xl border border-border/30">
                  <span className="text-[10px] uppercase font-bold text-muted-foreground/80">Show:</span>
                  <select
                    value={limit}
                    onChange={(e) => setLimit(Number(e.target.value))}
                    className="bg-transparent text-[11px] font-bold text-foreground font-mono focus:outline-none cursor-pointer"
                  >
                    <option value={20} className="bg-card text-foreground">20</option>
                    <option value={50} className="bg-card text-foreground">50</option>
                    <option value={100} className="bg-card text-foreground">100</option>
                  </select>
                </div>
              </div>
              {totalStocks > limit && (
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                    disabled={currentPage === 1}
                    className="px-3 py-1 text-[11px] font-semibold h-7 border-border bg-background/50 hover:bg-accent disabled:opacity-50"
                  >
                    Previous
                  </Button>
                  <div className="text-[11px] font-mono font-bold px-2.5 py-0.5 bg-accent/30 rounded-lg">
                    Page {currentPage} of {Math.ceil(totalStocks / limit)}
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentPage(prev => Math.min(prev + 1, Math.ceil(totalStocks / limit)))}
                    disabled={currentPage >= Math.ceil(totalStocks / limit)}
                    className="px-3 py-1 text-[11px] font-semibold h-7 border-border bg-background/50 hover:bg-accent disabled:opacity-50"
                  >
                    Next
                  </Button>
                </div>
              )}
            </div>
          </>
        )}

        {screenerTab === 'etfs' && (
          <div className="w-full overflow-x-auto custom-scrollbar bg-[#0f0f0f]/40 dark:bg-[#0f0f0f]/40 bg-white/50 backdrop-blur-xl border border-white/10 dark:border-white/5 rounded-2xl shadow-md">
            <table className="w-full text-left border-collapse text-[11px]">
              <thead>
                <tr className="border-b border-white/5 text-muted-foreground/80 text-[10px] uppercase tracking-wider font-mono font-semibold bg-white/[0.01]">
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground font-mono transition-colors whitespace-nowrap" onClick={() => toggleEtfSort('symbol')}>
                    Symbol {etfSortField === 'symbol' && (etfSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleEtfSort('name')}>
                    ETF Name {etfSortField === 'name' && (etfSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden sm:table-cell whitespace-nowrap" onClick={() => toggleEtfSort('category')}>
                    Category {etfSortField === 'category' && (etfSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleEtfSort('price')}>
                    Price {etfSortField === 'price' && (etfSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleEtfSort('changePercent')}>
                    Change % {etfSortField === 'changePercent' && (etfSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 text-right font-mono hidden md:table-cell whitespace-nowrap">Volume</th>
                  <th className="py-3 px-4 text-right font-mono hidden md:table-cell whitespace-nowrap">AUM</th>
                  <th className="py-3 px-4 text-right font-mono hidden lg:table-cell whitespace-nowrap">Expense Ratio</th>
                  <th className="py-3 px-4 text-center whitespace-nowrap">AI Analyst</th>
                </tr>
              </thead>
              <tbody>
                {loadingTab ? (
                  <TableSkeleton cols={9} rows={6} />
                ) : filteredETFs.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="p-6 text-center text-muted-foreground font-medium whitespace-nowrap ">
                      No matching ETFs found.
                    </td>
                  </tr>
                ) : (
                  filteredETFs.map((etf) => {
                    const isPositive = etf.changePercent >= 0;
                    return (
                      <tr 
                        key={etf.symbol}
                        className="hover:bg-accent/20 even:bg-accent/5 odd:bg-transparent transition-colors font-medium"
                      >
                        <td 
                          onClick={() => handleSymbolClick(etf.symbol, etf.name, { marketCap: etf.aum, price: etf.price, changePercent: etf.changePercent, volume: etf.volume })}
                          className="py-1 px-2 border border-border/30 font-bold font-mono text-primary hover:underline whitespace-nowrap cursor-pointer"
                        >
                          {etf.symbol}
                        </td>
                        <td className="py-3 px-4 text-foreground/80 truncate max-w-[130px] whitespace-nowrap">{etf.name}</td>
                        <td className="py-3 px-4 text-foreground/75 hidden sm:table-cell whitespace-nowrap">{etf.category}</td>
                        <td className="py-3 px-4 text-right font-mono font-bold text-foreground whitespace-nowrap">${etf.price.toFixed(2)}</td>
                        <td className={cn(
                          "py-1 px-2 border border-border/30 text-right font-mono font-bold whitespace-nowrap",
                          isPositive ? 'text-emerald-400' : 'text-rose-400'
                        )}>
                          {isPositive ? '+' : ''}{etf.changePercent.toFixed(2)}%
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden md:table-cell whitespace-nowrap">{etf.volume}</td>
                        <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden md:table-cell whitespace-nowrap">{etf.aum}</td>
                        <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden lg:table-cell whitespace-nowrap">{etf.expenseRatio}</td>
                        <td className="py-3 px-4 text-center whitespace-nowrap">
                          <Button
                            size="sm"
                            onClick={() => handleAction(etf.symbol)}
                            className="inline-flex items-center gap-1 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 hover:border-primary/40 px-2 rounded-lg py-0.5 h-auto text-[9px] font-semibold transition-all hover:scale-105 cursor-pointer"
                          >
                            <Sparkles size={10} className="mr-1 inline" /> Analyze
                          </Button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}

        {screenerTab === 'funds' && (
          <div className="w-full overflow-x-auto custom-scrollbar bg-[#0f0f0f]/40 dark:bg-[#0f0f0f]/40 bg-white/50 backdrop-blur-xl border border-white/10 dark:border-white/5 rounded-2xl shadow-md">
            <table className="w-full text-left border-collapse text-[11px]">
              <thead>
                <tr className="border-b border-white/5 text-muted-foreground/80 text-[10px] uppercase tracking-wider font-mono font-semibold bg-white/[0.01]">
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground font-mono transition-colors whitespace-nowrap" onClick={() => toggleFundSort('symbol')}>
                    Symbol {fundSortField === 'symbol' && (fundSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleFundSort('name')}>
                    Fund Name {fundSortField === 'name' && (fundSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden sm:table-cell whitespace-nowrap" onClick={() => toggleFundSort('category')}>
                    Category {fundSortField === 'category' && (fundSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleFundSort('nav')}>
                    NAV {fundSortField === 'nav' && (fundSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleFundSort('changePercent')}>
                    1D Change % {fundSortField === 'changePercent' && (fundSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors hidden md:table-cell whitespace-nowrap" onClick={() => toggleFundSort('ytdReturn')}>
                    YTD Return % {fundSortField === 'ytdReturn' && (fundSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors hidden lg:table-cell whitespace-nowrap" onClick={() => toggleFundSort('expenseRatio')}>
                    Expense Ratio {fundSortField === 'expenseRatio' && (fundSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 text-center hidden md:table-cell whitespace-nowrap">Morningstar</th>
                  <th className="py-3 px-4 text-right font-mono hidden lg:table-cell whitespace-nowrap">AUM</th>
                  <th className="py-3 px-4 text-center whitespace-nowrap">AI Brief</th>
                </tr>
              </thead>
              <tbody>
                {loadingTab ? (
                  <TableSkeleton cols={10} rows={6} />
                ) : filteredFunds.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="p-6 text-center text-muted-foreground font-medium whitespace-nowrap ">
                      No matching funds found.
                    </td>
                  </tr>
                ) : (
                  filteredFunds.map((fund) => {
                    const isPositive = fund.changePercent >= 0;
                    return (
                      <tr 
                        key={fund.symbol}
                        className="hover:bg-accent/20 even:bg-accent/5 odd:bg-transparent transition-colors font-medium"
                      >
                        <td 
                          onClick={() => handleSymbolClick(fund.symbol, fund.name, { marketCap: fund.aum, price: fund.nav, changePercent: fund.changePercent })}
                          className="py-1 px-2 border border-border/30 font-bold font-mono text-primary hover:underline whitespace-nowrap cursor-pointer"
                        >
                          {fund.symbol}
                        </td>
                        <td className="py-3 px-4 text-foreground/80 truncate max-w-[130px] whitespace-nowrap">{fund.name}</td>
                        <td className="py-3 px-4 text-foreground/75 hidden sm:table-cell whitespace-nowrap">{fund.category}</td>
                        <td className="py-3 px-4 text-right font-mono font-semibold text-foreground whitespace-nowrap">${fund.nav.toFixed(2)}</td>
                        <td className={cn(
                          "py-1 px-2 border border-border/30 text-right font-mono font-bold whitespace-nowrap",
                          isPositive ? 'text-emerald-400' : 'text-rose-400'
                        )}>
                          {isPositive ? '+' : ''}{fund.changePercent.toFixed(2)}%
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-emerald-400 font-semibold hidden md:table-cell whitespace-nowrap">{fund.ytdReturn.toFixed(2)}%</td>
                        <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden lg:table-cell whitespace-nowrap">{fund.expenseRatio}%</td>
                        <td className="py-3 px-4 hidden md:table-cell whitespace-nowrap">
                          <div className="flex items-center justify-center gap-0.5 text-amber-400">
                            {Array.from({ length: 5 }).map((_, idx) => (
                              <Star 
                                key={idx} 
                                size={11} 
                                fill={idx < fund.rating ? 'currentColor' : 'none'}
                                className={idx < fund.rating ? 'text-amber-400' : 'text-muted-foreground/30'}
                              />
                            ))}
                          </div>
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden lg:table-cell whitespace-nowrap">{fund.aum}</td>
                        <td className="py-3 px-4 text-center whitespace-nowrap">
                          <Button
                            size="sm"
                            onClick={() => handleAction(fund.symbol)}
                            className="inline-flex items-center gap-1 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 hover:border-primary/40 px-2 rounded-lg py-0.5 h-auto text-[9px] font-semibold transition-all hover:scale-105 cursor-pointer"
                          >
                            <Sparkles size={10} className="mr-1 inline" /> Analyze
                          </Button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}

        {screenerTab === 'dividend_stocks' && (
          <div className="w-full overflow-x-auto custom-scrollbar bg-[#0f0f0f]/40 dark:bg-[#0f0f0f]/40 bg-white/50 backdrop-blur-xl border border-white/10 dark:border-white/5 rounded-2xl shadow-md">
            <table className="w-full text-left border-collapse text-[11px]">
              <thead>
                <tr className="border-b border-white/5 text-muted-foreground/80 text-[10px] uppercase tracking-wider font-mono font-semibold bg-white/[0.01]">
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground font-mono transition-colors whitespace-nowrap" onClick={() => toggleDividendSort('symbol')}>
                    Symbol {dividendSortField === 'symbol' && (dividendSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleDividendSort('name')}>
                    Company Name {dividendSortField === 'name' && (dividendSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden sm:table-cell whitespace-nowrap" onClick={() => toggleDividendSort('dividendYield')}>
                    Dividend Yield {dividendSortField === 'dividendYield' && (dividendSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleDividendSort('price')}>
                    Price {dividendSortField === 'price' && (dividendSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleDividendSort('changePercent')}>
                    Change % {dividendSortField === 'changePercent' && (dividendSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 text-right font-mono hidden md:table-cell whitespace-nowrap">Volume</th>
                  <th className="py-3 px-4 text-right font-mono hidden md:table-cell whitespace-nowrap">Market Cap</th>
                  <th className="py-3 px-4 text-right font-mono hidden sm:table-cell whitespace-nowrap">P/E Ratio</th>
                  <th className="py-3 px-4 text-center font-mono hidden lg:table-cell whitespace-nowrap">Safety Rating</th>
                  <th className="py-3 px-4 text-center whitespace-nowrap">AI Analyst</th>
                </tr>
              </thead>
              <tbody>
                {loadingTab ? (
                  <TableSkeleton cols={10} rows={6} />
                ) : filteredDividendStocks.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="p-6 text-center text-muted-foreground font-medium whitespace-nowrap ">
                      No matching Dividend Stocks found.
                    </td>
                  </tr>
                ) : (
                  filteredDividendStocks.map((dividendStock) => {
                    const isPositive = dividendStock.changePercent >= 0;
                    return (
                      <tr 
                        key={dividendStock.symbol}
                        className="hover:bg-accent/20 even:bg-accent/5 odd:bg-transparent transition-colors font-medium"
                      >
                        <td 
                          onClick={() => handleSymbolClick(dividendStock.symbol, dividendStock.name, { peRatio: dividendStock.peRatio, marketCap: dividendStock.marketCap, dividendYield: dividendStock.dividendYield, price: dividendStock.price, changePercent: dividendStock.changePercent, volume: dividendStock.volume })}
                          className="py-1 px-2 border border-border/30 font-bold font-mono text-primary hover:underline whitespace-nowrap cursor-pointer"
                        >
                          {dividendStock.symbol}
                        </td>
                        <td className="py-3 px-4 text-foreground/80 truncate max-w-[130px] whitespace-nowrap">{dividendStock.name}</td>
                        <td className="py-3 px-4 text-emerald-400 font-bold font-mono hidden sm:table-cell whitespace-nowrap">{dividendStock.dividendYield}</td>
                        <td className="py-3 px-4 text-right font-mono font-semibold text-foreground whitespace-nowrap">${dividendStock.price.toFixed(2)}</td>
                        <td className={cn(
                          "py-1 px-2 border border-border/30 text-right font-mono font-bold whitespace-nowrap",
                          isPositive ? 'text-emerald-400' : 'text-rose-400'
                        )}>
                          {isPositive ? '+' : ''}{dividendStock.changePercent.toFixed(2)}%
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden md:table-cell whitespace-nowrap">{dividendStock.volume}</td>
                        <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden md:table-cell whitespace-nowrap">{dividendStock.marketCap}</td>
                        <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden sm:table-cell whitespace-nowrap">{dividendStock.peRatio}</td>
                        <td className="py-3 px-4 text-center whitespace-nowrap hidden lg:table-cell text-emerald-400 font-bold font-mono">
                          {dividendStock.safetyRating}
                        </td>
                        <td className="py-3 px-4 text-center whitespace-nowrap">
                          <Button
                            size="sm"
                            onClick={() => handleAction(dividendStock.symbol)}
                            className="inline-flex items-center gap-1 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 hover:border-primary/40 px-2 rounded-lg py-0.5 h-auto text-[9px] font-semibold transition-all hover:scale-105 cursor-pointer"
                          >
                            <Sparkles size={10} className="mr-1 inline" /> Analyze
                          </Button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>

      </div>
      
      {/* TradingView Detail Chart Analysis Screen Page Overlay */}
      {selectedAnalysisStock && (
        <TradingViewChart
          symbol={selectedAnalysisStock.symbol}
          stockName={selectedAnalysisStock.name}
          peRatio={selectedAnalysisStock.peRatio}
          marketCap={selectedAnalysisStock.marketCap}
          dividendYield={selectedAnalysisStock.dividendYield}
          shortFloat={selectedAnalysisStock.shortFloat}
          price={selectedAnalysisStock.price}
          changePercent={selectedAnalysisStock.changePercent}
          volume={selectedAnalysisStock.volume}
          sector={selectedAnalysisStock.sector}
          industry={selectedAnalysisStock.industry}
          country={selectedAnalysisStock.country}
          circulatingSupply={selectedAnalysisStock.circulatingSupply}
          totalSupply={selectedAnalysisStock.totalSupply}
          maxSupply={selectedAnalysisStock.maxSupply}
          ath={selectedAnalysisStock.ath}
          atl={selectedAnalysisStock.atl}
          rank={selectedAnalysisStock.rank}
          athChangePercent={selectedAnalysisStock.athChangePercent}
          atlChangePercent={selectedAnalysisStock.atlChangePercent}
          athDate={selectedAnalysisStock.athDate}
          atlDate={selectedAnalysisStock.atlDate}
          marketCapRaw={selectedAnalysisStock.marketCapRaw}
          volumeRaw={selectedAnalysisStock.volumeRaw}
          circulatingSupplyRaw={selectedAnalysisStock.circulatingSupplyRaw}
          maxSupplyRaw={selectedAnalysisStock.maxSupplyRaw}
          onClose={() => setSelectedAnalysisStock(null)}
        />
      )}
    </div>
    </>
  );
}
