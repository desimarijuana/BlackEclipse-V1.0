'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { 
  ArrowUpRight, ArrowDownRight, ArrowRight, Search, 
  Sparkles, Star, BarChart3, 
  Layers, Award, TrendingUp, TrendingDown, Sliders, X, Coins, ChevronDown, Download,
  Info
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { TradingViewChart } from './tradingview-chart';
import { cn, getTradingViewSymbol } from '@/lib/utils';
import { TopLoader } from '@/components/ui/top-loader';
import { Skeleton, SkeletonHeader, SkeletonIndexCard, SkeletonPanel, SkeletonTable } from '@/components/ui/skeleton';
import {
  IndexCard, SectorPerformance, ShifterItem, StockItem, FundItem, ETFItem, NewStockItem, BlueChipItem,
  INDEX_DATA, SECTOR_PERFORMANCE, TOP_GAINERS, TOP_LOSERS,
  getSimulatedDashboard,
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

  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);
  // Removed selectedStock state
  const [selectedAnalysisStock, setSelectedAnalysisStock] = useState<StockItem | null>(null);
  const [filterMetricType, setFilterMetricType] = useState('All');
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);
  const userCountry: string = 'USA'; // Unified default region for stocks
  const [apiStocks, setApiStocks] = useState<StockItem[]>([]);
  const [loadingApi, setLoadingApi] = useState(true);

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

  // Active view tab inside dashboard ('stocks' | 'etfs' | 'new_stocks' | 'blue_chips' | 'funds' | 'dividend_stocks' | 'crypto')
  const [screenerTab, setScreenerTab] = useState<'stocks' | 'etfs' | 'new_stocks' | 'blue_chips' | 'funds' | 'dividend_stocks' | 'crypto'>('crypto');
  const [loadingTab, setLoadingTab] = useState(false);

  const handleTabChange = (tab: 'stocks' | 'etfs' | 'new_stocks' | 'blue_chips' | 'funds' | 'dividend_stocks' | 'crypto') => {
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
    setExpandedSymbol(null);
    setStockSearch('');
    setTimeout(() => {
      setLoadingTab(false);
    }, 450);
  };

  const [currentPage, setCurrentPage] = useState(1);
  const [totalStocks, setTotalStocks] = useState(0);
  const [limit, setLimit] = useState(30);

  // Reset page on country, limit, search, sector, or tab changes
  React.useEffect(() => {
    setCurrentPage(1);
  }, [userCountry, limit, stockSearch, filterSector, screenerTab]);

  const [loadingDashboard, setLoadingDashboard] = useState(false);

  const [dataUpdatedTime, setDataUpdatedTime] = useState<string | null>(null);
  const [dataSource, setDataSource] = useState<string>('live');

  // Load demo stocks and dashboard metadata based on user's country/tab
  React.useEffect(() => {
    const queryCountry = screenerTab === 'crypto' ? 'CRYPTO' : userCountry;
    const demoStocks = getFallbackStocks(queryCountry);
    const dash = getSimulatedDashboard(queryCountry);

    setApiStocks(demoStocks);
    setTotalStocks(demoStocks.length);
    setDataSource('demo');
    setDataUpdatedTime(new Date().toISOString());
    setIndexData(dash.indices);
    setSectorPerformance(dash.sectors);
    setTopGainers(dash.shifters.gainers);
    setTopLosers(dash.shifters.losers);
    setLoadingApi(false);
    setLoadingDashboard(false);
  }, [userCountry, screenerTab]);



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

  // ETF state
  const [etfSearch, setEtfSearch] = useState('');
  const [etfCategory, setEtfCategory] = useState('All');
  const [etfSortField, setEtfSortField] = useState<keyof ETFItem>('symbol');
  const [etfSortOrder, setEtfSortOrder] = useState<'asc' | 'desc'>('asc');

  // New stock state
  const [newStockSearch, setNewStockSearch] = useState('');
  const [newStockSortField, setNewStockSortField] = useState<keyof NewStockItem>('symbol');
  const [newStockSortOrder, setNewStockSortOrder] = useState<'asc' | 'desc'>('asc');

  // Blue chip state
  const [blueChipSearch, setBlueChipSearch] = useState('');
  const [blueChipRating, setBlueChipRating] = useState('All');
  const [blueChipSortField, setBlueChipSortField] = useState<keyof BlueChipItem>('symbol');
  const [blueChipSortOrder, setBlueChipSortOrder] = useState<'asc' | 'desc'>('asc');

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
    } else if (screenerTab === 'new_stocks') {
      headers = ['Symbol', 'Company', 'IPO Date', 'Price', 'Change %', 'Market Cap', 'Offer Price'];
      rows = filteredNewStocks.map(n => [
        n.symbol, n.name, n.ipoDate, `$${n.price.toFixed(2)}`, `${n.changePercent >= 0 ? '+' : ''}${n.changePercent.toFixed(2)}%`, n.marketCap, `$${n.ipoPrice.toFixed(2)}`
      ]);
    } else if (screenerTab === 'blue_chips') {
      headers = ['Symbol', 'Company', 'Div Yield', 'Price', 'Change %', 'Market Cap', 'P/E', 'Safety'];
      rows = filteredBlueChips.map(b => [
        b.symbol, b.name, b.dividendYield, `$${b.price.toFixed(2)}`, `${b.changePercent >= 0 ? '+' : ''}${b.changePercent.toFixed(2)}%`, b.marketCap, b.peRatio, b.safetyRating
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
    filteredNewStocks,
    filteredBlueChips,
    filteredDividendStocks,
  } = useScreenerFilters({
    apiStocks, stockSearch, filterExchange, filterIndex, filterSector, filterIndustry,
    filterCountry, filterMarketCap, filterPE, filterDividendYield, filterPrice,
    filterChange, filterVolume, filterRecommendation, filterMetricType,
    screenerTab, userCountry, stockSortField, stockSortOrder,
    fundSearch, fundCategory, fundSortField, fundSortOrder,
    etfSearch, etfCategory, etfSortField, etfSortOrder,
    newStockSearch, newStockSortField, newStockSortOrder,
    blueChipSearch, blueChipRating, blueChipSortField, blueChipSortOrder,
    dividendSearch, dividendSortField, dividendSortOrder,
  });

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

  const toggleNewStockSort = (field: keyof NewStockItem) => {
    if (newStockSortField === field) {
      setNewStockSortOrder(prev => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setNewStockSortField(field);
      setNewStockSortOrder('asc');
    }
  };

  const toggleBlueChipSort = (field: keyof BlueChipItem) => {
    if (blueChipSortField === field) {
      setBlueChipSortOrder(prev => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setBlueChipSortField(field);
      setBlueChipSortOrder('asc');
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
          
          <div className="flex items-center gap-2 bg-accent/40 p-1.5 rounded-2xl border border-border/40 backdrop-blur-md shrink-0 self-start md:self-auto">
            <span className="text-[10px] uppercase font-bold text-muted-foreground/80 px-2 tracking-wider">Market:</span>
            <select
              value={screenerTab === 'crypto' ? 'crypto' : 'stocks'}
              onChange={e => handleTabChange(e.target.value as 'crypto' | 'stocks')}
              className="bg-background border border-border/60 hover:border-primary/50 rounded-xl px-3 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary outline-none transition-all cursor-pointer font-semibold"
            >
              <option value="crypto">Global (24/7) — Crypto</option>
              <option value="stocks">United States (USA) — Stocks</option>
            </select>
          </div>
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
        <div className="flex items-center justify-between border-b border-border/15 pb-5 mb-2 flex-wrap gap-4">
          <div className="flex items-center gap-1.5 bg-accent/30 p-1.5 rounded-2xl overflow-x-auto max-w-full scrollbar-none flex-nowrap shrink-0 w-full md:w-auto">
            {screenerTab !== 'crypto' ? (
              <>
                <button
                  onClick={() => handleTabChange('stocks')}
                  className={`px-4 py-2 rounded-xl text-xs font-bold tracking-tight transition-all duration-200 cursor-pointer flex items-center gap-1.5 shrink-0 ${
                    screenerTab === 'stocks' 
                      ? 'bg-primary text-primary-foreground shadow-lg shadow-primary/15' 
                      : 'text-muted-foreground hover:text-foreground hover:bg-accent/40'
                  }`}
                >
                  <TrendingUp className="w-3.5 h-3.5" /> Trending Stocks
                </button>
                <button
                  onClick={() => handleTabChange('new_stocks')}
                  className={`px-4 py-2 rounded-xl text-xs font-bold tracking-tight transition-all duration-200 cursor-pointer flex items-center gap-1.5 shrink-0 ${
                    screenerTab === 'new_stocks' 
                      ? 'bg-primary text-primary-foreground shadow-lg shadow-primary/15' 
                      : 'text-muted-foreground hover:text-foreground hover:bg-accent/40'
                  }`}
                >
                  <Sparkles className="w-3.5 h-3.5" /> New Listings
                </button>
                <button
                  onClick={() => handleTabChange('blue_chips')}
                  className={`px-4 py-2 rounded-xl text-xs font-bold tracking-tight transition-all duration-200 cursor-pointer flex items-center gap-1.5 shrink-0 ${
                    screenerTab === 'blue_chips' 
                      ? 'bg-primary text-primary-foreground shadow-lg shadow-primary/15' 
                      : 'text-muted-foreground hover:text-foreground hover:bg-accent/40'
                  }`}
                >
                  <Award className="w-3.5 h-3.5" /> Blue Chips
                </button>
              </>
            ) : (
              <button
                onClick={() => handleTabChange('crypto')}
                className={`px-4 py-2 rounded-xl text-xs font-bold tracking-tight transition-all duration-200 cursor-pointer flex items-center gap-1.5 shrink-0 ${
                  screenerTab === 'crypto' 
                    ? 'bg-primary text-primary-foreground shadow-lg shadow-primary/15' 
                    : 'text-muted-foreground hover:text-foreground hover:bg-accent/40'
                }`}
              >
                <Coins className="w-3.5 h-3.5" /> Cryptocurrency
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            {loadingApi && <span className="text-[10px] text-muted-foreground/80 animate-pulse bg-accent/20 px-2.5 py-1 rounded-xl font-mono">Syncing Exchange...</span>}
            <button
              onClick={exportToPDF}
              className="px-4 py-2 rounded-xl text-xs font-bold tracking-tight transition-all duration-200 cursor-pointer flex items-center gap-1.5 border border-border bg-background/50 hover:bg-accent/40 text-muted-foreground hover:text-foreground h-9"
            >
              <Download className="w-3.5 h-3.5 text-inherit" /> Download PDF
            </button>
          </div>
        </div>

        {/* Dedicated SPACIOUS Filter Action Bar - Solves Congestion */}
        <div className="flex items-center justify-between bg-accent/10 border border-border/20 rounded-2xl p-4 md:p-5 flex-wrap gap-4">
          {screenerTab === 'stocks' && (
            <div className="flex flex-col-reverse sm:flex-row sm:items-center justify-between w-full gap-4">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setShowAdvancedFilters(!showAdvancedFilters)}
                  className={`px-5 py-2.5 rounded-xl text-xs font-bold tracking-tight transition-all duration-200 cursor-pointer flex items-center gap-2 border h-10 shrink-0 ${
                    showAdvancedFilters
                      ? 'bg-primary text-primary-foreground border-primary shadow-md shadow-primary/25 scale-[1.02]'
                      : 'text-muted-foreground border-border bg-background/50 hover:border-primary/50 hover:text-foreground hover:bg-accent/40'
                  }`}
                >
                  <Sliders className="w-4 h-4 text-inherit" /> Advanced Filters
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
                {/* Industry Selector */}
                <div className="relative min-w-[160px]">
                  <select
                    value={filterIndustry}
                    onChange={e => setFilterIndustry(e.target.value)}
                    className="w-full appearance-none bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-3.5 pr-9 py-2.5 text-xs font-semibold text-foreground focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer transition-all"
                  >
                    <option value="All">All Industries</option>
                    <option value="Consumer Electronics">Consumer Electronics</option>
                    <option value="Semiconductors">Semiconductors</option>
                    <option value="Software - Infrastructure">Software</option>
                    <option value="Internet Retail">Internet Retail</option>
                    <option value="IT Services">IT Services</option>
                    <option value="Banks - Diversified">Banks</option>
                    <option value="Cement">Cement</option>
                    <option value="Fertilizers">Fertilizers</option>
                    <option value="Oil & Gas">Oil & Gas</option>
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
                  className={`px-4 py-2.5 rounded-xl text-xs font-bold tracking-tight transition-all duration-200 cursor-pointer flex items-center gap-2 border h-10 shrink-0 ${
                    showAdvancedFilters
                      ? 'bg-primary text-primary-foreground border-primary shadow-md shadow-primary/25'
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
            <div className="flex flex-col sm:flex-row sm:items-center justify-between w-full gap-4">
              <span className="text-xs font-bold text-foreground font-serif">ETF Directory</span>
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
                    <option value="Large Blend">Large Blend</option>
                    <option value="Large Growth">Large Growth</option>
                    <option value="Small Blend">Small Blend</option>
                    <option value="Large Value">Large Value</option>
                    <option value="Mid-Cap Growth">Mid-Cap Growth</option>
                  </select>
                  <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground w-3.5 h-3.5 pointer-events-none" />
                </div>
              </div>
            </div>
          )}

          {screenerTab === 'new_stocks' && (
            <div className="flex flex-col sm:flex-row sm:items-center justify-between w-full gap-4">
              <span className="text-xs font-bold text-foreground font-serif">New Stock Listings</span>
              <div className="relative w-64 min-w-[200px]">
                <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground w-4 h-4" />
                <input
                  type="text"
                  placeholder="Search New Listings..."
                  value={newStockSearch}
                  onChange={e => setNewStockSearch(e.target.value)}
                  className="w-full bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-10 pr-4 py-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary placeholder:text-muted-foreground/50 transition-all font-mono"
                />
              </div>
            </div>
          )}

          {screenerTab === 'blue_chips' && (
            <div className="flex flex-col sm:flex-row sm:items-center justify-between w-full gap-4">
              <span className="text-xs font-bold text-foreground font-serif">Blue Chip Investments</span>
              <div className="flex items-center gap-4 flex-wrap flex-1 max-w-2xl justify-end">
                <div className="relative w-64 min-w-[200px]">
                  <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground w-4 h-4" />
                  <input
                    type="text"
                    placeholder="Search Blue Chips..."
                    value={blueChipSearch}
                    onChange={e => setBlueChipSearch(e.target.value)}
                    className="w-full bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-10 pr-4 py-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary placeholder:text-muted-foreground/50 transition-all font-mono"
                  />
                </div>
                <div className="relative min-w-[180px]">
                  <select
                    value={blueChipRating}
                    onChange={e => setBlueChipRating(e.target.value)}
                    className="w-full appearance-none bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-3.5 pr-9 py-2.5 text-xs font-semibold text-foreground focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer transition-all"
                  >
                    <option value="All">All Safety Ratings</option>
                    <option value="AAA">AAA Rating</option>
                    <option value="AA+">AA+ Rating</option>
                  </select>
                  <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground w-3.5 h-3.5 pointer-events-none" />
                </div>
              </div>
            </div>
          )}

          {screenerTab === 'funds' && (
            <div className="flex flex-col sm:flex-row sm:items-center justify-between w-full gap-4">
              <span className="text-xs font-bold text-foreground font-serif">Mutual Funds</span>
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
                    <option value="Large Growth">Large Growth</option>
                    <option value="Large Blend">Large Blend</option>
                    <option value="Foreign Large Blend">Intl Blend</option>
                    <option value="Intermediate Core Bond">Core Bond</option>
                  </select>
                  <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground w-3.5 h-3.5 pointer-events-none" />
                </div>
              </div>
            </div>
          )}

          {screenerTab === 'dividend_stocks' && (
            <div className="flex flex-col sm:flex-row sm:items-center justify-between w-full gap-4">
              <span className="text-xs font-bold text-foreground font-serif">High Dividend Yield Stocks</span>
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
        </div>

        {/* Advanced Filters Panel - Clean, organized layout */}
        {screenerTab === 'stocks' && showAdvancedFilters && (
          <div className="w-full bg-card/35 border border-border/30 rounded-2xl p-4 md:p-5 backdrop-blur-2xl animate-fade-in text-xs shadow-lg">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-border/20">
              <div className="flex items-center gap-2">
                <Sliders className="w-4 h-4 text-primary" />
                <span className="font-semibold text-sm text-foreground">Advanced Filters</span>
                <span className="text-[10px] text-muted-foreground/70 font-mono">(applied to current page)</span>
              </div>
              <button 
                onClick={() => {
                  setFilterExchange('All'); setFilterIndex('All'); setFilterSector('All');
                  setFilterIndustry('All'); setFilterCountry('All'); setFilterMarketCap('All');
                  setFilterPE('All'); setFilterDividendYield('All'); setFilterPrice('All');
                  setFilterChange('All'); setFilterVolume('All'); setFilterRecommendation('All');
                }}
                className="text-[10px] text-muted-foreground hover:text-rose-400 font-mono font-bold uppercase tracking-wider transition-colors cursor-pointer flex items-center gap-1"
              >
                <X className="w-3 h-3" /> Reset All
              </button>
            </div>
            
            {/* 3-column grid for filters */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              {/* Sector */}
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-primary/80 tracking-widest font-mono">Sector</span>
                <div className="relative">
                  <select value={filterSector} onChange={e => setFilterSector(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-primary/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
                    <option value="All">Any Sector</option>
                    <option value="Technology">Technology</option>
                    <option value="Healthcare">Healthcare</option>
                    <option value="Financials">Financials</option>
                    <option value="Consumer Discretionary">Consumer Disc.</option>
                    <option value="Energy">Energy</option>
                    <option value="Industrials">Industrials</option>
                    <option value="Materials">Materials</option>
                    <option value="Utilities">Utilities</option>
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                </div>
              </div>

              {/* Market Cap */}
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-emerald-400/80 tracking-widest font-mono">Market Cap</span>
                <div className="relative">
                  <select value={filterMarketCap} onChange={e => setFilterMarketCap(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-emerald-500/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
                    <option value="All">Any Cap</option>
                    <option value="Mega">Mega ($100B+)</option>
                    <option value="Large">Large ($10B–$100B)</option>
                    <option value="Mid">Mid ($2B–$10B)</option>
                    <option value="Small">Small (&lt;$2B)</option>
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                </div>
              </div>

              {/* Volume */}
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-emerald-400/80 tracking-widest font-mono">Volume</span>
                <div className="relative">
                  <select value={filterVolume} onChange={e => setFilterVolume(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-emerald-500/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
                    <option value="All">Any Volume</option>
                    <option value="Under1">Under 1M</option>
                    <option value="1to10">1M – 10M</option>
                    <option value="Over10">Over 10M</option>
                    <option value="Over30">Over 30M</option>
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                </div>
              </div>

              {/* P/E Ratio */}
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-sky-400/80 tracking-widest font-mono">P/E Ratio</span>
                <div className="relative">
                  <select value={filterPE} onChange={e => setFilterPE(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-sky-500/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
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

              {/* Dividend Yield */}
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-sky-400/80 tracking-widest font-mono">Dividend</span>
                <div className="relative">
                  <select value={filterDividendYield} onChange={e => setFilterDividendYield(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-sky-500/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
                    <option value="All">Any Div.</option>
                    <option value="None">No Dividend</option>
                    <option value="Positive">Paying (&gt;0%)</option>
                    <option value="Over2">Over 2%</option>
                    <option value="Over5">Over 5%</option>
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                </div>
              </div>

              {/* 24h Change */}
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-amber-400/80 tracking-widest font-mono">Change %</span>
                <div className="relative">
                  <select value={filterChange} onChange={e => setFilterChange(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-amber-500/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
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
          <div className="w-full bg-card/35 border border-border/30 rounded-2xl p-4 md:p-5 backdrop-blur-2xl animate-fade-in text-xs shadow-lg">
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
                <span className="text-[9px] uppercase font-bold text-emerald-400/80 tracking-widest font-mono">Market Cap</span>
                <div className="relative">
                  <select value={filterMarketCap} onChange={e => setFilterMarketCap(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-emerald-500/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
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
                <span className="text-[9px] uppercase font-bold text-amber-400/80 tracking-widest font-mono">24h Change</span>
                <div className="relative">
                  <select value={filterChange} onChange={e => setFilterChange(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-amber-500/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
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
          filterIndustry !== 'All') && (
          <div className="flex items-center gap-2 flex-wrap p-3 rounded-xl border border-primary/20 bg-primary/5 text-[11px]">
            <span className="text-[10px] font-bold text-primary/70 uppercase tracking-wider font-mono">Active:</span>
            {filterSector !== 'All' && <span className="bg-primary/10 border border-primary/25 text-primary px-2 py-0.5 rounded-lg font-mono font-bold">{filterSector}</span>}
            {filterMarketCap !== 'All' && <span className="bg-primary/10 border border-primary/25 text-primary px-2 py-0.5 rounded-lg font-mono font-bold">Cap: {filterMarketCap}</span>}
            {filterPE !== 'All' && <span className="bg-primary/10 border border-primary/25 text-primary px-2 py-0.5 rounded-lg font-mono font-bold">P/E: {filterPE}</span>}
            {filterDividendYield !== 'All' && <span className="bg-primary/10 border border-primary/25 text-primary px-2 py-0.5 rounded-lg font-mono font-bold">Div: {filterDividendYield}</span>}
            {filterChange !== 'All' && <span className="bg-primary/10 border border-primary/25 text-primary px-2 py-0.5 rounded-lg font-mono font-bold">Δ: {filterChange}</span>}
            {filterVolume !== 'All' && <span className="bg-primary/10 border border-primary/25 text-primary px-2 py-0.5 rounded-lg font-mono font-bold">Vol: {filterVolume}</span>}
            {filterIndustry !== 'All' && <span className="bg-primary/10 border border-primary/25 text-primary px-2 py-0.5 rounded-lg font-mono font-bold">Industry: {filterIndustry}</span>}
            <button
              onClick={() => {
                setFilterSector('All'); setFilterMarketCap('All'); setFilterPE('All');
                setFilterDividendYield('All'); setFilterChange('All'); setFilterVolume('All');
                setFilterIndustry('All'); setFilterExchange('All'); setFilterIndex('All');
                setFilterCountry('All'); setFilterPrice('All'); setFilterRecommendation('All');
              }}
              className="ml-auto text-[10px] text-rose-400 hover:text-rose-300 font-mono font-bold uppercase tracking-wider transition-colors cursor-pointer flex items-center gap-1"
            >
              <X className="w-3 h-3" /> Clear
            </button>
          </div>
        )}



        {/* Screening Table Renderings - Zero Horizontal Scrolling due to responsive cols */}
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
                    <TableSkeleton cols={9} rows={8} />
                  ) : filteredStocks.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="p-6 text-center text-muted-foreground font-medium whitespace-nowrap ">
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
                          <td className="py-3 px-4 text-foreground/85 truncate max-w-[130px] whitespace-nowrap">{stock.name}</td>
                          <td className="py-3 px-4 text-foreground/75 hidden lg:table-cell whitespace-nowrap">{stock.industry}</td>
                          <td className="py-3 px-4 text-foreground/75 hidden lg:table-cell whitespace-nowrap">{stock.country}</td>
                          <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden sm:table-cell whitespace-nowrap">{stock.marketCap}</td>
                          <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden sm:table-cell whitespace-nowrap">{stock.peRatio}</td>
                          <td className="py-3 px-4 text-right font-mono font-bold text-foreground whitespace-nowrap">${stock.price.toFixed(2)}</td>
                          <td className={cn(
                            "py-1 px-2 border border-border/30 text-right font-mono font-bold whitespace-nowrap",
                            isPositive ? 'text-emerald-400' : 'text-rose-400'
                          )}>
                            {isPositive ? '+' : ''}{stock.changePercent.toFixed(2)}%
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
                    <option value={30} className="bg-card text-foreground">30</option>
                    <option value={60} className="bg-card text-foreground">60</option>
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
                                ${formatCryptoPrice(stock.price)}
                              </td>
                              <td className={cn(
                                "py-2 px-2 border border-border/30 text-right font-mono font-bold whitespace-nowrap",
                                isPositive ? 'text-emerald-400' : 'text-rose-400'
                              )}>
                                {isPositive ? '+' : ''}{stock.changePercent.toFixed(2)}%
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
                    <option value={30} className="bg-card text-foreground">30</option>
                    <option value={60} className="bg-card text-foreground">60</option>
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

        {screenerTab === 'new_stocks' && (
          <div className="w-full overflow-x-auto custom-scrollbar bg-[#0f0f0f]/40 dark:bg-[#0f0f0f]/40 bg-white/50 backdrop-blur-xl border border-white/10 dark:border-white/5 rounded-2xl shadow-md">
            <table className="w-full text-left border-collapse text-[11px]">
              <thead>
                <tr className="border-b border-white/5 text-muted-foreground/80 text-[10px] uppercase tracking-wider font-mono font-semibold bg-white/[0.01]">
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground font-mono transition-colors whitespace-nowrap" onClick={() => toggleNewStockSort('symbol')}>
                    Symbol {newStockSortField === 'symbol' && (newStockSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleNewStockSort('name')}>
                    Company Name {newStockSortField === 'name' && (newStockSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden sm:table-cell whitespace-nowrap" onClick={() => toggleNewStockSort('ipoDate')}>
                    IPO Date {newStockSortField === 'ipoDate' && (newStockSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleNewStockSort('price')}>
                    Price {newStockSortField === 'price' && (newStockSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleNewStockSort('changePercent')}>
                    Change % {newStockSortField === 'changePercent' && (newStockSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 text-right font-mono hidden md:table-cell whitespace-nowrap">Market Cap</th>
                  <th className="py-3 px-4 text-right font-mono hidden lg:table-cell whitespace-nowrap">IPO Offer Price</th>
                  <th className="py-3 px-4 text-center whitespace-nowrap">AI Analyst</th>
                </tr>
              </thead>
              <tbody>
                {loadingTab ? (
                  <TableSkeleton cols={8} rows={6} />
                ) : filteredNewStocks.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="p-6 text-center text-muted-foreground font-medium whitespace-nowrap ">
                      No matching IPOs found.
                    </td>
                  </tr>
                ) : (
                  filteredNewStocks.map((newStock) => {
                    const isPositive = newStock.changePercent >= 0;
                    return (
                      <tr 
                        key={newStock.symbol}
                        className="hover:bg-accent/20 even:bg-accent/5 odd:bg-transparent transition-colors font-medium"
                      >
                        <td 
                          onClick={() => handleSymbolClick(newStock.symbol, newStock.name, { marketCap: newStock.marketCap, price: newStock.price, changePercent: newStock.changePercent, volume: newStock.volume })}
                          className="py-1 px-2 border border-border/30 font-bold font-mono text-primary hover:underline whitespace-nowrap cursor-pointer"
                        >
                          {newStock.symbol}
                        </td>
                        <td className="py-3 px-4 text-foreground/80 truncate max-w-[130px] whitespace-nowrap">{newStock.name}</td>
                        <td className="py-3 px-4 text-foreground/75 hidden sm:table-cell whitespace-nowrap">{newStock.ipoDate}</td>
                        <td className="py-3 px-4 text-right font-mono font-bold text-foreground whitespace-nowrap">${newStock.price.toFixed(2)}</td>
                        <td className={cn(
                          "py-1 px-2 border border-border/30 text-right font-mono font-bold whitespace-nowrap",
                          isPositive ? 'text-emerald-400' : 'text-rose-400'
                        )}>
                          {isPositive ? '+' : ''}{newStock.changePercent.toFixed(2)}%
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden md:table-cell whitespace-nowrap">{newStock.marketCap}</td>
                        <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden lg:table-cell whitespace-nowrap">${newStock.ipoPrice.toFixed(2)}</td>
                        <td className="py-3 px-4 text-center whitespace-nowrap">
                          <Button
                            size="sm"
                            onClick={() => handleAction(newStock.symbol)}
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

        {screenerTab === 'blue_chips' && (
          <div className="w-full overflow-x-auto custom-scrollbar bg-[#0f0f0f]/40 dark:bg-[#0f0f0f]/40 bg-white/50 backdrop-blur-xl border border-white/10 dark:border-white/5 rounded-2xl shadow-md">
            <table className="w-full text-left border-collapse text-[11px]">
              <thead>
                <tr className="border-b border-white/5 text-muted-foreground/80 text-[10px] uppercase tracking-wider font-mono font-semibold bg-white/[0.01]">
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground font-mono transition-colors whitespace-nowrap" onClick={() => toggleBlueChipSort('symbol')}>
                    Symbol {blueChipSortField === 'symbol' && (blueChipSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleBlueChipSort('name')}>
                    Company Name {blueChipSortField === 'name' && (blueChipSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden sm:table-cell whitespace-nowrap" onClick={() => toggleBlueChipSort('dividendYield')}>
                    Dividend Yield {blueChipSortField === 'dividendYield' && (blueChipSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleBlueChipSort('price')}>
                    Price {blueChipSortField === 'price' && (blueChipSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleBlueChipSort('changePercent')}>
                    Change % {blueChipSortField === 'changePercent' && (blueChipSortOrder === 'asc' ? '▲' : '▼')}
                  </th>
                  <th className="py-3 px-4 text-right font-mono hidden md:table-cell whitespace-nowrap">Market Cap</th>
                  <th className="py-3 px-4 text-right font-mono hidden sm:table-cell whitespace-nowrap">P/E Ratio</th>
                  <th className="py-3 px-4 text-center font-mono hidden lg:table-cell whitespace-nowrap">Safety Rating</th>
                  <th className="py-3 px-4 text-center whitespace-nowrap">AI Analyst</th>
                </tr>
              </thead>
              <tbody>
                {loadingTab ? (
                  <TableSkeleton cols={9} rows={6} />
                ) : filteredBlueChips.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="p-6 text-center text-muted-foreground font-medium whitespace-nowrap ">
                      No matching Blue Chips found.
                    </td>
                  </tr>
                ) : (
                  filteredBlueChips.map((blueChip) => {
                    const isPositive = blueChip.changePercent >= 0;
                    return (
                      <tr 
                        key={blueChip.symbol}
                        className="hover:bg-accent/20 even:bg-accent/5 odd:bg-transparent transition-colors font-medium"
                      >
                        <td 
                          onClick={() => handleSymbolClick(blueChip.symbol, blueChip.name, { peRatio: blueChip.peRatio, marketCap: blueChip.marketCap, dividendYield: blueChip.dividendYield, price: blueChip.price, changePercent: blueChip.changePercent, volume: blueChip.volume })}
                          className="py-1 px-2 border border-border/30 font-bold font-mono text-primary hover:underline whitespace-nowrap cursor-pointer"
                        >
                          {blueChip.symbol}
                        </td>
                        <td className="py-3 px-4 text-foreground/80 truncate max-w-[130px] whitespace-nowrap">{blueChip.name}</td>
                        <td className="py-3 px-4 text-foreground/75 font-mono hidden sm:table-cell whitespace-nowrap">{blueChip.dividendYield}</td>
                        <td className="py-3 px-4 text-right font-mono font-semibold text-foreground whitespace-nowrap">${blueChip.price.toFixed(2)}</td>
                        <td className={cn(
                          "py-1 px-2 border border-border/30 text-right font-mono font-bold whitespace-nowrap",
                          isPositive ? 'text-emerald-400' : 'text-rose-400'
                        )}>
                          {isPositive ? '+' : ''}{blueChip.changePercent.toFixed(2)}%
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden md:table-cell whitespace-nowrap">{blueChip.marketCap}</td>
                        <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden sm:table-cell whitespace-nowrap">{blueChip.peRatio}</td>
                        <td className="py-3 px-4 text-center whitespace-nowrap hidden lg:table-cell text-emerald-400 font-bold font-mono">
                          {blueChip.safetyRating}
                        </td>
                        <td className="py-3 px-4 text-center whitespace-nowrap">
                          <Button
                            size="sm"
                            onClick={() => handleAction(blueChip.symbol)}
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
