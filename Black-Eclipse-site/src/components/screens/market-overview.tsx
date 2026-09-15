'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { 
  ArrowUpRight, ArrowDownRight, ArrowRight, ArrowUp, ArrowDown, Search,
  Sparkles, Star, ChartCandlestick,
  Layers, Award, TrendingUp, Sliders, X, Coins, ChevronDown,
  Info, Briefcase, Building2, Globe, RefreshCw, GripVertical, ArrowLeft,
  Eye
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { TabBar } from '@/components/ui/tab-bar';
import { TradingViewChart } from './tradingview-chart';
import { cn } from '@/lib/utils';
import { TopLoader } from '@/components/ui/top-loader';
import { useCommandStore } from '@/lib/search/store';
import {
  IndexCard, SectorPerformance, ShifterItem, StockItem, FundItem, ETFItem, BlueChipItem,
  INDEX_DATA, SECTOR_PERFORMANCE, TOP_GAINERS, TOP_LOSERS,
} from './market-data';
import { useScreenerFilters } from './use-screener-filters';
import { currencyCodeFor as currencyFor, formatPriceWithCurrency } from '@/lib/market-currency';
import { marketSentimentFromIndices } from '@/lib/aurora-sentiment';

// Currency helpers come from @/lib/market-currency (shared with the API
// routes and the chart panel) � dollar assets keep "$", everything else
// shows its native ISO code ("PKR 327.43", "CNY 12.40", ...).
const priceWithCurrency = (country: string, value: number) => formatPriceWithCurrency(country, value);

// Commodities & forex are ALWAYS shown in US dollars ("$"), per spec.
// Yahoo returns some contracts in US cents (USc/bu, USc/lb) � convert those
// to whole dollars so every price reads as USD. FX pairs are already quoted
// in the pair's units (EURUSD = dollars per euro) so they pass through.
const COMMODITY_USD_SCALE: Record<string, number> = {
  'ZW=F': 0.01, 'ZC=F': 0.01, 'ZS=F': 0.01, 'KC=F': 0.01,
  'SB=F': 0.01, 'CT=F': 0.01, 'LE=F': 0.01,
};
const formatUsdPrice = (symbol: string, value: number | null | undefined) => {
  if (value == null || !Number.isFinite(value)) return '-';
  const scaled = value * (COMMODITY_USD_SCALE[symbol] ?? 1);
  return `$ ${scaled.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: Math.abs(scaled) >= 1 ? 2 : 6,
  })}`;
};

// Human-readable market cap ("2.97T", "412.5B", "18.3M").
const fmtCap = (n?: number | null) => {
  if (!n || n <= 0) return '-';
  if (n >= 1e12) return `${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  return n.toLocaleString();
};

// ── ASCII dot-grid progress loader ─────────────────────────────────────────
// Per-section data loads use a quiet text line instead, so the page
// never floods with multiple dot grids.
function TableLoading({ pct, label }: { pct: number; label: string }) {
  const [currentPct, setCurrentPct] = useState(pct);

  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (currentPct < 95) {
      timer = setInterval(() => {
        setCurrentPct(prev => Math.min(95, prev + Math.max(0.5, (95 - prev) * 0.05)));
      }, 300);
    } else if (pct === 100) {
      setCurrentPct(100);
    }
    return () => clearInterval(timer);
  }, [pct]);

  return (
    <div className="flex items-center gap-2 font-mono text-[10px] text-muted-foreground/70">
      <span className="w-4 h-4 rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground/70 animate-spin" aria-hidden />
      <span className="font-bold">{Math.floor(currentPct)}%</span>
      {label && <span className="truncate">· {label}</span>}
    </div>
  );
}

function TableSkeleton({ cols = 11, rows = 6 }: { cols?: number; rows?: number }) {
  return (
    <tr>
      <td colSpan={cols} className="p-6">
        <div className="flex items-center justify-center">
          <TableLoading pct={Math.min(95, 30 + rows * 8)} label="loading table" />
        </div>
      </td>
    </tr>
  );
}

interface MarketOverviewScreenProps {
  onAnalyzeTicker: (ticker: string, customContextPrompt?: string) => void;
  onSelectChartSymbol?: (symbol: string) => void;
  embedded?: boolean;
  onMarketStatusChange?: (isBullish: boolean) => void;
  /** Optional initial market/country code to load (e.g. 'PK', 'US', 'IN'). */
  market?: string;
  /** Optional initial ticker to pre-fill the screener search (global search pivot). */
  initialSymbol?: string;
}

export function MarketOverviewScreen({ onAnalyzeTicker, onSelectChartSymbol, embedded = false, onMarketStatusChange, market, initialSymbol }: MarketOverviewScreenProps) {

  // Ctrl/Cmd+click on any symbol row opens that symbol in a NEW browser tab
  // (deep link: /?symbol=XYZ boots the app straight into its chart), instead
  // of the in-page overlay. Shift+click keeps the normal in-page behavior.
  const openInNewTab = (symbol: string, e: { ctrlKey?: boolean; metaKey?: boolean }) => {
    if (!(e.ctrlKey || e.metaKey)) return false;
    try {
      const url = new URL(window.location.href);
      url.searchParams.set('symbol', symbol.toUpperCase());
      window.open(url.toString(), '_blank', 'noopener');
    } catch { /* ignore malformed URLs */ }
    return true;
  };

  const handleSymbolClick = (symbol: string, name: string, extra?: Partial<StockItem>, e?: React.MouseEvent) => {
    if (e && openInNewTab(symbol, e)) return;
    // Open the full detail overlay (chart + all fundamental metrics). The
    // overlay embeds the native Eclipse chart so the terminal chart controls
    // (indicators, drawings, zoom/pan) are available in the popup.
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
        fiftyTwoWeekHigh: extra?.fiftyTwoWeekHigh ?? null,
        fiftyTwoWeekLow: extra?.fiftyTwoWeekLow ?? null,
        eps: extra?.eps || 'N/A',
        dayHigh: extra?.dayHigh ?? null,
        dayLow: extra?.dayLow ?? null,
        dayOpen: extra?.dayOpen ?? null,
        previousClose: extra?.previousClose ?? null,
        beta: extra?.beta || 'N/A',
        dividendRate: extra?.dividendRate || 'N/A',
        fdv: extra?.fdv || 'N/A',
      });
  };
  
  // Screener state
  const [stockSearch, setStockSearch] = useState(initialSymbol ? initialSymbol.toUpperCase() : '');  const [stockSortField, setStockSortField] = useState<keyof StockItem>('symbol');
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
  const [userCountry, setUserCountry] = useState<string>(market || 'GLOBAL');

  // Consume a market/country dispatched by the global search (⌘K → country
  // result). Applies it once so the right market's screener loads.
  const initialMarketRef = React.useRef(market || null);
  React.useEffect(() => {
    const pending = useCommandStore.getState().consumeMarket();
    if (pending) setUserCountry(pending);
    else if (initialMarketRef.current) {
      setUserCountry(initialMarketRef.current);
      initialMarketRef.current = null;
    }
  }, []);
  const [apiStocks, setApiStocks] = useState<StockItem[]>([]);
  const [loadingApi, setLoadingApi] = useState(false);
  const [filterOptions, setFilterOptions] = useState<{ sectors: string[]; industries: string[]; types: string[]; countries: string[] }>({ sectors: [], industries: [], types: [], countries: [] });

  // Unified dynamic metrics states loaded from region-specific backend queries.
  // Start EMPTY with the dashboard loader active � placeholder demo constants
  // are never rendered as if they were data.
  const [indexData, setIndexData] = useState<IndexCard[]>([]);
  const [sectorPerformance, setSectorPerformance] = useState<SectorPerformance[]>([]);
  const [topGainers, setTopGainers] = useState<ShifterItem[]>([]);
  const [topLosers, setTopLosers] = useState<ShifterItem[]>([]);

  // Customizable ticker strip above the screener: what the user wants to see
  // on top � market indices, top gainers/losers, or a custom symbol list.
  // Persisted in localStorage so the choice survives reloads.
  type StripMode = 'indices' | 'gainers' | 'losers' | 'custom';
  const STRIP_MODE_KEY = 'be_strip_mode';
  const STRIP_CUSTOM_KEY = 'be_strip_custom_symbols';
  const [stripMode, setStripMode] = useState<StripMode>('indices');
  const [customSymbols, setCustomSymbols] = useState<string[]>([]);
  const [stripConfigOpen, setStripConfigOpen] = useState(false);
  const [stripInput, setStripInput] = useState('');
  useEffect(() => {
    try {
      const m = window.localStorage.getItem(STRIP_MODE_KEY) as StripMode | null;
      if (m && ['indices', 'gainers', 'losers', 'custom'].includes(m)) setStripMode(m);
      const s = window.localStorage.getItem(STRIP_CUSTOM_KEY);
      if (s) {
        const arr = JSON.parse(s);
        if (Array.isArray(arr)) setCustomSymbols(arr.map((x: unknown) => String(x).toUpperCase()));
      }
    } catch { /* ignore corrupted storage */ }
  }, []);
  const applyStripMode = (mode: StripMode) => {
    setStripMode(mode);
    try { window.localStorage.setItem(STRIP_MODE_KEY, mode); } catch { /* ignore */ }
  };
  const applyCustomSymbols = (list: string[]) => {
    const unique = [...new Set(list.map(s => s.trim().toUpperCase()).filter(Boolean))];
    setCustomSymbols(unique);
    try { window.localStorage.setItem(STRIP_CUSTOM_KEY, JSON.stringify(unique)); } catch { /* ignore */ }
  };

  // -- Section & table visibility (fully customizable dashboards) ----------
  // Every major block � ticker strip, sectors, shifters, and each screener
  // table (stocks / crypto / etfs / funds / dividends / forex / commodities)
  // � can be hidden by the user. Persisted in localStorage.
  type SectionKey =
    | 'strip' | 'sectors' | 'shifters'
    | 'table_stocks' | 'table_crypto' | 'table_etfs' | 'table_funds'
    | 'table_dividend' | 'table_forex' | 'table_commodities';
  const SECTION_KEY = 'be_sections_hidden';
  const SECTION_LABELS: Record<SectionKey, string> = {
    strip: 'Ticker Strip',
    sectors: 'Sectors Daily Return',
    shifters: 'Market Shifters',
    table_stocks: 'Stocks Table',
    table_crypto: 'Crypto Table',
    table_etfs: 'ETFs Table',
    table_funds: 'Mutual Funds Table',
    table_dividend: 'Dividends Table',
    table_forex: 'Forex Table',
    table_commodities: 'Commodities Table',
  };
  const [hiddenSections, setHiddenSections] = useState<SectionKey[]>([]);
  const [sectionsOpen, setSectionsOpen] = useState(false);
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(SECTION_KEY);
      if (raw) {
        const arr = JSON.parse(raw);
        if (Array.isArray(arr)) setHiddenSections(arr.filter((x: unknown): x is SectionKey => typeof x === 'string'));
      }
    } catch { /* ignore corrupted storage */ }
  }, []);
  const toggleSection = (key: SectionKey) => {
    setHiddenSections(prev => {
      const next = prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key];
      try { window.localStorage.setItem(SECTION_KEY, JSON.stringify(next)); } catch { /* ignore */ }
      return next;
    });
  };
  const sectionVisible = (key: SectionKey) => !hiddenSections.includes(key);

  // Pinned symbols resolve against the WHOLE database (every market), so a
  // custom strip like [AAPL, OGDC, BTC] stays identical across all countries.
  type PinnedCard = IndexCard & { found?: boolean; marketId?: string; source?: string; updatedAt?: string };
  const [customQuotes, setCustomQuotes] = useState<Record<string, PinnedCard>>({});
  React.useEffect(() => {
    if (stripMode !== 'custom' || customSymbols.length === 0) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/quote?symbols=${encodeURIComponent(customSymbols.join(','))}`);
        const data = await res.json();
        if (!cancelled && Array.isArray(data.quotes)) {
          const map: Record<string, PinnedCard> = {};
          for (const q of data.quotes) {
            map[q.symbol] = {
              name: q.found ? q.name : `${q.symbol}`,
              symbol: q.symbol,
              price: q.price,
              change: q.price * q.changePercent / 100,
              changePercent: q.changePercent,
              sparkline: [],
              currency: q.currency,
              found: q.found,
              marketId: q.marketId,
              source: q.source,
              updatedAt: q.updatedAt,
            };
          }
          setCustomQuotes(map);
        }
      } catch (err) {
        console.error('Failed to resolve pinned symbols:', err);
      }
    })();
    return () => { cancelled = true; };
  }, [stripMode, customSymbols]);

  // DB-backed autocomplete for the pin input � only real, priced symbols
  // from the database can be added, so typos never create dead cards.
  const [stripSuggestions, setStripSuggestions] = useState<{ symbol: string; name: string; marketId: string; currency: string; price: number }[]>([]);
  React.useEffect(() => {
    if (stripMode !== 'custom') { setStripSuggestions([]); return; }
    const query = stripInput.trim();
    if (query.length < 1) { setStripSuggestions([]); return; }
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        const res = await fetch(`/api/quote?q=${encodeURIComponent(query)}`);
        const data = await res.json();
        if (!cancelled && Array.isArray(data.suggestions)) setStripSuggestions(data.suggestions);
      } catch { /* ignore search failures */ }
    }, 250);
    return () => { cancelled = true; clearTimeout(t); };
  }, [stripInput, stripMode]);

  const timeAgo = (iso?: string | Date) => {
    if (!iso) return '';
    const diff = Date.now() - new Date(iso).getTime();
    if (diff < 0 || Number.isNaN(diff)) return '';
    const m = Math.floor(diff / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  };

  // Resolve the currency that BELONGS to an index card: prefer the currency
  // stamped by /api/indices; fall back to the selected market.
  // (cardCurrency removed � cards now always carry a currency from the API.)

  // The cards actually rendered on the customizable strip.
  const stripCards: IndexCard[] = useMemo(() => {
    if (stripMode === 'gainers') {
      return topGainers.slice(0, 6).map(g => ({
        name: g.name, symbol: g.symbol, price: g.price,
        change: g.price * g.changePercent / 100, changePercent: g.changePercent,
        sparkline: [], currency: currencyFor(userCountry),
      }));
    }
    if (stripMode === 'losers') {
      return topLosers.slice(0, 6).map(g => ({
        name: g.name, symbol: g.symbol, price: g.price,
        change: g.price * g.changePercent / 100, changePercent: g.changePercent,
        sparkline: [], currency: currencyFor(userCountry),
      }));
    }
    if (stripMode === 'custom') {
      return customSymbols.map(sym => {
        const quote = customQuotes[sym];
        if (quote) return quote;
        // Instant local fill while /api/quote resolves in the background.
        const stock = apiStocks.find(x => x.symbol.toUpperCase() === sym);
        if (stock) {
          return {
            name: stock.name || sym, symbol: sym, price: stock.price,
            change: stock.price * stock.changePercent / 100, changePercent: stock.changePercent,
            sparkline: [], currency: currencyFor(stock.country),
          };
        }
        const idx = indexData.find(x => x.symbol.toUpperCase() === sym);
        if (idx) return idx;
        return { name: `${sym} - loading...`, symbol: sym, price: 0, change: 0, changePercent: 0, sparkline: [] };
      });
    }
    return indexData;
  }, [stripMode, topGainers, topLosers, customSymbols, customQuotes, apiStocks, indexData, userCountry]);

  // -- Market sentiment (drives the app-wide aurora glow) --------------------
  // SOURCE OF TRUTH: derived from the selected market's live dashboard data via
  // `marketSentimentFromIndices` (src/lib/aurora-sentiment.ts):
  //   • EQUITY INDEX AVERAGE — Bitcoin/Gold/oil cards are excluded: they are
  //     hedges that rise on risk-off days and used to invert the signal
  //     (gold +1% painted the glow green while every stock index bled red).
  //   • INDEX BREADTH — fraction of equity indices trading up. A 0.0% avg
  //     with 5/5 indices red is bearish, not neutral.
  //   • SECTOR BREADTH — fraction of sectors up, as confirmation.
  // The reading is normalized to [-1, +1] (tanh-compressed); `null` means no
  // priced index data → UNAVAILABLE (callers fall back to neutral, never bull).
  const sentimentScore = React.useMemo(
    () => marketSentimentFromIndices(indexData, sectorPerformance),
    [indexData, sectorPerformance],
  );

  // Boolean mirror for legacy consumers. Hysteresis: |score| within ±0.15
  // keeps the previous state so neutral afternoons don't strobe green/red.
  const lastSentimentRef = React.useRef(true);
  const isMarketBullish = React.useMemo(() => {
    if (sentimentScore === null) return lastSentimentRef.current;
    if (sentimentScore > 0.15) lastSentimentRef.current = true;
    else if (sentimentScore < -0.15) lastSentimentRef.current = false;
    // Within the dead-band: keep the previous state (hysteresis).
    return lastSentimentRef.current;
  }, [sentimentScore]);

  // Sync the legacy boolean with the layout container.
  useEffect(() => {
    if (onMarketStatusChange) {
      onMarketStatusChange(isMarketBullish);
    }
  }, [isMarketBullish, onMarketStatusChange]);

  // Active view tab inside dashboard ('stocks' | 'etfs' | 'funds' | 'dividend_stocks' | 'crypto' | 'markets' | 'forex' | 'commodities')
  const [screenerTab, setScreenerTab] = useState<'stocks' | 'etfs' | 'funds' | 'dividend_stocks' | 'crypto' | 'markets' | 'forex' | 'commodities'>('markets');
  const [loadingTab, setLoadingTab] = useState(false);

  const handleTabChange = (tab: 'stocks' | 'etfs' | 'funds' | 'dividend_stocks' | 'crypto' | 'markets' | 'forex' | 'commodities') => {
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
  //   GLOBAL ? show the global markets overview (all indices).
  //   any country ? switch to that country's stock screener.
  const handleMarketSelect = (market: string) => {
    // Market cards carry DB ids (e.g. "US"); the <select> uses "USA" � normalize.
    const normalized = market === 'US' ? 'USA' : market;
    setUserCountry(normalized);
    if (normalized === 'GLOBAL') {
      handleTabChange('markets');
      return;
    }
    if (normalized === 'FOREX') {
      handleTabChange('forex');
      return;
    }
    if (normalized === 'COMMODITIES') {
      handleTabChange('commodities');
      return;
    }
    if (normalized === 'CRYPTO') {
      handleTabChange('crypto');
      return;
    }
    if (screenerTab === 'markets' || screenerTab === 'crypto' || screenerTab === 'forex' || screenerTab === 'commodities') {
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
  const lastDashboardMarketRef = React.useRef<string | null>(null);

  const [dataUpdatedTime, setDataUpdatedTime] = useState<string | null>(null);
  const [dataSource, setDataSource] = useState<string>('live');

  const getQueryCountry = React.useCallback(() => {
    if (screenerTab === 'crypto') return 'CRYPTO';
    // The Markets/GLOBAL view has no stock universe; default to US stocks.
    if (userCountry === 'GLOBAL' || userCountry === 'All') return 'US';
    return userCountry;
  }, [screenerTab, userCountry]);

  // Live dashboard metrics (index quotes, sector performance, shifters) from
  // /api/indices � refreshed whenever the selected market changes. Falls back
  // to the static demo data if the endpoint is unreachable.
  React.useEffect(() => {
    let cancelled = false;
    // Stale-while-revalidate: if we already have data for THIS market, keep it
    // on screen and refresh silently; only clear + show the loader when the
    // market actually changed (so market A's cards never show under market B).
    const qc = screenerTab === 'markets' ? 'US' : getQueryCountry();
    // Stale-while-revalidate: if we already have data for THIS market, keep it
    // on screen and refresh silently; only clear + show the loader when the
    // market actually changed (so market A's cards never show under market B).
    const sameMarket = lastDashboardMarketRef.current === qc;
    lastDashboardMarketRef.current = qc;
    if (!sameMarket || indexData.length === 0) {
      setIndexData([]);
      setSectorPerformance([]);
      setLoadingDashboard(true);
    }
    const load = async (allowRetry: boolean) => {
      try {
        // The Markets/GLOBAL overview still needs index cards + sectors +
        // shifters � it just scopes the screener table to US by default.
        const res = await fetch(`/api/indices?market=${encodeURIComponent(qc)}`);
        const data = await res.json();
        if (cancelled || !data) return false;
        if (Array.isArray(data.indices) && data.indices.length > 0) {
          setIndexData(data.indices);
        }
        if (Array.isArray(data.sectors) && data.sectors.length > 0) {
          setSectorPerformance(data.sectors);
        }
        if (data.shifters) {
          if (Array.isArray(data.shifters.gainers) && data.shifters.gainers.length > 0) {
            setTopGainers(data.shifters.gainers);
          } else {
            setTopGainers([]);
          }
          if (Array.isArray(data.shifters.losers) && data.shifters.losers.length > 0) {
            setTopLosers(data.shifters.losers);
          } else {
            setTopLosers([]);
          }
        }
        // A cold-start cache may serve index cards WITHOUT sectors/shifters
        // (they are rebuilt from JDDS in the background). Retry once so the
        // sections fill in as soon as the fresh payload lands.
        const incomplete = (Array.isArray(data.sectors) && data.sectors.length === 0)
          || (data.shifters && (!Array.isArray(data.shifters.gainers) || data.shifters.gainers.length === 0));
        if (incomplete && allowRetry) {
          await new Promise((r) => setTimeout(r, 6000));
          if (cancelled) return true;
          return await load(false);
        }
        return true;
      } catch (err) {
        console.error('Failed to load dashboard metrics:', err);
        return false;
      }
    };
    (async () => {
      await load(true);
      // Unconditional: never leave the full-screen loader stuck, even if a
      // newer effect run superseded this one (cancelled).
      setLoadingDashboard(false);
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screenerTab, userCountry, getQueryCountry]);

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

  // Table load progress (ASCII loader): creeps toward 95% while work runs,
  // snaps to 100% on completion. "soft" starts keep an already-running bar.
  const [tableLoader, setTableLoader] = useState<{ active: boolean; pct: number; label: string }>({ active: false, pct: 0, label: '' });
  const tableLoaderTimer = React.useRef<ReturnType<typeof setInterval> | null>(null);
  const startTableLoader = React.useCallback((label: string, soft = false) => {
    setTableLoader(prev => {
      if (soft && prev.active) return { ...prev, label };
      return { active: true, pct: soft ? Math.max(prev.pct, 3) : 3, label };
    });
    if (!tableLoaderTimer.current) {
      tableLoaderTimer.current = setInterval(() => {
        setTableLoader(prev => prev.active
          ? { ...prev, pct: Math.min(95, prev.pct + Math.max(0.6, (95 - prev.pct) * 0.07)) }
          : prev);
      }, 280);
    }
  }, []);
  const finishTableLoader = React.useCallback(() => {
    if (tableLoaderTimer.current) { clearInterval(tableLoaderTimer.current); tableLoaderTimer.current = null; }
    setTableLoader(prev => ({ ...prev, pct: 100 }));
    setTimeout(() => setTableLoader({ active: false, pct: 0, label: '' }), 700);
  }, []);
  // Stop any running loader when the screen unmounts.
  useEffect(() => () => {
    if (tableLoaderTimer.current) clearInterval(tableLoaderTimer.current);
  }, []);

  const refreshStocks = React.useCallback(async (qc: string, silent = false) => {
    // Stale-while-revalidate: only block on a skeleton when we have nothing to
    // show yet. Otherwise keep the current data visible while refreshing.
    if (!silent && apiStocks.length === 0) {
      setLoadingApi(true);
      setLoadingDashboard(true);
    }
    startTableLoader(silent ? `syncing ${qc} prices...` : `loading ${qc} market data...`, silent);
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
      finishTableLoader();
    } finally {
      if (!silent && apiStocks.length === 0) {
        setLoadingApi(false);
        setLoadingDashboard(false);
      }
      if (!silent) finishTableLoader();
      setLoadingTab(false);
    }
  }, [fallbackToDemo, fetchPage, currentPage, pageCache, apiStocks.length, startTableLoader, finishTableLoader]);

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

  // Automatic price backfill: whenever a region's screener is shown and its
  // prices are missing/stale (>15 min), pull live quotes for THE VISIBLE PAGE
  // from yfinance/TradingView so rows show fresh prices within seconds.
  // (Passing symbols scopes /api/refresh to just this page � a full-market
  // backfill here took minutes on big universes like US/CN and made country
  // switches feel frozen. Background schedulers cover the whole universe.)
  const [autoRefreshedMarket, setAutoRefreshedMarket] = useState<string | null>(null);
  React.useEffect(() => {
    const qc = getQueryCountry();
    // Skip global markets overview & the demo/empty fallback.
    if (userCountry === 'GLOBAL' || screenerTab === 'markets') return;
    if (!apiStocks.length) return;
    if (autoRefreshedMarket === qc) return;
    const STALE_MS = 1000 * 60 * 15;
    const needsPrice = apiStocks.some((s) => {
      if (s.priceMissing || !s.price || s.price <= 0) return true;
      if (!s.updatedAt) return true; // no timestamp ? assume stale
      return Date.now() - new Date(s.updatedAt).getTime() > STALE_MS;
    });
    if (!needsPrice) {
      setAutoRefreshedMarket(qc);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        startTableLoader(`syncing live ${qc} prices from exchange...`, true);
        const res = await fetch('/api/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ market: qc, symbols: apiStocks.map((s) => s.symbol).filter(Boolean) }),
        });
        const data = await res.json();
        if (!cancelled && data && data.success && data.ok > 0) {
          // Live prices now persisted ? reload silently so the page reflects them.
          await refreshStocks(qc, true);
        }
        if (!cancelled) setAutoRefreshedMarket(qc);
      } catch {
        if (!cancelled) setAutoRefreshedMarket(qc);
      } finally {
        if (!cancelled) finishTableLoader();
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiStocks, currentPage, userCountry, screenerTab, getQueryCountry]);

  // Global markets overview: top stocks per market so the Markets tab shows
  // what is actually moving across world markets (not loader metadata).
  // Fully user-customizable: layout, countries, visible columns, rows per
  // market � persisted in localStorage.
  type GmLayout = 'compact' | 'comfortable' | 'focus';
  type GmColumns = { ticker: boolean; name: boolean; price: boolean; change: boolean; cap: boolean };
  type GmColumnKey = keyof GmColumns;
  type GmConfig = {
    layout: GmLayout;
    columns: GmColumns;
    columnOrder: GmColumnKey[]; // left ? right display order of table columns
    rows: number;
    countries: string[] | null;
    sortBy: 'cap' | 'change' | 'price' | 'name';
    movers: 'all' | 'gainers' | 'losers';
    dense: boolean;
    showRank: boolean;
    highlightExtremes: boolean;
    groupOrder: 'az' | 'movers';
    order: string[] | null; // manual country-card order (drag & drop / buttons)
  };
  const GM_CONFIG_KEY = 'be_gm_config';
  const GM_COLUMN_ORDER: GmColumnKey[] = ['ticker', 'name', 'price', 'cap', 'change'];
  const GM_COLUMN_LABELS: Record<GmColumnKey, string> = {
    ticker: 'Ticker', name: 'Name', price: 'Price', cap: 'Mkt Cap', change: 'Change %',
  };
  const GM_DEFAULTS: GmConfig = {
    layout: 'compact',
    columns: { ticker: true, name: true, price: true, change: true, cap: true },
    columnOrder: GM_COLUMN_ORDER,
    rows: 5,
    countries: null, // null = all countries
    sortBy: 'cap',
    movers: 'all',
    dense: false,
    showRank: false,
    highlightExtremes: false,
    groupOrder: 'az',
    order: null,
  };
  const [gmConfig, setGmConfig] = useState<GmConfig>(GM_DEFAULTS);
  const [gmConfigOpen, setGmConfigOpen] = useState(false);
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(GM_CONFIG_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        setGmConfig((prev) => ({
          ...prev,
          ...parsed,
          columns: { ...prev.columns, ...(parsed.columns || {}) },
          columnOrder: Array.isArray(parsed.columnOrder)
            // Repair saved orders missing/duplicating keys after app updates.
            ? GM_COLUMN_ORDER.filter((k) => parsed.columnOrder.includes(k))
              .concat(GM_COLUMN_ORDER.filter((k) => !parsed.columnOrder.includes(k)))
            : prev.columnOrder,
        }));
      }
    } catch { /* ignore corrupted storage */ }
  }, []);
  const applyGmConfig = (patch: Partial<GmConfig>) => {
    setGmConfig((prev) => {
      const next = { ...prev, ...patch };
      try { window.localStorage.setItem(GM_CONFIG_KEY, JSON.stringify(next)); } catch { /* ignore */ }
      return next;
    });
  };
  // Move a column left/right in the display order.
  const moveGmColumn = (key: GmColumnKey, dir: -1 | 1) => {
    const order = [...(gmConfig.columnOrder ?? GM_COLUMN_ORDER)];
    const i = order.indexOf(key);
    const j = i + dir;
    if (i === -1 || j < 0 || j >= order.length) return;
    [order[i], order[j]] = [order[j], order[i]];
    applyGmConfig({ columnOrder: order });
  };
  // Generic list reorder used by the ordering buttons in the config panel.
  const reorderList = <T,>(list: T[], item: T, dir: -1 | 1): T[] => {
    const i = list.indexOf(item);
    const j = i + dir;
    if (i === -1 || j < 0 || j >= list.length) return list;
    const next = [...list];
    [next[i], next[j]] = [next[j], next[i]];
    return next;
  };

  // Drag & drop reordering of the market tables � custom pointer-based drag.
  // 100% DOM-driven while dragging: the floating copy follows the cursor via
  // direct transforms, and the preview reorder moves real DOM nodes with FLIP
  // animations. ZERO React re-renders during the drag (state only changes on
  // drag start/end), which is what keeps it buttery smooth.
  const [gmDragId, setGmDragId] = useState<string | null>(null);
  const [gmDragWidth, setGmDragWidth] = useState(0);
  const gmFloatRef = React.useRef<HTMLDivElement | null>(null);
  const gmLastTargetRef = React.useRef<string | null>(null);
  const gmScrollerRef = React.useRef<HTMLElement | null>(null);
  const gmScrollTopRef = React.useRef(0);
  const gmScrollSpeedRef = React.useRef(0);
  const gmScrollRAF = React.useRef<number | null>(null);
  const gmSuppressClick = React.useRef(false);

  // Commit the CURRENT on-screen DOM order as the saved preference. The live
  // preview already moved the dragged card to exactly where the user dropped
  // it � persisting what they see is always correct, in every direction.
  const commitGmDomOrder = (grid: HTMLElement) => {
    const order: string[] = [];
    grid.querySelectorAll<HTMLElement>('[data-gm-card]').forEach((el) => {
      const gid = el.getAttribute('data-gm-id');
      if (gid) order.push(gid);
    });
    if (order.length > 0) applyGmConfig({ order });
  };

  // DOM-level preview reorder: move the (hidden) dragged card's node to the
  // target's slot, then FLIP-animate every other card from its old position.
  // No React state involved � the grid re-renders only on drop.
  const domPreviewReorder = (grid: HTMLElement, draggedId: string, targetId: string) => {
    const cards = [...grid.querySelectorAll<HTMLElement>('[data-gm-card]')];
    const draggedEl = cards.find(el => el.getAttribute('data-gm-id') === draggedId);
    const targetEl = cards.find(el => el.getAttribute('data-gm-id') === targetId);
    if (!draggedEl || !targetEl || draggedEl === targetEl) return;
    const from = cards.indexOf(draggedEl);
    const to = cards.indexOf(targetEl);
    if (to === from) return;

    // Record old centers for FLIP.
    const old = new Map<string, { x: number; y: number }>();
    cards.forEach(el => {
      const r = el.getBoundingClientRect();
      old.set(el.getAttribute('data-gm-id')!, { x: r.left + r.width / 2, y: r.top + r.height / 2 });
    });

    // Move the dragged node to the target's slot.
    if (to > from) {
      grid.insertBefore(draggedEl, cards[to + 1] ?? null);
    } else {
      grid.insertBefore(draggedEl, cards[to]);
    }

    // FLIP every other card from its old center to its new one.
    grid.querySelectorAll<HTMLElement>('[data-gm-card]').forEach(el => {
      if (el === draggedEl) return;
      const gid = el.getAttribute('data-gm-id');
      if (!gid) return;
      const f = old.get(gid);
      if (!f) return;
      const r = el.getBoundingClientRect();
      const dx = f.x - (r.left + r.width / 2);
      const dy = f.y - (r.top + r.height / 2);
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return;
      el.style.transition = 'none';
      el.style.transform = `translate(${dx}px, ${dy}px)`;
      requestAnimationFrame(() => {
        el.style.transition = 'transform 300ms cubic-bezier(.22,.9,.24,1)';
        el.style.transform = '';
      });
    });
  };

  const beginGmDrag = (clientX: number, clientY: number, button: number, anchor: HTMLElement) => {
    if (button !== 0) return;
    const card = anchor.closest('[data-gm-card]') as HTMLElement | null;
    if (!card) return;
    const grid = card.parentElement;
    if (!grid) return;
    const id = card.getAttribute('data-gm-id');
    if (!id) return;

    // The scroll container (the page's main scroller) for edge auto-scroll.
    // Must actually be scrollable � an overflow-y:auto ancestor with no
    // overflow (scrollHeight === clientHeight) is not the real scroller.
    const scroller = (() => {
      let el: HTMLElement | null = card;
      while (el) {
        const s = getComputedStyle(el);
        if ((s.overflowY === 'auto' || s.overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 1) {
          return el;
        }
        el = el.parentElement;
      }
      return document.scrollingElement as HTMLElement | null;
    })();
    gmScrollerRef.current = scroller;
    gmScrollTopRef.current = scroller?.scrollTop ?? 0;

    const startX = clientX;
    const startY = clientY;
    const cardRect = card.getBoundingClientRect();
    let started = false;

    // LIVE hit-test against the current on-screen card rects (NOT a drag-start
    // snapshot � cards FLIP to new slots as the preview reorders, so stale
    // rects made placing into center/other rows fail). Padding covers the
    // small grid gaps so dropping between cards also works.
    const liveHitTest = (x: number, y: number): string | null => {
      const PAD = 8;
      let best: string | null = null;
      let bestDist = Infinity;
      const cards = grid.querySelectorAll<HTMLElement>('[data-gm-card]');
      for (const el of cards) {
        const gid = el.getAttribute('data-gm-id');
        if (!gid || gid === id) continue;
        const r = el.getBoundingClientRect();
        if (x < r.left - PAD || x > r.right + PAD || y < r.top - PAD || y > r.bottom + PAD) continue;
        const d = Math.hypot(x - (r.left + r.width / 2), y - (r.top + r.height / 2));
        if (d < bestDist) {
          bestDist = d;
          best = gid;
        }
      }
      return best;
    };

    // Edge auto-scroll: near the top/bottom of the viewport, scroll the
    // container so the user can reach tables above/below the fold.
    const EDGE = 90;
    const MAX_SPEED = 18;
    const scrollStep = () => {
      if (!started) return;
      const speed = gmScrollSpeedRef.current;
      if (speed === 0 || !scroller) return;
      scroller.scrollTop += speed;
      gmScrollTopRef.current = scroller.scrollTop;
      gmScrollRAF.current = requestAnimationFrame(scrollStep);
    };
    const updateAutoScroll = (y: number) => {
      const vh = window.innerHeight;
      let speed = 0;
      if (y < EDGE) speed = -Math.min(MAX_SPEED, ((EDGE - y) / EDGE) * MAX_SPEED);
      else if (y > vh - EDGE) speed = Math.min(MAX_SPEED, ((y - (vh - EDGE)) / EDGE) * MAX_SPEED);
      gmScrollSpeedRef.current = speed;
      if (speed !== 0 && gmScrollRAF.current === null) {
        gmScrollRAF.current = requestAnimationFrame(scrollStep);
      }
    };

    const onMove = (ev: MouseEvent) => {
      if (!started) {
        if (Math.abs(ev.clientX - startX) < 5 && Math.abs(ev.clientY - startY) < 5) return;
        started = true;
        setGmDragId(id);
        setGmDragWidth(cardRect.width);
        document.body.style.userSelect = 'none';
      }
      // The floating copy follows the cursor via direct DOM transform (no
      // state ? no re-render ? no lag). Centered on the pointer (-50%,-50%)
      // so it stays glued to the mouse arrow wherever it moves.
      const floatEl = gmFloatRef.current;
      if (floatEl) {
        floatEl.style.transform = `translate3d(${ev.clientX}px, ${ev.clientY}px, 0) translate(-50%, -50%) scale(1.02)`;
      }
      // Live preview: move the real DOM node + FLIP the others. Pure DOM work,
      // zero React renders � this is what keeps the drag smooth.
      const target = liveHitTest(ev.clientX, ev.clientY);
      if (target && gmLastTargetRef.current !== target) {
        gmLastTargetRef.current = target;
        domPreviewReorder(grid, id, target);
      }
      updateAutoScroll(ev.clientY);
    };
    const cleanup = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      document.body.style.userSelect = '';
      if (gmScrollRAF.current !== null) {
        cancelAnimationFrame(gmScrollRAF.current);
        gmScrollRAF.current = null;
      }
      gmScrollSpeedRef.current = 0;
      gmLastTargetRef.current = null;
      gmScrollerRef.current = null;
      setGmDragId(null);
    };
    const onUp = (ev: MouseEvent) => {
      // The preview moved the (invisible) dragged card into its final slot.
      // Commit the on-screen DOM order � exactly what the user sees.
      cleanup();
      if (!started) return;
      gmSuppressClick.current = true;
      setTimeout(() => { gmSuppressClick.current = false; }, 150);
      commitGmDomOrder(grid);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };
  type OverviewGroup = { id: string; country: string; name?: string; exchange: string; isCrypto: boolean; currency: string; indexName?: string; index?: { symbol: string; name: string; price: number; changePct: number } | null; stocks: Array<{ symbol: string; name: string; price: number; changePct: number; marketCap?: number | null }> };
  const [globalOverview, setGlobalOverview] = useState<OverviewGroup[]>([]);
  const [loadingGlobalMarkets, setLoadingGlobalMarkets] = useState(false);
  // Visually marks the clicked row so selection stays obvious across cards.
  const [gmSelectedRow, setGmSelectedRow] = useState<{ marketId: string; symbol: string } | null>(null);
  React.useEffect(() => {
    if (screenerTab !== 'markets') return;
    let cancelled = false;
    (async () => {
      setLoadingGlobalMarkets(true);
      try {
        const res = await fetch('/api/global-overview');
        const data = await res.json();
        if (!cancelled && data && Array.isArray(data.groups)) {
          setGlobalOverview(data.groups);
        }
      } catch (err) {
        console.error('Failed to load global overview:', err);
      } finally {
        if (!cancelled) setLoadingGlobalMarkets(false);
        setLoadingTab(false);
      }
    })();
    return () => { cancelled = true; };
  }, [screenerTab]);



  // Demo fallback rows are placeholders � all prices/changes are zero (never
  // present simulated values as market data). The UI renders them as "�".
  function getFallbackStocks(country: string): StockItem[] {
    const list = [
      { symbol: 'AAPL', name: 'Apple Inc.', sector: 'Technology', industry: 'Consumer Electronics', country: 'USA', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', dividendYield: 'N/A', index: 'N/A', recommendation: 'N/A', exchange: 'NASDAQ', forwardPE: 'N/A', peg: 'N/A', ps: 'N/A', pb: 'N/A', evEbitda: 'N/A', grossMargin: 'N/A', operatingMargin: 'N/A', netProfitMargin: 'N/A', insiderOwnership: 'N/A', institutionalOwnership: 'N/A', shortFloat: 'N/A', rsi14: 'N/A', sma20: 'N/A', sma50: 'N/A', sma200: 'N/A' },
      { symbol: 'MSFT', name: 'Microsoft Corp.', sector: 'Technology', industry: 'Software - Infrastructure', country: 'USA', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', dividendYield: 'N/A', index: 'N/A', recommendation: 'N/A', exchange: 'NASDAQ', forwardPE: 'N/A', peg: 'N/A', ps: 'N/A', pb: 'N/A', evEbitda: 'N/A', grossMargin: 'N/A', operatingMargin: 'N/A', netProfitMargin: 'N/A', insiderOwnership: 'N/A', institutionalOwnership: 'N/A', shortFloat: 'N/A', rsi14: 'N/A', sma20: 'N/A', sma50: 'N/A', sma200: 'N/A' },
      { symbol: 'NVDA', name: 'NVIDIA Corp.', sector: 'Technology', industry: 'Semiconductors', country: 'USA', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', dividendYield: 'N/A', index: 'N/A', recommendation: 'N/A', exchange: 'NASDAQ', forwardPE: 'N/A', peg: 'N/A', ps: 'N/A', pb: 'N/A', evEbitda: 'N/A', grossMargin: 'N/A', operatingMargin: 'N/A', netProfitMargin: 'N/A', insiderOwnership: 'N/A', institutionalOwnership: 'N/A', shortFloat: 'N/A', rsi14: 'N/A', sma20: 'N/A', sma50: 'N/A', sma200: 'N/A' },
      { symbol: 'BTC', name: 'Bitcoin', sector: 'Layer 1', industry: 'Layer 1', country: 'CRYPTO', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', dividendYield: 'N/A', index: 'Crypto', recommendation: 'N/A', exchange: 'BINANCE', forwardPE: 'N/A', peg: 'N/A', ps: 'N/A', pb: 'N/A', evEbitda: 'N/A', grossMargin: 'N/A', operatingMargin: 'N/A', netProfitMargin: 'N/A', insiderOwnership: 'N/A', institutionalOwnership: 'N/A', shortFloat: 'N/A', rsi14: 'N/A', sma20: 'N/A', sma50: 'N/A', sma200: 'N/A' },
      { symbol: 'ETH', name: 'Ethereum', sector: 'Layer 1', industry: 'Layer 1', country: 'CRYPTO', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', dividendYield: 'N/A', index: 'Crypto', recommendation: 'N/A', exchange: 'BINANCE', forwardPE: 'N/A', peg: 'N/A', ps: 'N/A', pb: 'N/A', evEbitda: 'N/A', grossMargin: 'N/A', operatingMargin: 'N/A', netProfitMargin: 'N/A', insiderOwnership: 'N/A', institutionalOwnership: 'N/A', shortFloat: 'N/A', rsi14: 'N/A', sma20: 'N/A', sma50: 'N/A', sma200: 'N/A' },
      { symbol: 'SOL', name: 'Solana', sector: 'Layer 1', industry: 'Layer 1', country: 'CRYPTO', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', dividendYield: 'N/A', index: 'Crypto', recommendation: 'N/A', exchange: 'BINANCE', forwardPE: 'N/A', peg: 'N/A', ps: 'N/A', pb: 'N/A', evEbitda: 'N/A', grossMargin: 'N/A', operatingMargin: 'N/A', netProfitMargin: 'N/A', insiderOwnership: 'N/A', institutionalOwnership: 'N/A', shortFloat: 'N/A', rsi14: 'N/A', sma20: 'N/A', sma50: 'N/A', sma200: 'N/A' },
      { symbol: 'BNB', name: 'Binance Coin', sector: 'Exchange Tokens', industry: 'Exchange Tokens', country: 'CRYPTO', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', dividendYield: 'N/A', index: 'Crypto', recommendation: 'N/A', exchange: 'BINANCE', forwardPE: 'N/A', peg: 'N/A', ps: 'N/A', pb: 'N/A', evEbitda: 'N/A', grossMargin: 'N/A', operatingMargin: 'N/A', netProfitMargin: 'N/A', insiderOwnership: 'N/A', institutionalOwnership: 'N/A', shortFloat: 'N/A', rsi14: 'N/A', sma20: 'N/A', sma50: 'N/A', sma200: 'N/A' }
    ];
    if (country === 'All') return list;
    const resolved = country === 'CRYPTO' || country === 'Crypto' ? 'CRYPTO' : 'USA';
    return list.filter(item => item.country === resolved);
  }



  // Fund state
  const [fundSearch, setFundSearch] = useState('');
  const [fundCategory, setFundCategory] = useState('All');
  const [fundSortField, setFundSortField] = useState<keyof FundItem>('symbol');
  const [fundSortOrder, setFundSortOrder] = useState<'asc' | 'desc'>('asc');
  const [apiFunds, setApiFunds] = useState<FundItem[]>([]);
  const [, setTotalFunds] = useState(0);

  // ETF state
  const [etfSearch, setEtfSearch] = useState('');
  const [etfCategory, setEtfCategory] = useState('All');
  const [etfSortField, setEtfSortField] = useState<keyof ETFItem>('symbol');
  const [etfSortOrder, setEtfSortOrder] = useState<'asc' | 'desc'>('asc');
  const [apiEtfs, setApiEtfs] = useState<ETFItem[]>([]);
  const [, setTotalEtfs] = useState(0);

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
          const mapped: ETFItem[] = (data.stocks as Array<Record<string, unknown>>).map(s => ({
            symbol: String(s.symbol ?? ''),
            name: String(s.name ?? ''),
            category: (s.industry as string) || 'General',
            price: (s.price as number) || 0,
            changePercent: (s.changePercent as number) || 0,
            volume: (s.volume as string) || 'N/A',
            aum: (s.marketCap as string) || 'N/A',
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
          const mapped: FundItem[] = (data.stocks as Array<Record<string, unknown>>).map(s => ({
            symbol: String(s.symbol ?? ''),
            name: String(s.name ?? ''),
            category: (s.industry as string) || 'General',
            nav: (s.price as number) || 0,
            changePercent: (s.changePercent as number) || 0,
            ytdReturn: 0,
            expenseRatio: 0,
            rating: 0,
            aum: (s.marketCap as string) || 'N/A',
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

  // Forex states + fetch � live major currency pairs from /api/forex.
  type ForexPair = { symbol: string; name: string; base: string; quote: string; price: number; changePct: number; found: boolean };
  const [forexPairs, setForexPairs] = useState<ForexPair[]>([]);
  const [forexSearch, setForexSearch] = useState('');
  const [forexChange, setForexChange] = useState('All');
  const [forexCurrency, setForexCurrency] = useState('All');
  const [forexSortField, setForexSortField] = useState<keyof ForexPair>('symbol');
  const [forexSortOrder, setForexSortOrder] = useState<'asc' | 'desc'>('asc');
  const [loadingForex, setLoadingForex] = useState(false);
  React.useEffect(() => {
    if (screenerTab !== 'markets' && screenerTab !== 'forex') return;
    // Already loaded � switching between the overview card and the dedicated
    // table must be instant, not refetch the (slow) bridge.
    if (forexPairs.length > 0) { setLoadingTab(false); return; }
    let cancelled = false;
    (async () => {
      setLoadingForex(true);
      try {
        const res = await fetch('/api/forex');
        const data = await res.json();
        if (!cancelled && data && Array.isArray(data.pairs)) {
          setForexPairs(data.pairs);
        }
      } catch (err) {
        console.error('Failed to load forex pairs', err);
      } finally {
        if (!cancelled) setLoadingForex(false);
        setLoadingTab(false);
      }
    })();
    return () => { cancelled = true; };
  }, [screenerTab, forexPairs.length]);

  const toggleForexSort = (field: keyof ForexPair) => {
    if (forexSortField === field) {
      setForexSortOrder(forexSortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setForexSortField(field);
      setForexSortOrder('asc');
    }
  };
  const filteredForex = useMemo(() => {
    let list = forexPairs;
    if (forexSearch.trim()) {
      const q = forexSearch.trim().toLowerCase();
      list = list.filter(p => p.symbol.toLowerCase().includes(q) || p.name.toLowerCase().includes(q) || p.base.toLowerCase().includes(q) || p.quote.toLowerCase().includes(q));
    }
    // Preference filters: change direction, base currency, quote currency.
    if (forexChange === 'Gainers') list = list.filter(p => p.found && p.changePct > 0);
    else if (forexChange === 'Losers') list = list.filter(p => p.found && p.changePct < 0);
    else if (forexChange === 'Flat') list = list.filter(p => !p.found || p.changePct === 0);
    if (forexCurrency !== 'All') {
      list = list.filter(p => p.base === forexCurrency || p.quote === forexCurrency);
    }
    const dir = forexSortOrder === 'asc' ? 1 : -1;
    return [...list].sort((a, b) => {
      const av = a[forexSortField];
      const bv = b[forexSortField];
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
  }, [forexPairs, forexSearch, forexChange, forexCurrency, forexSortField, forexSortOrder]);

  // Commodities states + fetch � live major commodity futures from /api/commodities.
  type CommodityItem = { symbol: string; name: string; unit: string; price: number; changePct: number; found: boolean };
  const [commodities, setCommodities] = useState<CommodityItem[]>([]);
  const [commoditySearch, setCommoditySearch] = useState('');
  const [commodityChange, setCommodityChange] = useState('All');
  const [commodityCategory, setCommodityCategory] = useState('All');
  const [loadingCommodities, setLoadingCommodities] = useState(false);
  React.useEffect(() => {
    if (screenerTab !== 'markets' && screenerTab !== 'commodities') return;
    // Already loaded � switching between the overview card and the dedicated
    // table must be instant, not refetch the (slow) bridge.
    if (commodities.length > 0) { setLoadingTab(false); return; }
    let cancelled = false;
    (async () => {
      setLoadingCommodities(true);
      try {
        const res = await fetch('/api/commodities');
        const data = await res.json();
        if (!cancelled && data && Array.isArray(data.commodities)) {
          setCommodities(data.commodities);
        }
      } catch (err) {
        console.error('Failed to load commodities', err);
      } finally {
        if (!cancelled) setLoadingCommodities(false);
        setLoadingTab(false);
      }
    })();
    return () => { cancelled = true; };
  }, [screenerTab, commodities.length]);

  const filteredCommodities = useMemo(() => {
    let list = commodities;
    if (commoditySearch.trim()) {
      const q = commoditySearch.trim().toLowerCase();
      list = list.filter(c => c.name.toLowerCase().includes(q) || c.symbol.toLowerCase().includes(q));
    }
    // Preference filters: change direction + category (energy/metals/agriculture).
    if (commodityChange === 'Gainers') list = list.filter(c => c.found && c.changePct > 0);
    else if (commodityChange === 'Losers') list = list.filter(c => c.found && c.changePct < 0);
    else if (commodityChange === 'Flat') list = list.filter(c => !c.found || c.changePct === 0);
    if (commodityCategory !== 'All') {
      const energy = ['GC=F', 'SI=F', 'HG=F', 'PL=F', 'PA=F', 'ALI=F'];
      const agri = ['ZW=F', 'ZC=F', 'ZS=F', 'KC=F', 'CC=F', 'SB=F', 'CT=F', 'LE=F'];
      list = list.filter(c =>
        commodityCategory === 'Energy'
          ? ['CL=F', 'BZ=F', 'NG=F'].includes(c.symbol)
          : commodityCategory === 'Metals'
            ? energy.includes(c.symbol)
            : agri.includes(c.symbol)
      );
    }
    return list;
  }, [commodities, commoditySearch, commodityChange, commodityCategory]);

  // Dividend states
  const [dividendSearch, setDividendSearch] = useState('');
  const [dividendSortField, setDividendSortField] = useState<keyof BlueChipItem>('symbol');
  const [dividendSortOrder, setDividendSortOrder] = useState<'asc' | 'desc'>('asc');


  const handleAction = (ticker: string) => {
    onAnalyzeTicker(ticker);
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
          "w-full py-6 space-y-6 pb-20",
          !embedded && "flex-1 overflow-y-auto h-full bg-transparent"
        )}>
          {!embedded && (
            <div className="flex items-center justify-between gap-4 pb-6">
              <div className="space-y-2.5">
                <TableLoading pct={25} label="loading" />
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 md:gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="p-3.5 rounded-2xl glass-card border border-white/10 dark:border-white/5 flex items-center justify-center">
                <TableLoading pct={Math.min(95, 20 + i * 12)} label="loading" />
              </div>
            ))}
          </div>

          <div className="grid lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 h-64 rounded-2xl glass-card border border-white/10 dark:border-white/5 flex items-center justify-center">
              <TableLoading pct={55} label="loading market data" />
            </div>
            <div className="h-64 rounded-2xl glass-card border border-white/10 dark:border-white/5 flex items-center justify-center">
              <TableLoading pct={55} label="loading shifters" />
            </div>
          </div>

          <div className="rounded-2xl glass-card border border-white/10 dark:border-white/5 p-6 flex items-center justify-center">
            <TableLoading pct={70} label="loading screener table" />
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      {(loadingApi || loadingTab || loadingDashboard) && <TopLoader />}
      <div className={cn(
        "w-full py-6 space-y-8 pb-20 relative bg-transparent",
        !embedded && "flex-1 overflow-y-auto h-full"
      )}>
      
      {/* Page Title Header */}
      {!embedded && (
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 animate-fade-in-up border-b border-border/20 pb-6 mb-4">
          <div>
            <h1 className="font-serif text-3xl md:text-4xl font-medium tracking-tight text-foreground flex items-center gap-3">
              <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/15 shadow-lg shadow-primary/10">
                <ChartCandlestick className="text-primary" size={30} />
              </span>
              Market Screener
            </h1>
            <p className="text-muted-foreground text-sm mt-2">
              Real-time asset indices, sector breakdowns, high-fidelity stock databases, and automated AI analysis.
            </p>
          </div>
          
          <div className="flex items-center gap-2 glass-card-subtle p-1.5 rounded-3xl border border-border/40 shrink-0 self-start md:self-auto">
            <span className="text-[10px] uppercase font-bold text-muted-foreground/80 px-2 tracking-wider">Market:</span>
            <select
              value={userCountry === 'CRYPTO' ? 'CRYPTO' : (userCountry === 'GLOBAL' && screenerTab === 'stocks') ? 'USA' : userCountry === 'US' ? 'USA' : userCountry}
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
              <option value="FOREX">Forex</option>
              <option value="COMMODITIES">Commodities</option>
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

      {/* Customizable Ticker Strip */}
      {sectionVisible('strip') && (
      <div className="animate-fade-in-up [animation-delay:100ms]">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10px] uppercase font-bold text-muted-foreground/80 tracking-wider px-1">
            {stripMode === 'indices' ? 'Market Indices' : stripMode === 'gainers' ? 'Top Gainers' : stripMode === 'losers' ? 'Top Losers' : 'My Symbols'}
          </span>
          <span className="flex items-center gap-1.5">
            <button
              onClick={() => toggleSection('strip')}
              className="text-[10px] font-bold text-muted-foreground hover:text-rose-400 uppercase tracking-wider cursor-pointer transition-colors"
              title="Hide this section (re-enable from the Sections button below)"
            >
              Hide
            </button>
            <button
              onClick={() => setStripConfigOpen(o => !o)}
              className={`flex items-center gap-1.5 text-xs font-bold tracking-wider border rounded-lg px-3.5 py-2 transition-all cursor-pointer ${
                stripConfigOpen
                  ? 'text-primary bg-primary/10 border-primary/40'
                  : 'text-muted-foreground hover:text-primary bg-accent/40 hover:bg-accent/70 border-border/40'
              }`}
              title="Customize what shows here"
            >
              <Sliders size={14} /> Customize
            </button>
          </span>
        </div>
        {/* Inline config panel � expands in flow so content below moves down
            instead of being covered by a floating popover. */}
        {stripConfigOpen && (
          <div className="mb-3 p-3 sm:p-4 rounded-xl bg-background border border-border shadow-lg w-full max-w-full overflow-hidden animate-fade-in-up">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5 sm:max-w-md">
              {([
                ['indices', 'Indices'],
                ['gainers', 'Top Gainers'],
                ['losers', 'Top Losers'],
                ['custom', 'My Symbols'],
              ] as [StripMode, string][]).map(([mode, label]) => (
                <button
                  key={mode}
                  onClick={() => applyStripMode(mode)}
                  className={`px-2 py-1.5 rounded-lg text-[11px] font-bold transition-all cursor-pointer border whitespace-nowrap ${
                    stripMode === mode
                      ? 'bg-primary/15 text-primary border-primary/40'
                      : 'text-muted-foreground border-border/40 hover:bg-accent/40'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            {stripMode === 'custom' && (
              <div className="mt-3">
                <div className="flex flex-col sm:flex-row gap-1.5 w-full">
                  <input
                    value={stripInput}
                    onChange={e => setStripInput(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter' && stripInput.trim()) {
                        applyCustomSymbols([...customSymbols, stripInput]);
                        setStripInput('');
                      }
                    }}
                    placeholder="Type any symbol, e.g. AAPL, OGDC, BTC"
                    className="flex-1 min-w-0 bg-accent/30 border border-border/60 rounded-lg px-2 py-1.5 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                  <Button
                    size="sm"
                    onClick={() => { if (stripInput.trim()) { applyCustomSymbols([...customSymbols, stripInput]); setStripInput(''); } }}
                    className="h-auto py-1.5 px-3 text-xs cursor-pointer shrink-0"
                  >
                    Add
                  </Button>
                </div>
                {stripSuggestions.length > 0 && (
                  <div className="mt-2">
                    <p className="text-[9px] uppercase font-bold text-muted-foreground/70 tracking-wider mb-1">Matches from database � click to pin</p>
                    <div className="flex flex-col gap-1">
                      {stripSuggestions.map(s => (
                        <button
                          key={`${s.marketId}-${s.symbol}`}
                          onClick={() => {
                            applyCustomSymbols([...customSymbols, s.symbol]);
                            setStripInput('');
                            setStripSuggestions([]);
                          }}
                          className="flex items-center justify-between gap-2 w-full text-left bg-accent/20 hover:bg-primary/10 border border-border/40 hover:border-primary/40 rounded-lg px-2.5 py-1.5 transition-all cursor-pointer"
                        >
                          <span className="flex items-center gap-2 min-w-0">
                            <span className="font-mono text-[11px] font-bold text-foreground/80">{s.symbol}</span>
                            <span className="text-[11px] text-muted-foreground truncate">{s.name}</span>
                          </span>
                          <span className="font-mono text-[11px] font-semibold text-foreground shrink-0">
                            {s.price > 0 ? priceWithCurrency(s.marketId || s.currency, s.price) : '�'}
                            <span className="ml-1.5 text-[9px] text-muted-foreground/70">{s.marketId}</span>
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {customSymbols.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {customSymbols.map(sym => (
                      <span key={sym} className="inline-flex items-center gap-1 bg-accent/40 border border-border/40 rounded-full pl-2 pr-1 py-0.5 text-[10px] font-mono font-bold">
                        {sym}
                        <button
                          onClick={() => applyCustomSymbols(customSymbols.filter(s => s !== sym))}
                          className="text-muted-foreground hover:text-rose-400 cursor-pointer leading-none"
                        >
                          <X size={11} />
                        </button>
                      </span>
                    ))}
                  </div>
                )}
                <p className="text-[9px] text-muted-foreground mt-2">Searches every market (US, PSX, India, crypto�). Pinned symbols stay fixed across all countries.</p>
              </div>
            )}
          </div>
        )}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 md:gap-4">
          {(loadingDashboard && stripMode !== 'custom') ? (
            Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="p-3.5 rounded-2xl glass-card border border-white/10 dark:border-white/5 flex items-center justify-center">
                <TableLoading pct={Math.min(95, 15 + i * 13)} label="loading" />
              </div>
            ))
          ) : stripCards.length > 0 ? (
            stripCards.map((idxCard) => {
              const isPositive = idxCard.changePercent >= 0;
              const pinned = stripMode === 'custom' ? customQuotes[idxCard.symbol] : undefined;
              return (
                <div
                  key={`${stripMode}-${idxCard.symbol}`}
                  onClick={(e) => {
                    if (openInNewTab(idxCard.symbol, e)) return;
                    if (onSelectChartSymbol) {
                      onSelectChartSymbol(idxCard.symbol);
                    } else {
                      handleAction(idxCard.symbol);
                    }
                  }}
                  title="Ctrl+click to open in new tab"
                  className="p-3.5 rounded-2xl glass-card border border-white/10 dark:border-white/5 hover:border-primary/50 transition-all duration-300 flex flex-col justify-between group cursor-pointer"
                >
                  <div>
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] text-muted-foreground font-semibold uppercase truncate" title={idxCard.name}>{idxCard.name}</span>
                      <span className="text-[10px] font-mono font-bold bg-accent/40 px-1.5 py-0.5 rounded text-foreground">{idxCard.symbol}</span>
                    </div>
                    <div className="mt-2 flex items-baseline gap-1">
                      <span className="font-mono text-base font-bold text-foreground">
                        {idxCard.price > 0 ? priceWithCurrency(idxCard.currency || userCountry, idxCard.price) : '�'}
                      </span>
                    </div>
                    {stripMode === 'custom' && customQuotes[idxCard.symbol]?.found === false ? (
                      <div className="text-[10px] font-mono font-semibold text-muted-foreground mt-0.5">
                        not found in any market
                      </div>
                    ) : (
                      <div className={`text-[10px] font-mono font-semibold flex items-center gap-0.5 mt-0.5 ${
                        isPositive ? 'text-emerald-400' : 'text-rose-400'
                      }`}>
                        {isPositive ? <ArrowUpRight size={10} /> : <ArrowDownRight size={10} />}
                        {isPositive ? '+' : ''}{idxCard.changePercent}%
                      </div>
                    )}
                    {pinned?.found && (
                       <div className="text-[9px] font-mono text-muted-foreground/70 mt-1 truncate" title={`Source: ${pinned.source || 'db'} · ${pinned.updatedAt ? new Date(pinned.updatedAt).toLocaleString() : ''}`}>
                        {pinned.marketId || pinned.currency} · {pinned.updatedAt ? `updated ${timeAgo(pinned.updatedAt)}` : 'from database'}
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          ) : (
            <div className="col-span-full p-4 rounded-2xl glass-card-subtle border border-border/30 text-center text-xs text-muted-foreground">
              {stripMode === 'custom'
                ? 'No pinned symbols yet � click Customize above and type any symbol from any market (e.g. AAPL, OGDC, BTC).'
                : 'Nothing to show for this market yet.'}
            </div>
          )}
        </div>
      </div>
      )}

      {/* Split: Sectors Overview & Gainers/Losers */}
      {sectionVisible('sectors') && sectionVisible('shifters') && (
      <div className="grid lg:grid-cols-3 gap-6 animate-fade-in-up [animation-delay:200ms]">
        {sectionVisible('sectors') && (
        <div className="lg:col-span-2 p-5 rounded-2xl glass-card border border-white/10 dark:border-white/5 flex flex-col">
          <div className="flex items-center gap-2 mb-4">
            <Layers className="text-primary w-5 h-5" />
            <h2 className="font-serif text-lg font-semibold tracking-tight text-foreground">Sectors Daily Return Breakdown</h2>
            <button
              onClick={() => toggleSection('sectors')}
              className="ml-auto text-[10px] font-bold text-muted-foreground hover:text-rose-400 uppercase tracking-wider cursor-pointer transition-colors"
              title="Hide this section"
            >
              Hide
            </button>
          </div>

          <div className="grid md:grid-cols-2 gap-4 flex-1">
            {loadingDashboard ? (
              <div className="col-span-full flex items-center justify-center py-6">
                <TableLoading pct={45} label="loading sectors" />
              </div>
            ) : sectorPerformance.length > 0 ? (
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
            ) : (
              <div className="col-span-full flex items-center justify-center py-6 text-xs text-muted-foreground/70 font-mono">
                No sector data available for this market yet.
              </div>
            )}
          </div>
        </div>
        )}

        {/* Top Gainers & Losers Tabbed Split Pane */}
        <div className="p-5 rounded-2xl glass-card border border-white/10 dark:border-white/5 flex flex-col">
          <div className="flex items-center justify-between mb-4 border-b border-border/20 pb-2">
            <div className="flex items-center gap-2">
              <Award className="text-primary w-5 h-5" />
              <h2 className="font-serif text-base font-semibold tracking-tight">Market Shifters</h2>
            </div>
            <button
              onClick={() => toggleSection('shifters')}
              className="text-[10px] font-bold text-muted-foreground hover:text-rose-400 uppercase tracking-wider cursor-pointer transition-colors"
              title="Hide this section"
            >
              Hide
            </button>
          </div>

          <div className="grid grid-cols-2 gap-4 h-full">
            {loadingDashboard ? (
              <div className="col-span-full flex items-center justify-center py-6">
                <TableLoading pct={45} label="loading shifters" />
              </div>
            ) : topGainers.length === 0 && topLosers.length === 0 ? (
              <div className="col-span-full flex items-center justify-center py-6 text-xs text-muted-foreground/70 font-mono">
                No shifter data available for this market yet.
              </div>
            ) : (
              <>
                {/* Gainers List */}
                <div className="space-y-2">
                  <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-widest flex items-center gap-1 mb-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Top Gainers
                  </span>
                  {topGainers.map(item => (
                    <div
                      key={item.symbol}
                      onClick={(e) => {
                        if (openInNewTab(item.symbol, e)) return;
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
                    <span className="w-1.5 h-1.5 rounded-full bg-rose-400" /> Top Losers
                  </span>
                  {topLosers.map(item => (
                    <div
                      key={item.symbol}
                      onClick={(e) => {
                        if (openInNewTab(item.symbol, e)) return;
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
      )}
      {/* Main Screening Tables Master-Detail Grid Container */}
      <div className="w-full">
        <div className="w-full flex flex-col">
          {/* Main Screening Tables Card */}
          <div className="p-6 md:p-8 rounded-3xl glass-card border border-white/10 dark:border-white/5 flex flex-col animate-fade-in-up [animation-delay:300ms] gap-6 shadow-2xl shadow-black/20">
            
            {/* Dynamic Warning Banner for Delayed/Fallback Data */}
            {dataSource === 'fallback' && (
              <div className="glass-card-subtle border border-emerald-500/10 rounded-2xl p-3.5 flex items-center justify-between animate-fade-in text-emerald-400">
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

            {/* DEMO badge � never present simulated data as live market data. */}
            {dataSource === 'demo' && (
              <div className="glass-card-subtle border border-amber-500/10 rounded-2xl p-3.5 flex items-center justify-between animate-fade-in text-amber-400">
                <div className="flex items-center gap-3">
                  <Info className="w-4 h-4 text-amber-400 shrink-0" />
                  <div className="text-xs font-semibold">
                    SIMULATED DATA � these are demo values, not live market prices. Import a universe or enable the scraper to load real data.
                  </div>
                </div>
                <span className="text-[9px] bg-amber-500/15 px-2 py-0.5 rounded font-mono font-bold">DEMO</span>
              </div>
            )}
        
        {/* Tab Selection Row � market chip left, back button right */}
        <div className="flex items-center justify-between border-b border-border/15 pb-2 mb-1 flex-wrap gap-2">
          <div className="flex items-center gap-1.5 bg-accent/30 p-1.5 rounded-3xl overflow-x-auto max-w-full scrollbar-none flex-nowrap shrink-0 w-full md:w-auto">
            {screenerTab === 'crypto' ? (
              <span className="px-4 py-2 rounded-3xl text-xs font-bold text-primary flex items-center gap-1.5">
                <Coins className="w-3.5 h-3.5" /> Global Crypto
              </span>
            ) : screenerTab === 'markets' ? (
              <span className="px-4 py-2 rounded-3xl text-xs font-bold text-primary flex items-center gap-1.5">
                <Globe className="w-3.5 h-3.5" /> Global Market
              </span>
            ) : screenerTab === 'forex' ? (
              <span className="px-4 py-2 rounded-3xl text-xs font-bold text-primary flex items-center gap-1.5">
                <Globe className="w-3.5 h-3.5" /> Forex
              </span>
            ) : screenerTab === 'commodities' ? (
              <span className="px-4 py-2 rounded-3xl text-xs font-bold text-primary flex items-center gap-1.5">
                <Coins className="w-3.5 h-3.5" /> Commodities
              </span>
            ) : (
              <TabBar
                className="mb-0"
                items={[
                  {
                    id: 'stocks',
                    label: 'Stocks',
                    icon: TrendingUp,
                    active: screenerTab === 'stocks' && (filterType === 'All' || filterType === 'Stock'),
                  },
                  { id: 'etfs', label: 'ETFs', icon: Briefcase, active: screenerTab === 'etfs' },
                  { id: 'funds', label: 'Mutual Funds', icon: Layers, active: screenerTab === 'funds' },
                  {
                    id: 'reits',
                    label: 'REITs',
                    icon: Building2,
                    active: screenerTab === 'stocks' && filterType === 'REIT',
                  },
                  {
                    id: 'bonds',
                    label: 'Bonds',
                    icon: Coins,
                    active: screenerTab === 'stocks' && filterType === 'Listed Debt',
                  },
                ]}
                onChange={(id) => {
                  if (id === 'reits') { handleTabChange('stocks'); setFilterType('REIT'); }
                  else if (id === 'bonds') { handleTabChange('stocks'); setFilterType('Listed Debt'); }
                  else handleTabChange(id as 'stocks' | 'etfs' | 'funds');
                }}
              />
            )}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {loadingApi && <span className="text-[10px] text-muted-foreground/80 animate-pulse bg-accent/20 px-2.5 py-1 rounded-xl font-mono">Syncing Exchange...</span>}
            {screenerTab !== 'markets' && (
              <button
                onClick={() => setSectionsOpen(o => !o)}
                className={`inline-flex items-center gap-1.5 text-[10px] font-bold tracking-wider border rounded-xl px-2.5 py-1.5 transition-all cursor-pointer shrink-0 uppercase ${
                  sectionsOpen
                    ? 'text-primary bg-primary/10 border-primary/40'
                    : hiddenSections.length > 0
                      ? 'text-emerald-400/90 border-emerald-500/30 bg-emerald-500/5 hover:bg-emerald-500/10'
                      : 'text-muted-foreground border-border/40 bg-accent/30 hover:bg-accent/60'
                }`}
                title="Show / hide tables and sections"
              >
                <Eye size={12} /> {hiddenSections.length > 0 ? `${hiddenSections.length} Hidden` : 'Sections'}
              </button>
            )}
            {screenerTab !== 'markets' && (
              <button
                onClick={() => handleMarketSelect('GLOBAL')}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-primary border border-border/40 hover:border-primary/40 bg-accent/30 hover:bg-accent/60 rounded-xl px-3 py-1.5 transition-all cursor-pointer shrink-0"
              >
                <ArrowLeft size={13} /> Back to Market Screener
              </button>
            )}
          </div>
        </div>

        {/* Hidden-sections manager � lists every table/section with a toggle */}
        {sectionsOpen && (
          <div className="mb-3 p-3 sm:p-4 rounded-xl bg-background border border-border shadow-lg w-full animate-fade-in-up">
            <p className="text-[9px] uppercase font-bold text-muted-foreground/70 tracking-wider mb-2">Tables &amp; sections � click to show/hide</p>
            <div className="flex flex-wrap gap-1.5">
              {(Object.keys(SECTION_LABELS) as SectionKey[]).map(key => {
                const hidden = hiddenSections.includes(key);
                return (
                  <button
                    key={key}
                    onClick={() => toggleSection(key)}
                    className={`px-2.5 py-1.5 rounded-lg text-[11px] font-bold transition-all cursor-pointer border ${
                      hidden
                        ? 'border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/10'
                        : 'border-border/40 text-muted-foreground hover:bg-accent/40'
                    }`}
                    title={hidden ? `Show ${SECTION_LABELS[key]}` : `Hide ${SECTION_LABELS[key]}`}
                  >
                    {hidden ? <ArrowRight className="inline w-3 h-3" /> : <ChevronDown className="inline w-3 h-3" />}{SECTION_LABELS[key]}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Dedicated SPACIOUS Filter Action Bar - Solves Congestion */}
        <div className="flex items-center justify-between glass-card-subtle border border-border/20 rounded-3xl p-4 md:p-5 flex-wrap gap-4">
          {screenerTab === 'stocks' && (
            <div className="flex items-center gap-3 w-full flex-nowrap overflow-x-auto scrollbar-none py-0.5">
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
              {/* Search Input */}
              <div className="relative flex-1 min-w-[160px]">
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
              <div className="relative w-[140px] shrink-0">
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
                <div className="relative w-[180px] shrink-0">
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
          )}

          {screenerTab === 'crypto' && (
            <div className="flex items-center gap-3 w-full flex-nowrap overflow-x-auto scrollbar-none py-0.5">
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
              {/* Search Input */}
              <div className="relative flex-1 min-w-[200px]">
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
              <div className="relative w-[150px] shrink-0">
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
                <div className="relative w-[170px] shrink-0">
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
          )}

          {screenerTab === 'etfs' && (
            <div className="flex items-center gap-3 w-full flex-nowrap overflow-x-auto scrollbar-none py-0.5">
              <span className="text-xs font-bold text-foreground font-serif shrink-0">ETF Directory</span>
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
              <div className="relative flex-1 min-w-[200px]">
                <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground w-4 h-4" />
                <input
                  type="text"
                  placeholder="Search ETFs..."
                  value={etfSearch}
                  onChange={e => setEtfSearch(e.target.value)}
                  className="w-full bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-10 pr-4 py-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary placeholder:text-muted-foreground/50 transition-all font-mono"
                />
              </div>
              <div className="relative w-[150px] shrink-0">
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
          )}

          {screenerTab === 'funds' && (
            <div className="flex items-center gap-3 w-full flex-nowrap overflow-x-auto scrollbar-none py-0.5">
              <span className="text-xs font-bold text-foreground font-serif shrink-0">Mutual Funds</span>
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
              <div className="relative flex-1 min-w-[200px]">
                <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground w-4 h-4" />
                <input
                  type="text"
                  placeholder="Search Funds..."
                  value={fundSearch}
                  onChange={e => setFundSearch(e.target.value)}
                  className="w-full bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-10 pr-4 py-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary placeholder:text-muted-foreground/50 transition-all font-mono"
                />
              </div>
              <div className="relative w-[170px] shrink-0">
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
          )}

          {screenerTab === 'dividend_stocks' && (
            <div className="flex items-center gap-3 w-full flex-nowrap overflow-x-auto scrollbar-none py-0.5">
              <span className="text-xs font-bold text-foreground font-serif shrink-0">High Dividend Yield Stocks</span>
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
              <div className="relative flex-1 min-w-[200px]">
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
            <div className="flex items-center gap-3 w-full flex-nowrap overflow-x-auto scrollbar-none py-0.5">
              <span className="text-xs font-bold text-foreground font-serif shrink-0">Select a Market</span>
              <div className="relative flex-1 min-w-[200px]">
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
          )}

        {screenerTab === 'forex' && sectionVisible('table_forex') && (
            <div className="flex items-center gap-3 w-full flex-nowrap overflow-x-auto scrollbar-none py-0.5">
              <span className="text-xs font-bold text-foreground font-serif shrink-0">Forex Pairs</span>
              <span className="text-[10px] text-muted-foreground font-mono shrink-0 hidden md:inline">live from Yahoo Finance</span>
              <div className="relative flex-1 min-w-[160px]">
                <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground w-4 h-4" />
                <input
                  type="text"
                  placeholder="Search pairs e.g. EUR, PKR..."
                  value={forexSearch}
                  onChange={e => setForexSearch(e.target.value)}
                  className="w-full bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-10 pr-4 py-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary placeholder:text-muted-foreground/50 transition-all font-mono"
                />
              </div>
              {/* Preference filters */}
              <div className="relative w-[130px] shrink-0">
                <select
                  value={forexChange}
                  onChange={e => setForexChange(e.target.value)}
                  className="w-full appearance-none bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-3.5 pr-9 py-2.5 text-xs font-semibold text-foreground focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer transition-all"
                >
                  <option value="All">All Movers</option>
                  <option value="Gainers">Gainers only</option>
                  <option value="Losers">Losers only</option>
                  <option value="Flat">Flat / no data</option>
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground w-3.5 h-3.5 pointer-events-none" />
              </div>
              <div className="relative w-[150px] shrink-0">
                <select
                  value={forexCurrency}
                  onChange={e => setForexCurrency(e.target.value)}
                  className="w-full appearance-none bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-3.5 pr-9 py-2.5 text-xs font-semibold text-foreground focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer transition-all"
                >
                  <option value="All">All Currencies</option>
                  {Array.from(new Set(forexPairs.flatMap(p => [p.base, p.quote]))).sort().map((cur) => (
                    <option key={cur} value={cur}>{cur}</option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground w-3.5 h-3.5 pointer-events-none" />
              </div>
            </div>
          )}

          {screenerTab === 'commodities' && (
            <div className="flex items-center gap-3 w-full flex-nowrap overflow-x-auto scrollbar-none py-0.5">
              <span className="text-xs font-bold text-foreground font-serif shrink-0">Commodities</span>
              <span className="text-[10px] text-muted-foreground font-mono shrink-0 hidden md:inline">live from Yahoo Finance</span>
              <div className="relative flex-1 min-w-[160px]">
                <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground w-4 h-4" />
                <input
                  type="text"
                  placeholder="Search commodities e.g. Gold, Oil..."
                  value={commoditySearch}
                  onChange={e => setCommoditySearch(e.target.value)}
                  className="w-full bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-10 pr-4 py-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary placeholder:text-muted-foreground/50 transition-all font-mono"
                />
              </div>
              {/* Preference filters */}
              <div className="relative w-[130px] shrink-0">
                <select
                  value={commodityChange}
                  onChange={e => setCommodityChange(e.target.value)}
                  className="w-full appearance-none bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-3.5 pr-9 py-2.5 text-xs font-semibold text-foreground focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer transition-all"
                >
                  <option value="All">All Movers</option>
                  <option value="Gainers">Gainers only</option>
                  <option value="Losers">Losers only</option>
                  <option value="Flat">Flat / no data</option>
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground w-3.5 h-3.5 pointer-events-none" />
              </div>
              <div className="relative w-[150px] shrink-0">
                <select
                  value={commodityCategory}
                  onChange={e => setCommodityCategory(e.target.value)}
                  className="w-full appearance-none bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl pl-3.5 pr-9 py-2.5 text-xs font-semibold text-foreground focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer transition-all"
                >
                  <option value="All">All Categories</option>
                  <option value="Energy">Energy</option>
                  <option value="Metals">Metals</option>
                  <option value="Agriculture">Agriculture</option>
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground w-3.5 h-3.5 pointer-events-none" />
              </div>
            </div>
          )}
        </div>

        {/* Advanced Filters Panel - Clean, organized layout */}
        {screenerTab === 'stocks' && showAdvancedFilters && (
          <div className="w-full glass-card border border-border/30 rounded-3xl p-4 md:p-5 animate-fade-in text-xs shadow-lg">
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
                    <option value="Large">Large ($10B�$100B)</option>
                    <option value="Mid">Mid ($2B�$10B)</option>
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
          <div className="w-full glass-card border border-border/30 rounded-3xl p-4 md:p-5 animate-fade-in text-xs shadow-lg">
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
                    <option value="Large">Large ($10B�$100B)</option>
                    <option value="Mid">Mid ($2B�$10B)</option>
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
          <div className="w-full glass-card border border-border/30 rounded-3xl p-4 md:p-5 animate-fade-in text-xs shadow-lg">
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
          <div className="w-full glass-card border border-border/30 rounded-3xl p-4 md:p-5 animate-fade-in text-xs shadow-lg">
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
          <div className="w-full glass-card border border-border/30 rounded-3xl p-4 md:p-5 animate-fade-in text-xs shadow-lg">
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



        {/* Global Markets overview � fully customizable: layout, countries, columns */}
        {/* Hybrid load indicator: skeletons cover first paint; this ASCII
            dot-grid bar shows live progress on top of existing data during
            loads/refreshes so users always see that data is coming in. */}
        {tableLoader.active && (
          <TableLoading pct={tableLoader.pct} label={tableLoader.label} />
        )}

        {screenerTab === 'markets' && (() => {
          const col = gmConfig.columns;
          const gridClass = gmConfig.layout === 'focus'
            ? 'grid-cols-1'
            : gmConfig.layout === 'comfortable'
              ? 'grid-cols-1 lg:grid-cols-2'
              : 'grid-cols-1 lg:grid-cols-2 xl:grid-cols-3';
          // Per-market stock processing: movers filter ? sort ? page size.
          const processStocks = (stocks: OverviewGroup['stocks']) => {
            let list = [...stocks];
            if (gmConfig.movers === 'gainers') list = list.filter(s => s.changePct > 0);
            else if (gmConfig.movers === 'losers') list = list.filter(s => s.changePct < 0);
            switch (gmConfig.sortBy) {
              case 'change': list.sort((a, b) => b.changePct - a.changePct); break;
              case 'price': list.sort((a, b) => b.price - a.price); break;
              case 'name': list.sort((a, b) => a.name.localeCompare(b.name)); break;
              default: list.sort((a, b) => (b.marketCap || 0) - (a.marketCap || 0));
            }
            return list.slice(0, gmConfig.rows);
          };
          const groups: OverviewGroup[] = gmConfig.countries
            ? globalOverview.filter(g => gmConfig.countries!.includes(g.id))
            : [...globalOverview];
          // Default card order for the ordering buttons in the config panel
          // (countries in load order, then the special cards).
          const cardIdBaseOrder: string[] = [
            ...globalOverview.map((g) => g.id),
            'FOREX',
            'COMMODITIES',
          ];
          if (gmConfig.groupOrder === 'movers') {
            const avgChange = (g: OverviewGroup) => {
              const rows = processStocks(g.stocks);
              return rows.length ? rows.reduce((acc, s) => acc + s.changePct, 0) / rows.length : -Infinity;
            };
            groups.sort((a, b) => avgChange(b) - avgChange(a));
          }
          // Manual drag order wins over the automatic group ordering. The
          // saved order spans ALL cards � country ids plus the special FOREX
          // and COMMODITIES cards � so dragging any card persists. Hidden
          // cards (Forex/Commodities via section toggles) are dropped here.
          const cardOrder: string[] = [
            ...groups.map((g) => g.id),
            ...(sectionVisible('table_forex') ? ['FOREX'] : []),
            ...(sectionVisible('table_commodities') ? ['COMMODITIES'] : []),
          ];
          if (gmConfig.order && gmConfig.order.length > 0) {
            const idx = (id: string) => {
              const i = gmConfig.order!.indexOf(id);
              return i === -1 ? Number.MAX_SAFE_INTEGER : i;
            };
            cardOrder.sort((a, b) => idx(a) - idx(b));
          }
          const anyColumn = col.ticker || col.name || col.price || col.change || col.cap;
          const rowPad = gmConfig.dense ? 'py-1' : 'py-2';
          return (
            <div className="w-full">
              <div className="flex items-center justify-between gap-3 mb-3 px-1">
                <span className="flex items-center gap-2 min-w-0">
                  <Globe className="text-primary w-4 h-4 shrink-0" />
                  <span className="text-xs font-bold text-foreground uppercase tracking-wider font-mono">Global Markets Overview</span>
                  <span className="text-[10px] text-muted-foreground font-mono hidden md:inline">
                    {groups.length} markets � top {gmConfig.rows} by market cap � local currency
                  </span>
                </span>
                <button
                  onClick={() => setGmConfigOpen(o => !o)}
                  className={`flex items-center gap-1.5 text-xs font-bold tracking-wider border rounded-lg px-3.5 py-2 transition-all cursor-pointer shrink-0 ${
                    gmConfigOpen
                      ? 'text-primary bg-primary/10 border-primary/40'
                      : 'text-muted-foreground hover:text-primary bg-accent/40 hover:bg-accent/70 border-border/40'
                  }`}
                  title="Customize this overview"
                >
                  <Sliders size={14} /> Customize
                </button>
              </div>

              {/* Inline config panel � expands in flow, pushes content down */}
              {gmConfigOpen && (
                <div className="mb-3 p-3 sm:p-4 rounded-xl glass-card border border-white/10 dark:border-white/5 shadow-lg w-full max-w-full overflow-hidden animate-fade-in-up space-y-4">
                  <div className="flex items-center justify-between">
                    <p className="text-[10px] font-bold text-foreground uppercase tracking-wider">Overview Preferences</p>
                    <button
                      onClick={() => applyGmConfig(GM_DEFAULTS)}
                      className="text-[10px] font-bold text-muted-foreground hover:text-rose-400 uppercase tracking-wider cursor-pointer transition-colors"
                    >
                      Reset to defaults
                    </button>
                  </div>
                  {/* Layout */}
                  <div>
                    <p className="text-[9px] uppercase font-bold text-muted-foreground/70 tracking-wider mb-1.5">Layout <span className="normal-case font-medium text-muted-foreground/60">� drag any table by its header to reorder</span></p>
                    <div className="flex flex-wrap gap-1.5">
                      {([
                        ['compact', 'Compact (3 cols)'],
                        ['comfortable', 'Comfortable (2 cols)'],
                        ['focus', 'Focus (1 col)'],
                      ] as [GmLayout, string][]).map(([l, label]) => (
                        <button
                          key={l}
                          onClick={() => applyGmConfig({ layout: l })}
                          className={`px-2.5 py-1.5 rounded-lg text-[11px] font-bold transition-all cursor-pointer border whitespace-nowrap ${
                            gmConfig.layout === l ? 'bg-primary/15 text-primary border-primary/40' : 'text-muted-foreground border-border/40 hover:bg-accent/40'
                          }`}
                        >
                          {label}
                        </button>
                      ))}
                      <span className="mx-2 w-px self-stretch bg-border/60" aria-hidden />
                      <span className="flex items-center gap-1.5">
                        <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">Rows:</span>
                        {[3, 5, 10].map(n => (
                          <button
                            key={n}
                            onClick={() => applyGmConfig({ rows: n })}
                            className={`px-2 py-1 rounded-lg text-[11px] font-bold transition-all cursor-pointer border ${
                              gmConfig.rows === n ? 'bg-primary/15 text-primary border-primary/40' : 'text-muted-foreground border-border/40 hover:bg-accent/40'
                            }`}
                          >
                            {n}
                          </button>
                        ))}
                      </span>
                    </div>
                  </div>

                  {/* Columns � toggle visibility + reorder (left/right) */}
                  <div>
                    <p className="text-[9px] uppercase font-bold text-muted-foreground/70 tracking-wider mb-1.5">Columns <span className="normal-case font-medium text-muted-foreground/60">use drag to choose what shows first</span></p>
                    <div className="flex flex-wrap gap-1.5">
                      {(gmConfig.columnOrder ?? GM_COLUMN_ORDER).map((key, idx, arr) => (
                        <span
                          key={key}
                          className={`inline-flex items-center rounded-lg border transition-all ${
                            col[key] ? 'bg-primary/10 border-primary/40' : 'bg-transparent border-border/40 opacity-60'
                          }`}
                        >
                          <button
                            onClick={() => applyGmConfig({ columns: { ...col, [key]: !col[key] } })}
                            className={`pl-2.5 pr-1.5 py-1.5 text-[11px] font-bold transition-all cursor-pointer rounded-l-lg ${
                              col[key] ? 'text-primary' : 'text-muted-foreground hover:text-foreground'
                            }`}
                            title={col[key] ? `Hide ${GM_COLUMN_LABELS[key]}` : `Show ${GM_COLUMN_LABELS[key]}`}
                          >
                            {GM_COLUMN_LABELS[key]}
                          </button>
                          <button
                            onClick={() => moveGmColumn(key, -1)}
                            disabled={idx === 0}
                            className="px-1 py-1.5 text-[9px] text-muted-foreground hover:text-primary disabled:opacity-25 disabled:cursor-default cursor-pointer"
                            title="Move earlier"
                          >
                            ?
                          </button>
                          <button
                            onClick={() => moveGmColumn(key, 1)}
                            disabled={idx === arr.length - 1}
                            className="px-1 pr-2 py-1.5 text-[9px] text-muted-foreground hover:text-primary disabled:opacity-25 disabled:cursor-default cursor-pointer rounded-r-lg"
                            title="Move later"
                          >
                            ?
                          </button>
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Sorting & filters */}
                  <div>
                    <p className="text-[9px] uppercase font-bold text-muted-foreground/70 tracking-wider mb-1.5">Sorting &amp; Filters</p>
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                      <span className="flex items-center gap-1.5">
                        <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">Sort by</span>
                        {([
                          ['cap', 'Mkt Cap'],
                          ['change', 'Change %'],
                          ['price', 'Price'],
                          ['name', 'Name'],
                        ] as [GmConfig['sortBy'], string][]).map(([k, label]) => (
                          <button
                            key={k}
                            onClick={() => applyGmConfig({ sortBy: k })}
                            className={`px-2 py-1 rounded-lg text-[11px] font-bold transition-all cursor-pointer border ${
                              gmConfig.sortBy === k ? 'bg-primary/15 text-primary border-primary/40' : 'text-muted-foreground border-border/40 hover:bg-accent/40'
                            }`}
                          >
                            {label}
                          </button>
                        ))}
                      </span>
                      <span className="flex items-center gap-1.5">
                        <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">Show</span>
                        {([
                          ['all', 'All'],
                          ['gainers', 'Gainers'],
                          ['losers', 'Losers'],
                        ] as [GmConfig['movers'], string][]).map(([k, label]) => (
                          <button
                            key={k}
                            onClick={() => applyGmConfig({ movers: k })}
                            className={`px-2 py-1 rounded-lg text-[11px] font-bold transition-all cursor-pointer border ${
                              gmConfig.movers === k ? 'bg-primary/15 text-primary border-primary/40' : 'text-muted-foreground border-border/40 hover:bg-accent/40'
                            }`}
                          >
                            {label}
                          </button>
                        ))}
                      </span>
                    </div>
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mt-2">
                      <span className="flex items-center gap-1.5">
                        <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">Rows</span>
                        {([
                          ['dense', 'Dense'],
                          ['showRank', '# Rank'],
                          ['highlightExtremes', 'Highlight �'],
                        ] as [keyof GmConfig, string][]).map(([key, label]) => (
                          <button
                            key={String(key)}
                            onClick={() => applyGmConfig({ [key]: !gmConfig[key] } as Partial<GmConfig>)}
                            className={`px-2 py-1 rounded-lg text-[11px] font-bold transition-all cursor-pointer border ${
                              gmConfig[key] ? 'bg-primary/15 text-primary border-primary/40' : 'text-muted-foreground border-border/40 hover:bg-accent/40'
                            }`}
                          >
                            {label}
                          </button>
                        ))}
                      </span>
                      <span className="flex items-center gap-1.5">
                        <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">Order markets</span>
                        {([
                          ['az', 'A ? Z'],
                          ['movers', 'Movers first'],
                        ] as [GmConfig['groupOrder'], string][]).map(([k, label]) => (
                          <button
                            key={k}
                            onClick={() => applyGmConfig({ groupOrder: k })}
                            className={`px-2 py-1 rounded-lg text-[11px] font-bold transition-all cursor-pointer border ${
                              gmConfig.groupOrder === k ? 'bg-primary/15 text-primary border-primary/40' : 'text-muted-foreground border-border/40 hover:bg-accent/40'
                            }`}
                          >
                            {label}
                          </button>
                        ))}
                      </span>
                    </div>
                  </div>

                  {/* Countries � visibility + ordering (what shows first) */}
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <p className="text-[9px] uppercase font-bold text-muted-foreground/70 tracking-wider">Countries <span className="normal-case font-medium text-muted-foreground/60">drag to order, first is default</span></p>
                      <span className="flex gap-1.5">
                        <button onClick={() => applyGmConfig({ countries: null })} className="text-[10px] font-bold text-primary hover:underline cursor-pointer uppercase tracking-wider">All</button>
                        <button onClick={() => applyGmConfig({ countries: [] })} className="text-[10px] font-bold text-muted-foreground hover:text-rose-400 cursor-pointer uppercase tracking-wider">None</button>
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {(['FOREX', 'COMMODITIES'] as const).map(special => {
                        const active = sectionVisible(special === 'FOREX' ? 'table_forex' : 'table_commodities');
                        return (
                          <button
                            key={special}
                            onClick={() => toggleSection(special === 'FOREX' ? 'table_forex' : 'table_commodities')}
                            className={`px-2.5 py-1 rounded-full text-[10px] font-bold font-mono transition-all cursor-pointer border ${
                              active ? 'bg-primary/15 text-primary border-primary/40' : 'text-muted-foreground border-border/40 hover:bg-accent/40 opacity-60'
                            }`}
                            title={active ? `Hide ${special.toLowerCase()} card` : `Show ${special.toLowerCase()} card`}
                          >
                            {active ? '' : '? '}{special}
                          </button>
                        );
                      })}
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {globalOverview.map(g => {
                        const active = !gmConfig.countries || gmConfig.countries.includes(g.id);
                        return (
                          <span
                            key={g.id}
                            className={`inline-flex items-center rounded-full border transition-all ${
                              active ? 'bg-primary/10 border-primary/40' : 'bg-transparent border-border/40 opacity-60'
                            }`}
                          >
                            <button
                              onClick={() => {
                                const cur = new Set(gmConfig.countries ?? globalOverview.map(x => x.id));
                                if (cur.has(g.id)) cur.delete(g.id); else cur.add(g.id);
                                applyGmConfig({ countries: [...cur] });
                              }}
                              className={`pl-2.5 pr-1 py-1 text-[10px] font-bold font-mono transition-all cursor-pointer rounded-l-full ${
                                active ? 'text-primary' : 'text-muted-foreground hover:text-foreground'
                              }`}
                              title={active ? `Hide ${g.id}` : `Show ${g.id}`}
                            >
                              {g.id}
                            </button>
                            <button
                              onClick={() => applyGmConfig({ order: [g.id, ...(gmConfig.order ?? cardIdBaseOrder).filter((x) => x !== g.id)] })}
                              className="px-0.5 py-1 text-[9px] text-muted-foreground hover:text-primary cursor-pointer"
                              title={`${g.id} first`}
                            >
                              ?
                            </button>
                            <button
                              onClick={() => applyGmConfig({ order: reorderList(gmConfig.order ?? cardIdBaseOrder, g.id, -1) })}
                              className="px-0.5 py-1 text-[9px] text-muted-foreground hover:text-primary cursor-pointer"
                              title="Move up"
                            >
                              ?
                            </button>
                            <button
                              onClick={() => applyGmConfig({ order: reorderList(gmConfig.order ?? cardIdBaseOrder, g.id, 1) })}
                              className="px-0.5 pr-2 py-1 text-[9px] text-muted-foreground hover:text-primary cursor-pointer rounded-r-full"
                              title="Move down"
                            >
                              ?
                            </button>
                          </span>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}

              {loadingGlobalMarkets ? (
                <div className={`grid ${gridClass} gap-3`}>
                  {Array.from({ length: 6 }).map((_, i) => (
                    <div key={i} className="p-3.5 rounded-2xl glass-card border border-white/10 dark:border-white/5 flex items-center justify-center">
                      <TableLoading pct={Math.min(95, 15 + i * 13)} label="loading" />
                    </div>
                  ))}
                </div>
              ) : groups.length === 0 ? (
                <div className="py-10 text-center text-muted-foreground text-xs">
                  {globalOverview.length === 0
                    ? 'No priced markets yet - open a country screener and refresh prices to populate the overview.'
                    : 'All countries hidden � click Customize above and select the markets you want to see.'}
                </div>
              ) : (
                <div className={`relative grid ${gridClass} gap-3`}>
                  {cardOrder.map((cardId) => {
                    if (cardId === 'FOREX') {
                      return (
                        <div
                          key="FOREX"
                          data-gm-card
                          data-gm-id="FOREX"
                          className={cn(
                            'rounded-2xl glass-card border border-white/10 dark:border-white/5 overflow-hidden flex flex-col transition-all',
                            gmDragId === 'FOREX' && 'invisible'
                          )}
                        >
                          <div
                            data-gm-header
                            className="flex items-center justify-between gap-2 px-3.5 py-2.5 border-b border-white/5 hover:bg-accent/30 transition-colors select-none"
                          >
                            <span
                              data-gm-handle
                              role="button"
                              tabIndex={0}
                              aria-label="Drag Forex to reorder"
                              onMouseDown={(e) => beginGmDrag(e.clientX, e.clientY, e.button, e.currentTarget.closest('[data-gm-header]') as HTMLElement)}
                              className="flex items-center gap-2 min-w-0 cursor-grab active:cursor-grabbing text-left"
                              style={{ touchAction: 'none' }}
                              title="Drag to reorder"
                            >
                              <GripVertical size={14} className="text-muted-foreground/60 shrink-0" aria-hidden />
                              <span className="font-serif font-semibold text-sm text-foreground truncate">Forex</span>
                              <span className="text-[9px] text-muted-foreground font-mono truncate">Major Pairs</span>
                            </span>
                            <button
                              onClick={() => handleTabChange('forex')}
                              className="text-[9px] font-bold text-primary/90 uppercase tracking-wider shrink-0 hover:text-primary cursor-pointer bg-transparent border-none p-0"
                              title="Open Forex table"
                            >
                              Open <ArrowUpRight size={11} className="inline" />
                            </button>
                          </div>
                          <table className="w-full text-left text-[11px]">
                            <thead>
                              <tr className="text-muted-foreground/70 text-[9px] uppercase tracking-wider font-mono">
                                <th className={`${rowPad} pl-3.5 pr-2 font-semibold`}>Pair</th>
                                <th className={`${rowPad} px-2 text-right font-semibold`}>Rate (USD)</th>
                                <th className={`${rowPad} pr-3.5 pl-2 text-right font-semibold`}>Chg%</th>
                              </tr>
                            </thead>
                            <tbody>
                              {loadingForex ? (
                                <tr><td colSpan={3} className={`${rowPad} pl-3.5 pr-3.5 text-muted-foreground/60 italic`}>loading forex...</td></tr>
                              ) : filteredForex.length === 0 ? (
                                <tr><td colSpan={3} className={`${rowPad} pl-3.5 pr-3.5 text-muted-foreground/60 italic`}>No forex data</td></tr>
                              ) : filteredForex.slice(0, gmConfig.rows).map((pair) => {
                                const isPositive = pair.changePct >= 0;
                                return (
                                  <tr
                                    key={pair.symbol}
                                    onClick={(e) => handleSymbolClick(pair.symbol, pair.name, { price: pair.price, changePercent: pair.changePct }, e)}
                                    title="Ctrl+click to open in new tab"
                                    className="border-t border-white/5 transition-colors cursor-pointer hover:bg-primary/[0.04]"
                                  >
                                    <td className={`${rowPad} pl-3.5 pr-2 font-bold whitespace-nowrap text-foreground/80`}>
                                      {pair.symbol.replace('=X', '')}
                                    </td>
                                    <td className={`${rowPad} px-2 text-right font-mono font-semibold text-foreground whitespace-nowrap`}>
                                      {pair.found ? formatUsdPrice(pair.symbol, pair.price) : '�'}
                                    </td>
                                    <td className={`${rowPad} pr-3.5 pl-2 text-right whitespace-nowrap`}>
                                      <span className={`inline-block rounded px-1.5 font-mono font-bold ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                                        {pair.found ? `${isPositive ? '+' : ''}${pair.changePct.toFixed(2)}%` : '�'}
                                      </span>
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      );
                    }
                    if (cardId === 'COMMODITIES') {
                      return (
                        <div
                          key="COMMODITIES"
                          data-gm-card
                          data-gm-id="COMMODITIES"
                          className={cn(
                            'rounded-2xl glass-card border border-white/10 dark:border-white/5 overflow-hidden flex flex-col transition-all',
                            gmDragId === 'COMMODITIES' && 'invisible'
                          )}
                        >
                          <div
                            data-gm-header
                            className="flex items-center justify-between gap-2 px-3.5 py-2.5 border-b border-white/5 hover:bg-accent/30 transition-colors select-none"
                          >
                            <span
                              data-gm-handle
                              role="button"
                              tabIndex={0}
                              aria-label="Drag Commodities to reorder"
                              onMouseDown={(e) => beginGmDrag(e.clientX, e.clientY, e.button, e.currentTarget.closest('[data-gm-header]') as HTMLElement)}
                              className="flex items-center gap-2 min-w-0 cursor-grab active:cursor-grabbing text-left"
                              style={{ touchAction: 'none' }}
                              title="Drag to reorder"
                            >
                              <GripVertical size={14} className="text-muted-foreground/60 shrink-0" aria-hidden />
                              <span className="font-serif font-semibold text-sm text-foreground truncate">Commodities</span>
                              <span className="text-[9px] text-muted-foreground font-mono truncate">Gold � Silver � Oil</span>
                            </span>
                            <button
                              onClick={() => handleTabChange('commodities')}
                              className="text-[9px] font-bold text-primary/90 uppercase tracking-wider shrink-0 hover:text-primary cursor-pointer bg-transparent border-none p-0"
                              title="Open Commodities table"
                            >
                              Open <ArrowUpRight size={11} className="inline" />
                            </button>
                          </div>
                          <table className="w-full text-left text-[11px]">
                            <thead>
                              <tr className="text-muted-foreground/70 text-[9px] uppercase tracking-wider font-mono">
                                <th className={`${rowPad} pl-3.5 pr-2 font-semibold`}>Commodity</th>
                                <th className={`${rowPad} px-2 text-right font-semibold`}>Price (USD)</th>
                                <th className={`${rowPad} pr-3.5 pl-2 text-right font-semibold`}>Chg%</th>
                              </tr>
                            </thead>
                            <tbody>
                              {loadingCommodities ? (
                                <tr><td colSpan={3} className={`${rowPad} pl-3.5 pr-3.5 text-muted-foreground/60 italic`}>loading commodities...</td></tr>
                              ) : commodities.length === 0 ? (
                                <tr><td colSpan={3} className={`${rowPad} pl-3.5 pr-3.5 text-muted-foreground/60 italic`}>No commodity data</td></tr>
                              ) : commodities.slice(0, gmConfig.rows).map((c) => {
                                const isPositive = c.changePct >= 0;
                                return (
                                  <tr
                                    key={c.symbol}
                                    onClick={(e) => handleSymbolClick(c.symbol, c.name, { price: c.price, changePercent: c.changePct }, e)}
                                    title="Ctrl+click to open in new tab"
                                    className="border-t border-white/5 transition-colors cursor-pointer hover:bg-primary/[0.04]"
                                  >
                                    <td className={`${rowPad} pl-3.5 pr-2 font-bold whitespace-nowrap text-foreground/80`}>
                                      {c.name}
                                      <span className="ml-1.5 text-[8px] font-mono text-muted-foreground/60 font-semibold">{c.unit}</span>
                                    </td>
                                    <td className={`${rowPad} px-2 text-right font-mono font-semibold text-foreground whitespace-nowrap`}>
                                      {c.found ? formatUsdPrice(c.symbol, c.price) : '�'}
                                    </td>
                                    <td className={`${rowPad} pr-3.5 pl-2 text-right whitespace-nowrap`}>
                                      <span className={`inline-block rounded px-1.5 font-mono font-bold ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                                        {c.found ? `${isPositive ? '+' : ''}${c.changePct.toFixed(2)}%` : '�'}
                                      </span>
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      );
                    }
                    const g = groups.find((x) => x.id === cardId);
                    if (!g) return null;
                    const isDragged = gmDragId === g.id;
                    return (
                    <div
                      key={g.id}
                      data-gm-card
                      data-gm-id={g.id}
                      className={cn(
                        'rounded-2xl glass-card border border-white/10 dark:border-white/5 overflow-hidden flex flex-col transition-all',
                        isDragged && 'invisible'
                      )}
                    >
                      {/* Drag via the grip handle only; the rest of the header
                          is a click-to-open action (pointer cursor). */}
                      <div
                        data-gm-header
                        className="flex items-center justify-between gap-2 px-3.5 py-2.5 border-b border-white/5 hover:bg-accent/30 transition-colors select-none"
                      >
                        <span
                          data-gm-handle
                          role="button"
                          tabIndex={0}
                          aria-label={`Drag ${g.country} to reorder`}
                          onMouseDown={(e) => beginGmDrag(e.clientX, e.clientY, e.button, e.currentTarget.closest('[data-gm-header]') as HTMLElement)}
                          className="flex items-center gap-2 min-w-0 cursor-grab active:cursor-grabbing text-left"
                          style={{ touchAction: 'none' }}
                          title={`Drag to reorder ${g.country}`}
                        >
                          <GripVertical size={14} className="text-muted-foreground/60 shrink-0" aria-hidden />
                          <span className="font-serif font-semibold text-sm text-foreground truncate">{g.name || g.country}</span>
                          <span className="text-[9px] text-muted-foreground font-mono truncate">{g.exchange}</span>
                        </span>
                        <button
                          onClick={() => handleMarketSelect(g.isCrypto ? 'CRYPTO' : g.id)}
                          className="text-[9px] font-bold text-primary/90 uppercase tracking-wider shrink-0 hover:text-primary cursor-pointer bg-transparent border-none p-0"
                          title={`Open ${g.country} screener`}
                        >
                          Open <ArrowUpRight size={11} className="inline" />
                        </button>
                      </div>
                      {/* Country headline index — the market's own benchmark. */}
                      {g.index && (
                        <div className="flex items-center justify-between gap-2 px-3.5 py-1.5 border-b border-white/5 bg-white/[0.02]">
                          <span
                            className="min-w-0 truncate text-[10px] font-mono text-muted-foreground"
                            title={`${g.index.name} (${g.index.symbol})`}
                          >
                            {g.indexName || g.index.name}
                          </span>
                          <span className="shrink-0 font-mono text-[11px] font-semibold text-foreground whitespace-nowrap">
                            {priceWithCurrency(g.id, g.index.price)}
                            <span className={cn('ml-1.5', g.index.changePct >= 0 ? 'text-emerald-400' : 'text-rose-400')}>
                              {g.index.changePct >= 0 ? '+' : ''}{g.index.changePct.toFixed(2)}%
                            </span>
                          </span>
                        </div>
                      )}
                      {anyColumn && (() => {
                        const rows = processStocks(g.stocks);
                        const best = rows.length ? Math.max(...rows.map(r => r.changePct)) : 0;
                        const worst = rows.length ? Math.min(...rows.map(r => r.changePct)) : 0;
                        return (
                          <table className="w-full text-left text-[11px]">
                            <thead>
                              <tr className="text-muted-foreground/70 text-[9px] uppercase tracking-wider font-mono">
                                {(gmConfig.columnOrder ?? GM_COLUMN_ORDER).map((cKey) => {
                                  if (!col[cKey]) return null;
                                  if (cKey === 'ticker') return <th key={cKey} className={`${rowPad} pl-3.5 pr-2 font-semibold`}>Ticker</th>;
                                  if (cKey === 'name') return <th key={cKey} className={`${rowPad} px-2 font-semibold hidden sm:table-cell`}>Name</th>;
                                  if (cKey === 'price') return <th key={cKey} className={`${rowPad} px-2 text-right font-semibold`}>Price</th>;
                                  if (cKey === 'cap') return <th key={cKey} className={`${rowPad} px-2 text-right font-semibold hidden md:table-cell`}>Mkt Cap</th>;
                                  return <th key={cKey} className={`${rowPad} pr-3.5 pl-2 text-right font-semibold`}>Chg%</th>;
                                })}
                              </tr>
                            </thead>
                            <tbody>
                              {rows.length === 0 ? (
                                <tr><td colSpan={5} className={`${rowPad} pl-3.5 pr-3.5 text-muted-foreground/60 italic`}>
                                  No {gmConfig.movers === 'all' ? '' : gmConfig.movers} in top {gmConfig.rows}
                                </td></tr>
                              ) : rows.map((s, idx) => {
                                const isPositive = s.changePct >= 0;
                                const isBest = gmConfig.highlightExtremes && rows.length > 1 && s.changePct === best && best > 0;
                                const isWorst = gmConfig.highlightExtremes && rows.length > 1 && s.changePct === worst && worst < 0;
                                const isSelected = gmSelectedRow?.marketId === g.id && gmSelectedRow?.symbol === s.symbol;
                                return (
                                  <tr
                                    key={s.symbol}
                                    onClick={() => {
                                      setGmSelectedRow({ marketId: g.id, symbol: s.symbol });
                                      handleSymbolClick(s.symbol, s.name, { price: s.price, changePercent: s.changePct });
                                    }}
                                    className={cn(
                                      'border-t border-white/5 transition-colors cursor-pointer',
                                      isSelected
                                        ? 'bg-primary/[0.09] shadow-[inset_2px_0_0_0_#7aff78]'
                                        : 'hover:bg-primary/[0.04]'
                                    )}
                                  >
                                    {(gmConfig.columnOrder ?? GM_COLUMN_ORDER).map((cKey) => {
                                      if (!col[cKey]) return null;
                                      if (cKey === 'ticker') return (
                                        <td key={cKey} className={`${rowPad} pl-3.5 pr-2 font-bold whitespace-nowrap ${isSelected ? 'text-foreground' : 'text-foreground/80'}`}>
                                          {gmConfig.showRank && <span className="text-muted-foreground/60 font-mono font-semibold mr-1">{idx + 1}.</span>}
                                          {/* Always the raw ticker symbol � this is what
                                              resolves on TradingView. Name lives in the
                                              tooltip + the Name column. */}
                                          <span className="font-mono" title={`${s.name} (${s.symbol})`}>{s.symbol}</span>
                                        </td>
                                      );
                                      if (cKey === 'name') return (
                                        <td key={cKey} className={`${rowPad} px-2 truncate max-w-[110px] hidden sm:table-cell ${isSelected ? 'text-foreground' : 'text-foreground/75'}`}>{s.name}</td>
                                      );
                                      if (cKey === 'price') return (
                                        <td key={cKey} className={`${rowPad} px-2 text-right font-mono font-semibold text-foreground whitespace-nowrap`}>
                                          {priceWithCurrency(g.id, s.price)}
                                        </td>
                                      );
                                      if (cKey === 'cap') return (
                                        <td key={cKey} className={`${rowPad} px-2 text-right font-mono ${isSelected ? 'text-foreground/90' : 'text-foreground/75'} hidden md:table-cell whitespace-nowrap`}>{fmtCap(s.marketCap)}</td>
                                      );
                                      return (
                                        <td key={cKey} className={`${rowPad} pr-3.5 pl-2 text-right whitespace-nowrap`}>
                                          <span className={`inline-block rounded px-1.5 font-mono font-bold ${
                                            isSelected
                                              ? 'bg-primary text-black'
                                              : isBest ? 'bg-primary/15 text-primary' : isWorst ? 'bg-rose-500/10 text-rose-400' : isPositive ? 'text-emerald-400' : 'text-rose-400'
                                          }`}>
                                            {isPositive ? '+' : ''}{s.changePct.toFixed(2)}%
                                          </span>
                                        </td>
                                      );
                                    })}
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        );
                      })()}
                    </div>
                    );
                  })}
                  {/* Floating copy of the dragged table � follows the cursor via
                      direct DOM transform (ref), zero re-renders. Rendered through
                      a portal to document.body and ALWAYS mounted: an ancestor
                      with backdrop-blur / transform would otherwise become the
                      containing block for position:fixed and the ghost would fly
                      off away from the mouse. visibility:hidden hides it when not
                      dragging so the ref is always available on drag start. */}
                  {createPortal(
                    <div
                      ref={gmFloatRef}
                      className="fixed z-[70] pointer-events-none rounded-2xl overflow-hidden bg-[#0e0e0e] dark:bg-[#0e0e0e] text-foreground shadow-[0_30px_80px_rgba(0,0,0,0.6)] will-change-transform"
                      style={{
                        left: 0,
                        top: 0,
                        width: gmDragWidth || 320,
                        visibility: gmDragId ? 'visible' : 'hidden',
                        transform: 'translate3d(-9999px, -9999px, 0) translate(-50%, -50%) scale(1.02)',
                      }}
                    >
                      {gmDragId && (() => {
                        const src = globalOverview.find(x => x.id === gmDragId);
                        if (gmDragId === 'FOREX') {
                          const rows = filteredForex.slice(0, Math.min(3, gmConfig.rows));
                          return (
                            <>
                              <div className="flex items-center justify-between gap-2 px-3.5 py-2.5 border-b border-white/10">
                                <span className="flex items-center gap-2 min-w-0">
                                  <GripVertical size={14} className="text-primary shrink-0" aria-hidden />
                                  <span className="font-serif font-semibold text-sm text-foreground truncate">Forex</span>
                                  <span className="text-[9px] text-muted-foreground font-mono truncate">Major Pairs</span>
                                </span>
                                <span className="text-[9px] font-bold text-primary uppercase tracking-wider shrink-0">moving�</span>
                              </div>
                              <div className="px-3.5 py-2.5 space-y-1.5">
                                {rows.map(pair => (
                                  <div key={pair.symbol} className="flex items-center justify-between gap-2 text-[11px]">
                                    <span className="font-mono font-bold text-foreground/80 truncate">{pair.symbol.replace('=X', '')}</span>
                                    <span className="font-mono text-foreground/80">{pair.found ? formatUsdPrice(pair.symbol, pair.price) : '�'}</span>
                                  </div>
                                ))}
                                <div className="pt-1 text-[9px] font-mono text-muted-foreground/70">{filteredForex.length} pairs � drop to place</div>
                              </div>
                            </>
                          );
                        }
                        if (gmDragId === 'COMMODITIES') {
                          const rows = commodities.slice(0, Math.min(3, gmConfig.rows));
                          return (
                            <>
                              <div className="flex items-center justify-between gap-2 px-3.5 py-2.5 border-b border-white/10">
                                <span className="flex items-center gap-2 min-w-0">
                                  <GripVertical size={14} className="text-primary shrink-0" aria-hidden />
                                  <span className="font-serif font-semibold text-sm text-foreground truncate">Commodities</span>
                                  <span className="text-[9px] text-muted-foreground font-mono truncate">Gold � Silver � Oil</span>
                                </span>
                                <span className="text-[9px] font-bold text-primary uppercase tracking-wider shrink-0">moving�</span>
                              </div>
                              <div className="px-3.5 py-2.5 space-y-1.5">
                                {rows.map(c => (
                                  <div key={c.symbol} className="flex items-center justify-between gap-2 text-[11px]">
                                    <span className="font-mono font-bold text-foreground/80 truncate">{c.name}</span>
                                    <span className="font-mono text-foreground/80">{c.found ? formatUsdPrice(c.symbol, c.price) : '�'}</span>
                                  </div>
                                ))}
                                <div className="pt-1 text-[9px] font-mono text-muted-foreground/70">{commodities.length} commodities � drop to place</div>
                              </div>
                            </>
                          );
                        }
                        if (!src) return null;
                        return (
                          <>
                            <div className="flex items-center justify-between gap-2 px-3.5 py-2.5 border-b border-white/10">
                              <span className="flex items-center gap-2 min-w-0">
                                <GripVertical size={14} className="text-primary shrink-0" aria-hidden />
                                <span className="font-serif font-semibold text-sm text-foreground truncate">{src.name || src.country}</span>
                                <span className="text-[9px] text-muted-foreground font-mono truncate">{src.exchange}</span>
                              </span>
                              <span className="text-[9px] font-bold text-primary uppercase tracking-wider shrink-0">moving�</span>
                            </div>
                            <div className="px-3.5 py-2.5 space-y-1.5">
                              {src.stocks.slice(0, Math.min(3, gmConfig.rows)).map(s => (
                                <div key={s.symbol} className="flex items-center justify-between gap-2 text-[11px]">
                                  <span className="font-mono font-bold text-foreground/80 truncate">{s.symbol}</span>
                                  <span className="font-mono text-foreground/80">{priceWithCurrency(src.id, s.price)}</span>
                                </div>
                              ))}
                              <div className="pt-1 text-[9px] font-mono text-muted-foreground/70">
                                {src.stocks.length} rows � drop to place
                              </div>
                            </div>
                          </>
                        );
                      })()}
                    </div>,
                    document.body
                  )}
                </div>
              )}
            </div>
          );
        })()}

        {screenerTab === 'forex' && sectionVisible('table_forex') && (
          <>
            <div className="w-full overflow-x-auto custom-scrollbar glass-card-subtle border border-white/10 dark:border-white/5 rounded-2xl shadow-md">
              <table className="w-full text-left border-collapse text-[11px]">
                <thead>
                  <tr className="border-b border-white/5 text-muted-foreground/80 text-[10px] uppercase tracking-wider font-mono font-semibold bg-white/[0.01]">
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground font-mono transition-colors whitespace-nowrap" onClick={() => toggleForexSort('symbol')}>
                      Pair {forexSortField === 'symbol' && (forexSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleForexSort('name')}>
                      Name {forexSortField === 'name' && (forexSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden sm:table-cell whitespace-nowrap" onClick={() => toggleForexSort('base')}>
                      Base {forexSortField === 'base' && (forexSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden sm:table-cell whitespace-nowrap" onClick={() => toggleForexSort('quote')}>
                      Quote {forexSortField === 'quote' && (forexSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleForexSort('price')}>
                      Rate (USD) {forexSortField === 'price' && (forexSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleForexSort('changePct')}>
                      Change % {forexSortField === 'changePct' && (forexSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-center whitespace-nowrap">AI Analyst</th>
                  </tr>
                </thead>
                <tbody>
                  {loadingForex ? (
                    <TableSkeleton cols={7} rows={8} />
                  ) : filteredForex.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="p-6 text-center text-muted-foreground font-medium whitespace-nowrap ">
                        No matching forex pairs found.
                      </td>
                    </tr>
                  ) : (
                    filteredForex.map((pair) => {
                      const isPositive = pair.changePct >= 0;
                      return (
                        <tr
                          key={pair.symbol}
                          className="hover:bg-accent/20 even:bg-accent/5 odd:bg-transparent transition-colors font-medium"
                        >
                          <td
                            onClick={(e) => handleSymbolClick(pair.symbol, pair.name, { price: pair.price, changePercent: pair.changePct }, e)}
                            title="Ctrl+click to open in new tab"
                            className="py-1 px-2 border border-border/30 font-bold font-mono text-foreground/80 hover:underline whitespace-nowrap cursor-pointer"
                          >
                            {pair.symbol.replace('=X', '')}
                          </td>
                          <td className="py-3 px-4 text-foreground/80 truncate max-w-[180px] whitespace-nowrap">{pair.name}</td>
                          <td className="py-3 px-4 text-foreground/75 hidden sm:table-cell whitespace-nowrap font-mono">{pair.base}</td>
                          <td className="py-3 px-4 text-foreground/75 hidden sm:table-cell whitespace-nowrap font-mono">{pair.quote}</td>
                          <td className="py-3 px-4 text-right font-mono font-bold text-foreground whitespace-nowrap">
                            {pair.found ? formatUsdPrice(pair.symbol, pair.price) : '�'}
                          </td>
                          <td className={cn(
                            "py-1 px-2 border border-border/30 text-right font-mono font-bold whitespace-nowrap",
                            isPositive ? 'text-emerald-400' : 'text-rose-400'
                          )}>
                            {pair.found ? `${isPositive ? '+' : ''}${pair.changePct.toFixed(2)}%` : '�'}
                          </td>
                          <td className="py-3 px-4 text-center whitespace-nowrap">
                            <Button
                              size="sm"
                              onClick={() => handleAction(pair.symbol)}
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
          </>
        )}

        {screenerTab === 'commodities' && sectionVisible('table_commodities') && (
          <>
            <div className="w-full overflow-x-auto custom-scrollbar glass-card-subtle border border-white/10 dark:border-white/5 rounded-2xl shadow-md">
              <table className="w-full text-left border-collapse text-[11px]">
                <thead>
                  <tr className="border-b border-white/5 text-muted-foreground/80 text-[10px] uppercase tracking-wider font-mono font-semibold bg-white/[0.01]">
                    <th className="py-3 px-4 whitespace-nowrap">Commodity</th>
                    <th className="py-3 px-4 whitespace-nowrap">Symbol</th>
                    <th className="py-3 px-4 hidden sm:table-cell whitespace-nowrap">Unit</th>
                    <th className="py-3 px-4 text-right whitespace-nowrap">Price (USD)</th>
                    <th className="py-3 px-4 text-right whitespace-nowrap">Change %</th>
                    <th className="py-3 px-4 text-center whitespace-nowrap">AI Analyst</th>
                  </tr>
                </thead>
                <tbody>
                  {loadingCommodities ? (
                    <TableSkeleton cols={6} rows={8} />
                  ) : filteredCommodities.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="p-6 text-center text-muted-foreground font-medium whitespace-nowrap ">
                        No commodity data found.
                      </td>
                    </tr>
                  ) : (
                    filteredCommodities.map((c) => {
                      const isPositive = c.changePct >= 0;
                      return (
                        <tr
                          key={c.symbol}
                          className="hover:bg-accent/20 even:bg-accent/5 odd:bg-transparent transition-colors font-medium"
                        >
                          <td
                            onClick={(e) => handleSymbolClick(c.symbol, c.name, { price: c.price, changePercent: c.changePct }, e)}
                            title="Ctrl+click to open in new tab"
                            className="py-1 px-2 border border-border/30 font-bold text-foreground/80 hover:underline whitespace-nowrap cursor-pointer"
                          >
                            {c.name}
                          </td>
                          <td className="py-3 px-4 font-mono text-foreground/75 whitespace-nowrap">{c.symbol}</td>
                          <td className="py-3 px-4 text-foreground/75 hidden sm:table-cell whitespace-nowrap font-mono">{c.unit}</td>
                          <td className="py-3 px-4 text-right font-mono font-bold text-foreground whitespace-nowrap">
                            {c.found ? formatUsdPrice(c.symbol, c.price) : '�'}
                          </td>
                          <td className={cn(
                            "py-1 px-2 border border-border/30 text-right font-mono font-bold whitespace-nowrap",
                            isPositive ? 'text-emerald-400' : 'text-rose-400'
                          )}>
                            {c.found ? `${isPositive ? '+' : ''}${c.changePct.toFixed(2)}%` : '�'}
                          </td>
                          <td className="py-3 px-4 text-center whitespace-nowrap">
                            <Button
                              size="sm"
                              onClick={() => handleAction(c.symbol)}
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
          </>
        )}

        {screenerTab === 'stocks' && sectionVisible('table_stocks') && (
          <>
            <div className="w-full overflow-x-auto custom-scrollbar glass-card-subtle border border-white/10 dark:border-white/5 rounded-2xl shadow-md">
              <table className="w-full text-left border-collapse text-[11px]">
                <thead>
                  <tr className="border-b border-white/5 text-muted-foreground/80 text-[10px] uppercase tracking-wider font-mono font-semibold bg-white/[0.01]">
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground font-mono transition-colors whitespace-nowrap" onClick={() => toggleStockSort('symbol')}>
                      Ticker {stockSortField === 'symbol' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('name')}>
                      Company {stockSortField === 'name' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden md:table-cell whitespace-nowrap" onClick={() => toggleStockSort('securityType')}>
                      Type {stockSortField === 'securityType' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden lg:table-cell whitespace-nowrap" onClick={() => toggleStockSort('industry')}>
                      Industry {stockSortField === 'industry' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden lg:table-cell whitespace-nowrap" onClick={() => toggleStockSort('country')}>
                      Country {stockSortField === 'country' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors hidden sm:table-cell whitespace-nowrap" onClick={() => toggleStockSort('marketCap')}>
                      Market Cap {stockSortField === 'marketCap' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors hidden sm:table-cell whitespace-nowrap" onClick={() => toggleStockSort('peRatio')}>
                      P/E {stockSortField === 'peRatio' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('price')}>
                      Price {stockSortField === 'price' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('changePercent')}>
                      Change {stockSortField === 'changePercent' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
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
                          onClick={(e) => handleSymbolClick(stock.symbol, stock.name, stock, e)}
                          className="border-b border-white/5 hover:bg-white/[0.02] transition-colors cursor-pointer group"
                        >
                          <td
                            onClick={(e) => {
                              e.stopPropagation();
                              handleSymbolClick(stock.symbol, stock.name, stock, e);
                            }}
                            title="Ctrl+click to open in new tab"
                            className="py-1 px-2 border border-border/30 font-bold font-mono text-foreground/80 hover:underline whitespace-nowrap"
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
                                <span className="text-[9px] text-muted-foreground/60 animate-pulse">⠹ fetching�</span>
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1.5">
                                {priceWithCurrency(stock.country || userCountry, stock.price)}
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
                              <span className="text-[9px] text-muted-foreground/60 animate-pulse">⠹</span>
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
                <div className="flex items-center gap-2 glass-card-subtle px-3 py-1.5 rounded-xl border border-border/30">
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

        {screenerTab === 'crypto' && sectionVisible('table_crypto') && (
          <>
            <div className="w-full overflow-x-auto custom-scrollbar glass-card-subtle border border-white/10 dark:border-white/5 rounded-2xl shadow-md">
              <table className="w-full text-left border-collapse text-[11px]">
                <thead>
                  <tr className="border-b border-white/5 text-muted-foreground/80 text-[10px] uppercase tracking-wider font-mono font-semibold bg-white/[0.01]">
                    <th className="py-3 px-4 text-center whitespace-nowrap cursor-pointer hover:text-foreground transition-colors" onClick={() => toggleStockSort('rank')}>
                      Rank {stockSortField === 'rank' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground font-mono transition-colors whitespace-nowrap" onClick={() => toggleStockSort('symbol')}>
                      Symbol {stockSortField === 'symbol' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('name')}>
                      Asset Name {stockSortField === 'name' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('sector')}>
                      Category {stockSortField === 'sector' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('price')}>
                      Price {stockSortField === 'price' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('changePercent')}>
                      24H Change {stockSortField === 'changePercent' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('marketCap')}>
                      Market Cap {stockSortField === 'marketCap' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('volume')}>
                      24H Volume {stockSortField === 'volume' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('circulatingSupply')}>
                      Circulating Supply {stockSortField === 'circulatingSupply' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('maxSupply')}>
                      Max Supply {stockSortField === 'maxSupply' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-center cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('ath')}>
                      ATH Distance {stockSortField === 'ath' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
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
                                  handleSymbolClick(stock.symbol, stock.name, stock, e);
                                }}
                                title="Ctrl+click to open in new tab"
                                className="py-2 px-2 border border-border/30 font-bold font-mono text-foreground/80 hover:underline whitespace-nowrap"
                              >
                                {stock.symbol}
                              </td>
                              <td
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleSymbolClick(stock.symbol, stock.name, stock, e);
                                }}
                                title="Ctrl+click to open in new tab"
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
                                    <span className="text-[9px] text-muted-foreground/60 animate-pulse">⠹ fetching�</span>
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center gap-1.5">
                                    {currencyFor('CRYPTO')}{formatCryptoPrice(stock.price)}
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
                                  <span className="text-[9px] text-muted-foreground/60 animate-pulse">⠹</span>
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
                                    <div className="flex flex-col gap-1 glass-card-subtle border border-border/20 rounded-xl p-3 min-w-[150px]">
                                      <span className="text-[9px] uppercase font-bold text-muted-foreground tracking-wider font-mono">Liquidity</span>
                                      <span className="text-xs font-mono font-bold text-foreground">24H Volume:</span>
                                      <span className="text-sm font-mono font-black text-primary">{stock.volume || 'N/A'}</span>
                                    </div>
                                    <div className="flex flex-col gap-1 glass-card-subtle border border-border/20 rounded-xl p-3 min-w-[180px]">
                                      <span className="text-[9px] uppercase font-bold text-muted-foreground tracking-wider font-mono">Supply Status</span>
                                      <span className="text-xs font-mono font-bold text-foreground">Circulating / Max:</span>
                                      <span className="text-xs font-mono text-foreground">{stock.circulatingSupply || 'N/A'} / {stock.maxSupply || 'N/A'}</span>
                                    </div>
                                    <div className="flex flex-col gap-1 glass-card-subtle border border-border/20 rounded-xl p-3 min-w-[150px]">
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
                <div className="flex items-center gap-2 glass-card-subtle px-3 py-1.5 rounded-xl border border-border/30">
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

        {screenerTab === 'etfs' && sectionVisible('table_etfs') && (
          <div>
            {apiEtfs.length === 0 && (
              <div className="glass-card-subtle border border-amber-500/10 rounded-2xl p-3 flex items-center gap-3 text-amber-400 mb-3">
                <Info className="w-4 h-4 shrink-0" />
                <span className="text-xs font-semibold flex-1">SIMULATED DATA � no ETF universe loaded in JDDS; showing a curated demo list, not live prices.</span>
                <span className="text-[9px] bg-amber-500/15 px-2 py-0.5 rounded font-mono font-bold">DEMO</span>
              </div>
            )}
          <div className="w-full overflow-x-auto custom-scrollbar glass-card-subtle border border-white/10 dark:border-white/5 rounded-2xl shadow-md">
            <table className="w-full text-left border-collapse text-[11px]">
              <thead>
                <tr className="border-b border-white/5 text-muted-foreground/80 text-[10px] uppercase tracking-wider font-mono font-semibold bg-white/[0.01]">
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground font-mono transition-colors whitespace-nowrap" onClick={() => toggleEtfSort('symbol')}>
                    Symbol {etfSortField === 'symbol' && (etfSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleEtfSort('name')}>
                    ETF Name {etfSortField === 'name' && (etfSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden sm:table-cell whitespace-nowrap" onClick={() => toggleEtfSort('category')}>
                    Category {etfSortField === 'category' && (etfSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleEtfSort('price')}>
                    Price {etfSortField === 'price' && (etfSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleEtfSort('changePercent')}>
                    Change % {etfSortField === 'changePercent' && (etfSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
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
                          onClick={(e) => handleSymbolClick(etf.symbol, etf.name, { marketCap: etf.aum, price: etf.price, changePercent: etf.changePercent, volume: etf.volume }, e)}
                          title="Ctrl+click to open in new tab"
                          className="py-1 px-2 border border-border/30 font-bold font-mono text-foreground/80 hover:underline whitespace-nowrap cursor-pointer"
                        >
                          {etf.symbol}
                        </td>
                        <td className="py-3 px-4 text-foreground/80 truncate max-w-[130px] whitespace-nowrap">{etf.name}</td>
                        <td className="py-3 px-4 text-foreground/75 hidden sm:table-cell whitespace-nowrap">{etf.category}</td>
                        <td className="py-3 px-4 text-right font-mono font-bold text-foreground whitespace-nowrap">{priceWithCurrency(userCountry, etf.price)}</td>
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
          </div>
        )}

        {screenerTab === 'funds' && sectionVisible('table_funds') && (
          <div>
            {apiFunds.length === 0 && (
              <div className="glass-card-subtle border border-amber-500/10 rounded-2xl p-3 flex items-center gap-3 text-amber-400 mb-3">
                <Info className="w-4 h-4 shrink-0" />
                <span className="text-xs font-semibold flex-1">SIMULATED DATA � no fund universe loaded in JDDS; showing a curated demo list, not live NAVs.</span>
                <span className="text-[9px] bg-amber-500/15 px-2 py-0.5 rounded font-mono font-bold">DEMO</span>
              </div>
            )}
          <div className="w-full overflow-x-auto custom-scrollbar glass-card-subtle border border-white/10 dark:border-white/5 rounded-2xl shadow-md">
            <table className="w-full text-left border-collapse text-[11px]">
              <thead>
                <tr className="border-b border-white/5 text-muted-foreground/80 text-[10px] uppercase tracking-wider font-mono font-semibold bg-white/[0.01]">
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground font-mono transition-colors whitespace-nowrap" onClick={() => toggleFundSort('symbol')}>
                    Symbol {fundSortField === 'symbol' && (fundSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleFundSort('name')}>
                    Fund Name {fundSortField === 'name' && (fundSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden sm:table-cell whitespace-nowrap" onClick={() => toggleFundSort('category')}>
                    Category {fundSortField === 'category' && (fundSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleFundSort('nav')}>
                    NAV {fundSortField === 'nav' && (fundSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleFundSort('changePercent')}>
                    1D Change % {fundSortField === 'changePercent' && (fundSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors hidden md:table-cell whitespace-nowrap" onClick={() => toggleFundSort('ytdReturn')}>
                    YTD Return % {fundSortField === 'ytdReturn' && (fundSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors hidden lg:table-cell whitespace-nowrap" onClick={() => toggleFundSort('expenseRatio')}>
                    Expense Ratio {fundSortField === 'expenseRatio' && (fundSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
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
                          onClick={(e) => handleSymbolClick(fund.symbol, fund.name, { marketCap: fund.aum, price: fund.nav, changePercent: fund.changePercent }, e)}
                          title="Ctrl+click to open in new tab"
                          className="py-1 px-2 border border-border/30 font-bold font-mono text-foreground/80 hover:underline whitespace-nowrap cursor-pointer"
                        >
                          {fund.symbol}
                        </td>
                        <td className="py-3 px-4 text-foreground/80 truncate max-w-[130px] whitespace-nowrap">{fund.name}</td>
                        <td className="py-3 px-4 text-foreground/75 hidden sm:table-cell whitespace-nowrap">{fund.category}</td>
                        <td className="py-3 px-4 text-right font-mono font-semibold text-foreground whitespace-nowrap">{priceWithCurrency(userCountry, fund.nav)}</td>
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
          </div>
        )}

        {screenerTab === 'dividend_stocks' && sectionVisible('table_dividend') && (
          <div>
            {/* Dividend stocks are a curated static list � never live prices. */}
            <div className="glass-card-subtle border border-amber-500/10 rounded-2xl p-3 flex items-center gap-3 text-amber-400 mb-3">
              <Info className="w-4 h-4 shrink-0" />
              <span className="text-xs font-semibold flex-1">SIMULATED DATA � dividend stock rows are a curated demo list, not live market prices.</span>
              <span className="text-[9px] bg-amber-500/15 px-2 py-0.5 rounded font-mono font-bold">DEMO</span>
            </div>
            <div className="w-full overflow-x-auto custom-scrollbar glass-card-subtle border border-white/10 dark:border-white/5 rounded-2xl shadow-md">
            <table className="w-full text-left border-collapse text-[11px]">
              <thead>
                <tr className="border-b border-white/5 text-muted-foreground/80 text-[10px] uppercase tracking-wider font-mono font-semibold bg-white/[0.01]">
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground font-mono transition-colors whitespace-nowrap" onClick={() => toggleDividendSort('symbol')}>
                    Symbol {dividendSortField === 'symbol' && (dividendSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleDividendSort('name')}>
                    Company Name {dividendSortField === 'name' && (dividendSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden sm:table-cell whitespace-nowrap" onClick={() => toggleDividendSort('dividendYield')}>
                    Dividend Yield {dividendSortField === 'dividendYield' && (dividendSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleDividendSort('price')}>
                    Price {dividendSortField === 'price' && (dividendSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleDividendSort('changePercent')}>
                    Change % {dividendSortField === 'changePercent' && (dividendSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
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
                          onClick={(e) => handleSymbolClick(dividendStock.symbol, dividendStock.name, { peRatio: dividendStock.peRatio, marketCap: dividendStock.marketCap, dividendYield: dividendStock.dividendYield, price: dividendStock.price, changePercent: dividendStock.changePercent, volume: dividendStock.volume }, e)}
                          title="Ctrl+click to open in new tab"
                          className="py-1 px-2 border border-border/30 font-bold font-mono text-foreground/80 hover:underline whitespace-nowrap cursor-pointer"
                        >
                          {dividendStock.symbol}
                        </td>
                        <td className="py-3 px-4 text-foreground/80 truncate max-w-[130px] whitespace-nowrap">{dividendStock.name}</td>
                        <td className="py-3 px-4 text-emerald-400 font-bold font-mono hidden sm:table-cell whitespace-nowrap">{dividendStock.dividendYield}</td>
                        <td className="py-3 px-4 text-right font-mono font-semibold text-foreground whitespace-nowrap">{priceWithCurrency(userCountry, dividendStock.price)}</td>
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
          fiftyTwoWeekHigh={selectedAnalysisStock.fiftyTwoWeekHigh}
          fiftyTwoWeekLow={selectedAnalysisStock.fiftyTwoWeekLow}
          eps={selectedAnalysisStock.eps}
          dayHigh={selectedAnalysisStock.dayHigh}
          dayLow={selectedAnalysisStock.dayLow}
          dayOpen={selectedAnalysisStock.dayOpen}
          previousClose={selectedAnalysisStock.previousClose}
          beta={selectedAnalysisStock.beta}
          dividendRate={selectedAnalysisStock.dividendRate}
          fdv={selectedAnalysisStock.fdv}
          onClose={() => setSelectedAnalysisStock(null)}
        />
      )}
    </div>
    </>
  );
}
