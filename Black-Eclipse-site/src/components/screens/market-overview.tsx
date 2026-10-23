'use client';

import React, { useState, useEffect, useMemo } from 'react';
import {
  ArrowUpRight, ArrowDownRight, ArrowRight, Search,
  GlobeStand,
  Layers, Award, TrendingUp, Sliders, X, Coins, ChevronDown,
  Info, Briefcase, Building2, Globe, RefreshCw, ArrowLeft,
  Eye, CalendarClock,
} from '@/lib/icons';
import { Button } from '@/components/ui/button';
import { TabBar } from '@/components/ui/tab-bar';
import { TradingViewChart } from './tradingview-chart';
import { cn } from '@/lib/utils';
import { TopLoader } from '@/components/ui/top-loader';
import { useCommandStore } from '@/lib/search/store';
import { destinationToHref } from '@/lib/search/deep-link';
import { useSubroute } from '@/hooks/use-subroute';
import { usePageShortcuts } from '@/hooks/use-page-shortcuts';
import { useListNavigation } from '@/hooks/use-list-navigation';
import {
  IndexCard, SectorPerformance, ShifterItem, StockItem, FundItem, ETFItem, BlueChipItem,
} from '@/lib/screener/data';
import { useScreenerFilters } from './use-screener-filters';
import { useGlobalMarkets } from './use-global-markets';
import { useForex, useCommodities } from './use-market-tabs';
import { GlobalMarketsOverview } from './market-overview-global-markets';
import { MarketTables } from './market-tables';
import { EarningsCalendar } from './earnings-calendar';
import { StockCryptoTables } from './market-stock-tables';
import { FundEtfTables } from './market-fund-etf-tables';
import { TableLoading } from './market-loaders';
import { currencyCodeFor as currencyFor } from '@/lib/market-currency';
import { marketDisplayName } from '@/lib/markets';
import { resolveUserMarket, setUserMarket } from '@/lib/user-market';
import { marketSentimentFromIndices } from '@/lib/aurora-sentiment';
import { fetchWithRetry, logHandledFetchFailure } from '@/lib/fetch-retry';

// Pure formatting helpers live in @/lib/screener/format (extracted to keep this
// file small). Currency rules: dollar assets keep "$", everything else shows
// its native ISO code ("PKR 327.43"); commodities/forex are always USD.
import { priceWithCurrency, timeAgo } from '@/lib/screener/format';

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
  // (deep link: /?tab=chart&symbol=XYZ boots straight into its chart), instead
  // of the in-page overlay. Shift+click keeps the normal in-page behavior.
  const openInNewTab = (symbol: string, e: { ctrlKey?: boolean; metaKey?: boolean }) => {
    if (!(e.ctrlKey || e.metaKey)) return false;
    try {
      const url = new URL(window.location.origin + destinationToHref({ tab: 'chart', params: { symbol: symbol.toUpperCase() } }));
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
  // Start EMPTY with the dashboard loader active — placeholder demo constants
  // are never rendered as if they were data.
  const [indexData, setIndexData] = useState<IndexCard[]>([]);
  const [sectorPerformance, setSectorPerformance] = useState<SectorPerformance[]>([]);
  const [topGainers, setTopGainers] = useState<ShifterItem[]>([]);
  const [topLosers, setTopLosers] = useState<ShifterItem[]>([]);

  // Customizable ticker strip above the screener: what the user wants to see
  // on top — market indices, top gainers/losers, or a custom symbol list.
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
  // Every major block — ticker strip, sectors, shifters, and each screener
  // table (stocks / crypto / etfs / funds / dividends / forex / commodities)
  // — can be hidden by the user. Persisted in localStorage.
  type SectionKey =
    | 'strip' | 'earnings' | 'sectors' | 'shifters'
    | 'table_stocks' | 'table_crypto' | 'table_etfs' | 'table_funds'
    | 'table_dividend' | 'table_forex' | 'table_commodities';
  const SECTION_KEY = 'be_sections_hidden';
  const SECTION_LABELS: Record<SectionKey, string> = {
    strip: 'Ticker Strip',
    earnings: 'Earnings Calendar',
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

  // DB-backed autocomplete for the pin input — only real, priced symbols
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

  // Resolve the currency that BELONGS to an index card: prefer the currency
  // stamped by /api/indices; fall back to the selected market.
  // (cardCurrency removed — cards now always carry a currency from the API.)

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

  // Global search: 'discovery.<tab>' sub-pages (e.g. 'discovery.crypto').
  // `handleTabChange` above resets filters, matching a real tab switch.
  useSubroute('discovery', (req) => {
    const SCREENER_TABS = ['stocks', 'etfs', 'funds', 'dividend_stocks', 'crypto', 'markets', 'forex', 'commodities'] as const;
    type ScreenerTab = (typeof SCREENER_TABS)[number];
    const target = req.subroute as ScreenerTab;
    if (SCREENER_TABS.includes(target)) handleTabChange(target);
  });

  // Select a market (GLOBAL / US / PK / CRYPTO / ...).
  //   GLOBAL ? show the global markets overview (all indices).
  //   any country ? switch to that country's stock screener.
  const handleMarketSelect = (market: string) => {
    // Market cards carry DB ids (e.g. "US"); the <select> uses "USA" — normalize.
    const normalized = market === 'US' ? 'USA' : market;
    setUserCountry(normalized);
    // Share the choice with the other market surfaces (Market Bubbles), which
    // read the heatmap market ids (US, not USA).
    setUserMarket(market === 'USA' ? 'US' : market);
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

  // Combined Sector/Industry selection: a single dropdown that sets either the
  // sector or the industry filter. The option value is prefixed with the kind
  // ("sector:…" / "industry:…") because real markets (e.g. PK) contain names
  // that are BOTH a sector and an industry — an unprefixed value was ambiguous
  // and always routed to sector.
  const handleSectorIndustryChange = (value: string) => {
    if (value === 'All') {
      setFilterSector('All');
      setFilterIndustry('All');
      return;
    }
    const sep = value.indexOf(':');
    const kind = value.slice(0, sep);
    const name = value.slice(sep + 1);
    if (kind === 'sector') {
      setFilterSector(name);
      setFilterIndustry('All');
    } else {
      setFilterIndustry(name);
      setFilterSector('All');
    }
  };

  // The value shown in the combined dropdown (matches the encoded option value).
  const sectorIndustryValue = filterSector !== 'All'
    ? `sector:${filterSector}`
    : filterIndustry !== 'All' ? `industry:${filterIndustry}` : 'All';

  // Reset page + drop prefetch cache on country, limit, search, sector, or tab changes
  React.useEffect(() => {
    setCurrentPage(1);
    setPageCache({});
  }, [userCountry, limit, stockSearch, filterSector, filterIndustry, filterType, filterMarketCap, filterPE, filterPrice, filterChange, filterVolume, filterDividendYield, filterCountry, screenerTab, stockSortField, stockSortOrder]);

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
  // /api/indices — refreshed whenever the selected market changes. Falls back
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
        // shifters — it just scopes the screener table to US by default.
        const res = await fetchWithRetry(`/api/indices?market=${encodeURIComponent(qc)}`);
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
        logHandledFetchFailure('Failed to load dashboard metrics:', err);
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
    if (filterDividendYield !== 'All') params.set('dividend', filterDividendYield);
    if (stockSearch.trim()) params.set('search', stockSearch.trim());
    // Order the whole universe server-side before paginating, so a header sort
    // is correct across pages, not just within the visible slice.
    params.set('sort', String(stockSortField));
    params.set('dir', stockSortOrder);

    try {
      const res = await fetchWithRetry(`/api/stocks?${params.toString()}`);
      const data = await res.json();
      if (data && data.stocks && data.stocks.length > 0) {
        return { stocks: data.stocks, total: data.pagination?.total ?? data.stocks.length, filterOptions: data.filterOptions };
      }
      return null;
    } catch (err) {
      logHandledFetchFailure('Failed to load from JDBC, using demo:', err);
      return null;
    }
  }, [getQueryCountry, limit, filterType, filterSector, filterIndustry, filterCountry, filterMarketCap, filterPE, filterPrice, filterChange, filterVolume, filterDividendYield, stockSearch, stockSortField, stockSortOrder]);

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
      logHandledFetchFailure('Failed to load from JD, using demo:', err);
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
  }, [userCountry, screenerTab, currentPage, limit, filterType, filterSector, filterIndustry, filterCountry, filterMarketCap, filterPE, filterPrice, filterChange, filterVolume, filterDividendYield, stockSearch, stockSortField, stockSortOrder]);

  // Automatic price backfill: whenever a region's screener is shown and its
  // prices are missing/stale (>15 min), pull live quotes for THE VISIBLE PAGE
  // from yfinance/TradingView so rows show fresh prices within seconds.
  // (Passing symbols scopes /api/refresh to just this page — a full-market
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
  // Fully user-customizable preferences + the pointer-based drag engine live
  // in ./use-global-markets.ts (extracted to keep this file small).
  const {
    globalOverview,
    loadingGlobalMarkets,
    gmSelectedRow,
    setGmSelectedRow,
    gmConfig,
    gmConfigOpen,
    setGmConfigOpen,
    gmSearch,
    setGmSearch,
    applyGmConfig,
    moveGmColumn,
    gmDragId,
    gmDragWidth,
    gmFloatRef,
    beginGmDrag,
  } = useGlobalMarkets(screenerTab === 'markets');


  // Demo fallback rows are placeholders — all prices/changes are zero (never
  // present simulated values as market data). The UI renders them as "—".
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
  const [totalFunds, setTotalFunds] = useState(0);
  const [fundPage, setFundPage] = useState(1);
  const [fundLimit, setFundLimit] = useState(50);
  // Full category list for the dropdown — kept separate from the (filtered,
  // paginated) rows so choosing a category doesn't collapse the option list.
  const [fundCategories, setFundCategories] = useState<string[]>([]);

  // ETF state
  const [etfSearch, setEtfSearch] = useState('');
  const [etfCategory, setEtfCategory] = useState('All');
  const [etfSortField, setEtfSortField] = useState<keyof ETFItem>('symbol');
  const [etfSortOrder, setEtfSortOrder] = useState<'asc' | 'desc'>('asc');
  const [apiEtfs, setApiEtfs] = useState<ETFItem[]>([]);
  const [totalEtfs, setTotalEtfs] = useState(0);
  const [etfPage, setEtfPage] = useState(1);
  const [etfLimit, setEtfLimit] = useState(50);
  const [etfCategories, setEtfCategories] = useState<string[]>([]);

  // Fetch real ETF data from JDDS when the ETFs tab is active. Paginated
  // server-side (the API caps limit at 100) so the full universe is reachable
  // instead of being silently truncated to the first page.
  React.useEffect(() => {
    if (screenerTab !== 'etfs') return;
    let cancelled = false;
    (async () => {
      setLoadingTab(true);
      try {
        const params = new URLSearchParams({
          country: userCountry === 'PK' ? 'PK' : 'US',
          type: 'ETF',
          page: String(etfPage),
          limit: String(etfLimit),
          sort: etfSortField === 'category' ? 'industry' : etfSortField,
          dir: etfSortOrder,
        });
        if (etfCategory !== 'All') params.set('industry', etfCategory);
        if (etfSearch.trim()) params.set('search', etfSearch.trim());
        // ETF advanced filters share change/price state with the Stocks panel;
        // push them server-side so pagination counts the full universe.
        if (filterChange !== 'All') params.set('change', filterChange);
        if (filterPrice !== 'All') params.set('price', filterPrice);
        const res = await fetchWithRetry(`/api/stocks?${params.toString()}`);
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
        logHandledFetchFailure('Failed to load ETFs from JDDS', err);
      } finally {
        if (!cancelled) setLoadingTab(false);
      }
    })();
    return () => { cancelled = true; };
  }, [screenerTab, etfCategory, etfSearch, userCountry, etfPage, etfLimit, etfSortField, etfSortOrder, filterChange, filterPrice]);

  // ETF category options: fetched once (unfiltered, type=ETF) so the dropdown
  // never collapses to just the selected category after a choice.
  React.useEffect(() => {
    if (screenerTab !== 'etfs') return;
    let cancelled = false;
    (async () => {
      try {
        const params = new URLSearchParams({ country: userCountry === 'PK' ? 'PK' : 'US', type: 'ETF', limit: '1' });
        const res = await fetch(`/api/stocks?${params.toString()}`);
        const data = await res.json();
        if (!cancelled && data?.filterOptions?.industries) {
          setEtfCategories(data.filterOptions.industries as string[]);
        }
      } catch { /* non-fatal: dropdown falls back to the page's own categories */ }
    })();
    return () => { cancelled = true; };
  }, [screenerTab, userCountry]);

  // Fetch real Mutual Fund data from JDDS when the funds tab is active (paginated).
  React.useEffect(() => {
    if (screenerTab !== 'funds') return;
    let cancelled = false;
    (async () => {
      setLoadingTab(true);
      try {
        const params = new URLSearchParams({
          country: userCountry === 'PK' ? 'PK' : 'US',
          type: 'Mutual Fund',
          page: String(fundPage),
          limit: String(fundLimit),
          sort: fundSortField === 'category' ? 'industry' : fundSortField,
          dir: fundSortOrder,
        });
        if (fundCategory !== 'All') params.set('industry', fundCategory);
        if (fundSearch.trim()) params.set('search', fundSearch.trim());
        const res = await fetchWithRetry(`/api/stocks?${params.toString()}`);
        const data = await res.json();
        if (!cancelled && data && Array.isArray(data.stocks)) {
          const mapped: FundItem[] = (data.stocks as Array<Record<string, unknown>>).map(s => ({
            symbol: String(s.symbol ?? ''),
            name: String(s.name ?? ''),
            category: (s.industry as string) || 'General',
            nav: (s.price as number) || 0,
            changePercent: (s.changePercent as number) || 0,
            // Not sourced in JDDS yet → null renders N/A, not a fake 0.
            ytdReturn: null,
            expenseRatio: null,
            rating: null,
            aum: (s.marketCap as string) || 'N/A',
          }));
          setApiFunds(mapped);
          setTotalFunds(data.pagination?.total ?? mapped.length);
        }
      } catch (err) {
        logHandledFetchFailure('Failed to load funds from JDDS', err);
      } finally {
        if (!cancelled) setLoadingTab(false);
      }
    })();
    return () => { cancelled = true; };
  }, [screenerTab, fundSearch, userCountry, fundCategory, fundPage, fundLimit, fundSortField, fundSortOrder]);

  // Fund category options: fetched once (unfiltered).
  React.useEffect(() => {
    if (screenerTab !== 'funds') return;
    let cancelled = false;
    (async () => {
      try {
        const params = new URLSearchParams({ country: userCountry === 'PK' ? 'PK' : 'US', type: 'Mutual Fund', limit: '1' });
        const res = await fetch(`/api/stocks?${params.toString()}`);
        const data = await res.json();
        if (!cancelled && data?.filterOptions?.industries) {
          setFundCategories(data.filterOptions.industries as string[]);
        }
      } catch { /* non-fatal */ }
    })();
    return () => { cancelled = true; };
  }, [screenerTab, userCountry]);

  // Reset to page 1 whenever an ETF/Fund filter or search changes.
  React.useEffect(() => { setEtfPage(1); }, [etfCategory, etfSearch, userCountry, etfLimit]);
  React.useEffect(() => { setFundPage(1); }, [fundCategory, fundSearch, userCountry, fundLimit]);

  // Forex & commodities live in ./use-market-tabs.ts (extracted to keep this
  // file small). Each hook owns its fetch, filter state, and filtered list.
  const {
    forexPairs, forexSearch, setForexSearch, forexChange, setForexChange,
    forexCurrency, setForexCurrency, forexSortField, forexSortOrder,
    loadingForex, toggleForexSort, filteredForex,
  } = useForex(screenerTab === 'markets' || screenerTab === 'forex', setLoadingTab);
  const {
    commodities, commoditySearch, setCommoditySearch, commodityChange,
    setCommodityChange, commodityCategory, setCommodityCategory,
    loadingCommodities, filteredCommodities,
  } = useCommodities(screenerTab === 'markets' || screenerTab === 'commodities', setLoadingTab);

  // Dividend states
  const [dividendSearch, setDividendSearch] = useState('');
  const [dividendSortField, setDividendSortField] = useState<keyof BlueChipItem>('symbol');
  const [dividendSortOrder, setDividendSortOrder] = useState<'asc' | 'desc'>('asc');


  const handleAction = (ticker: string) => {
    onAnalyzeTicker(ticker);
  };

  // Fields /api/stocks can ORDER BY consistently with what the table DISPLAYS.
  // `sector`/`industry`/`country` are excluded: the API normalizes their values
  // on read (synonyms → canonical sector, "United States" → "US"), so a DB
  // order by the raw column would interleave rows that render identically. Those
  // fall back to client sorting over the returned page so the visible order
  // matches the column. Everything else is ordered over the full universe.
  const SERVER_SORTABLE_FIELDS = new Set([
    'symbol', 'name', 'securityType',
    'price', 'changePercent', 'marketCap', 'peRatio', 'volume', 'rank',
  ]);

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
    // /api/stocks ordered the page by the active sort (JDDS-backed tabs only);
    // the hook must not re-sort the slice — but only when the sort field is one
    // the DB actually ordered by.
    stocksServerSorted: dataSource === 'jdds'
      && (screenerTab === 'stocks' || screenerTab === 'crypto')
      && SERVER_SORTABLE_FIELDS.has(String(stockSortField)),
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

  const rootRef = React.useRef<HTMLDivElement>(null);
  const searchRef = React.useRef<HTMLInputElement>(null);
  const shortcutsEnabled = !embedded && !selectedAnalysisStock && !loadingApi;
  const tableNavEnabled = shortcutsEnabled && !loadingTab && (screenerTab === 'stocks' || screenerTab === 'crypto');
  const tableIds = tableNavEnabled ? filteredStocks.map((s) => s.symbol) : [];
  const tablePageCount = Math.max(1, Math.ceil(totalStocks / limit));
  const tableNav = useListNavigation({
    ids: tableIds,
    rootRef,
    enabled: tableNavEnabled,
    shortcutPrefix: 'screener.list',
    onOpen: (symbol) => {
      if (screenerTab === 'crypto') {
        setExpandedSymbol((prev) => (prev === symbol ? null : symbol));
        return;
      }
      const stock = filteredStocks.find((s) => s.symbol === symbol);
      if (stock) handleSymbolClick(stock.symbol, stock.name, stock);
    },
    onEscape: () => setSelectedAnalysisStock(null),
    pagination: {
      onPrevious: () => setCurrentPage((prev) => Math.max(prev - 1, 1)),
      onNext: () => setCurrentPage((prev) => Math.min(prev + 1, tablePageCount)),
      canPrevious: currentPage > 1,
      canNext: currentPage < tablePageCount,
    },
  });
  usePageShortcuts(rootRef, [
    { id: 'screener.search', label: 'Search current screener', keys: 'S', run: () => searchRef.current?.focus(), enabled: shortcutsEnabled && (screenerTab !== 'forex' || sectionVisible('table_forex')) },
    { id: 'screener.filters', label: 'Toggle advanced filters', keys: 'Shift+F', run: () => setShowAdvancedFilters((v) => !v), enabled: shortcutsEnabled && ['stocks', 'crypto', 'etfs', 'funds', 'dividend_stocks'].includes(screenerTab) },
    { id: 'screener.customize', label: 'Customize screener', keys: 'Shift+C', run: () => { if (screenerTab === 'markets') setGmConfigOpen((v) => !v); else setSectionsOpen((v) => !v); }, enabled: shortcutsEnabled },
    { id: 'screener.refresh', label: 'Refresh prices', keys: 'R', run: handleRefreshPrices, enabled: shortcutsEnabled && !refreshing && userCountry !== 'GLOBAL' },
  ]);

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
      <div ref={rootRef} data-keyboard-scope="Market screener" className={cn(
        "w-full py-6 space-y-8 pb-20 relative bg-transparent",
        !embedded && "flex-1 overflow-y-auto h-full"
      )}>
      
      {/* Page Title Header */}
      {!embedded && (
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 animate-fade-in-up border-b border-border/20 pb-6 mb-4">
          <div>
            <h1 className="font-serif text-3xl md:text-4xl font-medium tracking-tight text-foreground flex items-center gap-3">
              <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/15 shadow-lg shadow-primary/10">
                <GlobeStand className="text-primary" size={32} />
              </span>
              Market Discover
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

      {/* Earnings Calendar — embedded at the top of the screener (no separate page). */}
      {sectionVisible('earnings') && (
        <div className="animate-fade-in-up p-5 rounded-2xl glass-card border border-white/10 dark:border-white/5 flex flex-col">
          <div className="flex items-center gap-2 mb-4">
            <CalendarClock className="text-primary w-5 h-5" />
            <h2 className="font-serif text-lg font-semibold tracking-tight text-foreground">Earnings Calendar</h2>
            <button
              onClick={() => toggleSection('earnings')}
              className="ml-auto text-[10px] font-bold text-muted-foreground hover:text-rose-400 uppercase tracking-wider cursor-pointer transition-colors"
              title="Hide this section"
            >
              Hide
            </button>
          </div>
          <EarningsCalendar />
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
        {/* Inline config panel — expands in flow so content below moves down
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
                    <p className="text-[9px] uppercase font-bold text-muted-foreground/70 tracking-wider mb-1">Matches from database — click to pin</p>
                    <div className="flex flex-col gap-1 max-h-64 overflow-y-auto">
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
                            {s.price > 0 ? priceWithCurrency(s.marketId || s.currency, s.price) : '—'}
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
                <p className="text-[9px] text-muted-foreground mt-2">Searches every market (US, PSX, India, crypto…). Pinned symbols stay fixed across all countries.</p>
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
                        {idxCard.price > 0 ? priceWithCurrency(idxCard.currency || userCountry, idxCard.price) : '—'}
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
                ? 'No pinned symbols yet — click Customize above and type any symbol from any market (e.g. AAPL, OGDC, BTC).'
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

          <div className="grid grid-cols-1 gap-4 h-full sm:grid-cols-2">
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

            {/* DEMO badge — never present simulated data as live market data. */}
            {dataSource === 'demo' && (
              <div className="glass-card-subtle border border-amber-500/10 rounded-2xl p-3.5 flex items-center justify-between animate-fade-in text-amber-400">
                <div className="flex items-center gap-3">
                  <Info className="w-4 h-4 text-amber-400 shrink-0" />
                  <div className="text-xs font-semibold">
                    SIMULATED DATA — these are demo values, not live market prices. Import a universe or enable the scraper to load real data.
                  </div>
                </div>
                <span className="text-[9px] bg-amber-500/15 px-2 py-0.5 rounded font-mono font-bold">DEMO</span>
              </div>
            )}
        
        {/* Tab Selection Row — market chip left, back button right */}
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
            {screenerTab !== 'markets' && (
              <button
                onClick={() => handleMarketSelect('GLOBAL')}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-primary border border-border/40 hover:border-primary/40 bg-accent/30 hover:bg-accent/60 rounded-xl px-3 py-1.5 transition-all cursor-pointer shrink-0"
              >
                <ArrowLeft size={13} /> Back to Market Discover
              </button>
            )}
          </div>
        </div>

        {/* Hidden-sections manager — lists every table/section with a toggle */}
        {sectionsOpen && (
          <div className="mb-3 p-3 sm:p-4 rounded-xl bg-background border border-border shadow-lg w-full animate-fade-in-up">
            <p className="text-[9px] uppercase font-bold text-muted-foreground/70 tracking-wider mb-2">Tables &amp; sections — click to show/hide</p>
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
                  ref={searchRef}
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
                        <option key={`s-${s}`} value={`sector:${s}`}>{s}</option>
                      ))}
                    </optgroup>
                    <optgroup label="Industries">
                      {filterOptions.industries.map((ind) => (
                        <option key={`i-${ind}`} value={`industry:${ind}`}>{ind}</option>
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
                  ref={searchRef}
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
                  {filterOptions.sectors.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
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
                  ref={searchRef}
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
                  {(etfCategories.length > 0
                    ? etfCategories
                    : Array.from(new Set(apiEtfs.map((e) => e.category).filter(Boolean))).sort()
                  ).map((c) => (
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
                  ref={searchRef}
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
                  {(fundCategories.length > 0
                    ? fundCategories
                    : Array.from(new Set(apiFunds.map((f) => f.category).filter(Boolean))).sort()
                  ).map((c) => (
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
                  ref={searchRef}
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
                  ref={searchRef}
                  type="text"
                  placeholder="Search markets..."
                  value={gmSearch}
                  onChange={e => setGmSearch(e.target.value)}
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
                  ref={searchRef}
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
                  ref={searchRef}
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
                        <option key={`s-${s}`} value={`sector:${s}`}>{s}</option>
                      ))}
                    </optgroup>
                    <optgroup label="Industries">
                      {filterOptions.industries.map((ind) => (
                        <option key={`i-${ind}`} value={`industry:${ind}`}>{ind}</option>
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
                      // Value stays the canonical code (matches the Country
                      // column); the label is the readable market name.
                      <option key={c} value={c}>{marketDisplayName(c)}</option>
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

              {/* Dividend Yield */}
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-muted-foreground/80 tracking-widest font-mono">Dividend Yield</span>
                <div className="relative">
                  <select value={filterDividendYield} onChange={e => setFilterDividendYield(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-primary/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
                    <option value="All">Any Yield</option>
                    <option value="None">No Dividend</option>
                    <option value="Positive">Pays Dividend</option>
                    <option value="Over2">Over 2%</option>
                    <option value="Over5">Over 5%</option>
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                </div>
              </div>

              {/* Volume */}
              <div className="flex flex-col gap-1.5">
                <span className="text-[9px] uppercase font-bold text-muted-foreground/80 tracking-widest font-mono">Volume</span>
                <div className="relative">
                  <select value={filterVolume} onChange={e => setFilterVolume(e.target.value)}
                    className="w-full appearance-none bg-background/80 border border-border/50 hover:border-primary/40 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none transition-all cursor-pointer">
                    <option value="All">Any Volume</option>
                    <option value="Under1">Under 1M</option>
                    <option value="1to10">1M – 10M</option>
                    <option value="Over10">Over 10M</option>
                    <option value="Over30">Over 30M</option>
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
                    {filterOptions.sectors.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
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
                    {(etfCategories.length > 0
                      ? etfCategories
                      : Array.from(new Set(apiEtfs.map((e) => e.category).filter(Boolean))).sort()
                    ).map((c) => (
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
                    {(fundCategories.length > 0
                      ? fundCategories
                      : Array.from(new Set(apiFunds.map((f) => f.category).filter(Boolean))).sort()
                    ).map((c) => (
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
              {/* YTD return is not yet sourced into the fund adapter (rendered
                  as N/A, not a fake 0), so this control is shown disabled rather
                  than silently bound to the Change filter (a previous duplicate). */}
              <div className="flex flex-col gap-1.5 opacity-50">
                <span className="text-[9px] uppercase font-bold text-muted-foreground/80 tracking-widest font-mono">YTD Return</span>
                <div className="relative">
                  <select disabled value="All" title="YTD return is not available in JDDS for funds yet"
                    className="w-full appearance-none bg-background/80 border border-border/50 text-foreground text-[11px] rounded-lg pl-2.5 pr-7 py-2 outline-none cursor-not-allowed">
                    <option value="All">Not available</option>
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



        {/* Global Markets overview — fully customizable: layout, countries, columns */}
        {/* Hybrid load indicator: skeletons cover first paint; this ASCII
            dot-grid bar shows live progress on top of existing data during
            loads/refreshes so users always see that data is coming in. */}
        {tableLoader.active && (
          <TableLoading pct={tableLoader.pct} label={tableLoader.label} />
        )}

        {screenerTab === 'markets' && (
          <GlobalMarketsOverview
            gmConfig={gmConfig}
            gmConfigOpen={gmConfigOpen}
            setGmConfigOpen={setGmConfigOpen}
            gmSearch={gmSearch}
            setGmSearch={setGmSearch}
            applyGmConfig={applyGmConfig}
            moveGmColumn={moveGmColumn}
            gmSelectedRow={gmSelectedRow}
            setGmSelectedRow={setGmSelectedRow}
            gmDragId={gmDragId}
            gmDragWidth={gmDragWidth}
            gmFloatRef={gmFloatRef}
            beginGmDrag={beginGmDrag}
            globalOverview={globalOverview}
            loadingGlobalMarkets={loadingGlobalMarkets}
            sectionVisible={sectionVisible}
            toggleSection={toggleSection}
            handleSymbolClick={handleSymbolClick}
            handleMarketSelect={handleMarketSelect}
            handleTabChange={handleTabChange}
            filteredForex={filteredForex}
            loadingForex={loadingForex}
            commodities={commodities}
            loadingCommodities={loadingCommodities}
          />
        )}

        <MarketTables
          screenerTab={screenerTab}
          sectionVisible={sectionVisible}
          handleSymbolClick={handleSymbolClick}
          onAnalyzeTicker={onAnalyzeTicker}
          forexSortField={forexSortField}
          forexSortOrder={forexSortOrder}
          toggleForexSort={toggleForexSort}
          loadingForex={loadingForex}
          filteredForex={filteredForex}
          loadingCommodities={loadingCommodities}
          filteredCommodities={filteredCommodities}
        />

        <StockCryptoTables
          screenerTab={screenerTab}
          sectionVisible={sectionVisible}
          stockSortField={stockSortField}
          stockSortOrder={stockSortOrder}
          toggleStockSort={toggleStockSort}
          loadingTab={loadingTab}
          loadingApi={loadingApi}
          filteredStocks={filteredStocks}
          expandedSymbol={expandedSymbol}
          setExpandedSymbol={setExpandedSymbol}
          tableNav={tableNav}
          handleSymbolClick={handleSymbolClick}
          onAnalyzeTicker={onAnalyzeTicker}
          currentPage={currentPage}
          setCurrentPage={setCurrentPage}
          limit={limit}
          setLimit={setLimit}
          totalStocks={totalStocks}
          userCountry={userCountry}
          priceWithCurrency={priceWithCurrency}
        />

        <FundEtfTables
          screenerTab={screenerTab}
          sectionVisible={sectionVisible}
          handleSymbolClick={handleSymbolClick}
          onAnalyzeTicker={onAnalyzeTicker}
          loadingTab={loadingTab}
          userCountry={userCountry}
          priceWithCurrency={priceWithCurrency}
          apiEtfs={apiEtfs}
          etfSortField={etfSortField}
          etfSortOrder={etfSortOrder}
          toggleEtfSort={toggleEtfSort}
          filteredETFs={filteredETFs}
          etfTotal={totalEtfs}
          etfPage={etfPage}
          etfLimit={etfLimit}
          setEtfPage={setEtfPage}
          setEtfLimit={setEtfLimit}
          apiFunds={apiFunds}
          fundSortField={fundSortField}
          fundSortOrder={fundSortOrder}
          toggleFundSort={toggleFundSort}
          filteredFunds={filteredFunds}
          fundTotal={totalFunds}
          fundPage={fundPage}
          fundLimit={fundLimit}
          setFundPage={setFundPage}
          setFundLimit={setFundLimit}
          dividendSortField={dividendSortField}
          dividendSortOrder={dividendSortOrder}
          toggleDividendSort={toggleDividendSort}
          filteredDividendStocks={filteredDividendStocks}
        />
      </div>
    </div>

      </div>
      
      {/* TradingView Detail Chart Analysis Screen Page Overlay */}
      {selectedAnalysisStock && (
        <TradingViewChart
          symbol={selectedAnalysisStock.symbol}
          stockName={selectedAnalysisStock.name}
          peRatio={selectedAnalysisStock.peRatio} forwardPE={selectedAnalysisStock.forwardPE}
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
