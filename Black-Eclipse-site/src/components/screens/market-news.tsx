'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { Newspaper, Sparkles, Eye, Search, X, SlidersHorizontal } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { TopLoader } from '@/components/ui/top-loader';
import { Skeleton } from '@/components/ui/skeleton';

export interface NewsItem {
  id: string;
  source: string;
  category?: string;
  region?: string;
  tier?: number;
  ticker?: string;
  timestamp: string;
  headline: string;
  summary: string;
  sentiment: 'bullish' | 'bearish' | 'neutral';
  impactPercent: number;
  url?: string;
}

const NEWS_MOCK: NewsItem[] = [
  {
    id: 'n1',
    source: 'Bloomberg',
    ticker: 'NVDA',
    timestamp: '12m ago',
    headline: 'NVIDIA CEO Unveils Next-Gen Blackwell Ultra Chips at Tech Summit',
    summary: 'NVIDIA CEO Jensen Huang showcased the new Blackwell Ultra architecture, delivering extreme efficiency and high compute power. Market analysts predict massive upgrades in hyperscaler datacenters starting Q3, driving continued dominance.',
    sentiment: 'bullish',
    impactPercent: 4.8,
  },
  {
    id: 'n2',
    source: 'Reuters',
    ticker: 'TSLA',
    timestamp: '35m ago',
    headline: 'Tesla Seeks Shareholder Approval for Model Y Autonomy Integration in EU',
    summary: 'Tesla has formally submitted regulatory requests to deploy its next-generation Full Self-Driving (FSD) beta across European countries. While approval remains subject to stringent safety checks, a positive nod could unlock a massive secondary revenue pipeline.',
    sentiment: 'bullish',
    impactPercent: 2.5,
  },
  {
    id: 'n3',
    source: 'BlackEclipse AI',
    ticker: 'AAPL',
    timestamp: '1h ago',
    headline: 'AI Stock Brief: Apple Services Revenue Surges Beyond Hardware Projections',
    summary: 'An autonomous financial sweep indicates App Store and Apple Pay transactions have reached record highs this quarter, compensating for slight declines in global smartphone shipments. Services gross margins remain high at 74%.',
    sentiment: 'neutral',
    impactPercent: 0.5,
  },
  {
    id: 'n4',
    source: 'Financial Times',
    ticker: 'MSFT',
    timestamp: '2h ago',
    headline: 'Antitrust Concerns Mount as EU Probes Microsoft Cloud Bundling Practices',
    summary: 'Regulatory officials in Brussels have expanded their compliance audits into Microsofts cloud bundling services. Industry rivals argue licensing terms restrict fair competition, posing a minor litigation risk.',
    sentiment: 'bearish',
    impactPercent: -1.2,
  },
  {
    id: 'n5',
    source: 'CoinDesk',
    ticker: 'BTC',
    timestamp: '2h ago',
    headline: 'Bitcoin Crosses $67,000 as Institutional Inflows into Spot ETFs Accelerate',
    summary: 'Spot Bitcoin ETFs recorded a net inflow of $350 million yesterday, marking the tenth consecutive day of positive inflows. Analysts suggest this institutional demand is establishing a strong price floor above key support levels.',
    sentiment: 'bullish',
    impactPercent: 3.2,
  },
  {
    id: 'n6',
    source: 'CoinTelegraph',
    ticker: 'ETH',
    timestamp: '3h ago',
    headline: 'Ethereum Developers Confirm Date for Next Core Network Upgrade',
    summary: 'The next major Ethereum network upgrade, designed to reduce transaction fees on Layer 2 scaling networks further, has been scheduled for testnet deployment. This is expected to drive increased user activity across decentralized finance protocols.',
    sentiment: 'bullish',
    impactPercent: 2.8,
  },
];

interface MarketNewsProps {
  onDiscussNews?: (news: NewsItem) => void;
  onAnalyzeTicker?: (ticker: string) => void;
  fullPage?: boolean;
  onNewsStatusChange?: (isBullish: boolean) => void;
}

const CATEGORIES = ['MARKETS', 'CRYPTO', 'REGULATORY', 'GEOPOLITICS', 'ECONOMIC', 'TECH', 'ENERGY'] as const;
const REGIONS = ['US', 'GLOBAL', 'EU', 'UK', 'ASIA', 'INDIA', 'MENA'] as const;
const TIERS = [
  { value: '1', label: 'T1 Wires' },
  { value: '2', label: 'T2 Media' },
  { value: '3', label: 'T3 Analysis' },
  { value: '4', label: 'T4 Blogs' },
] as const;
const SENTIMENTS = ['bullish', 'bearish', 'neutral'] as const;

interface FilterState {
  category: string;
  region: string;
  tier: string;
  sentiment: string;
  q: string;
}

const EMPTY_FILTERS: FilterState = { category: '', region: '', tier: '', sentiment: '', q: '' };

// ─── Card customization ────────────────────────────────────────────────
// User-tunable card appearance, persisted per-browser in localStorage.

export interface CardSettings {
  columns: 1 | 2 | 3;            // grid layout
  density: 'compact' | 'cozy';   // card padding + font scale
  showSummary: boolean;
  summaryLines: 2 | 3 | 4 | 0;   // 0 = unlimited
  showBadges: boolean;           // source/category/ticker row
  showSentiment: boolean;        // sentiment pill + swing estimate
  showButtons: boolean;          // footer action row
  showTimestamp: boolean;
  glow: boolean;                 // ambient sentiment glow
}

const DEFAULT_CARD_SETTINGS: CardSettings = {
  columns: 1,
  density: 'cozy',
  showSummary: true,
  summaryLines: 3,
  showBadges: true,
  showSentiment: true,
  showButtons: true,
  showTimestamp: true,
  glow: true,
};

const CARD_SETTINGS_KEY = 'be_news_card_settings';

function loadCardSettings(): CardSettings {
  if (typeof window === 'undefined') return DEFAULT_CARD_SETTINGS;
  try {
    const raw = window.localStorage.getItem(CARD_SETTINGS_KEY);
    if (!raw) return DEFAULT_CARD_SETTINGS;
    return { ...DEFAULT_CARD_SETTINGS, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_CARD_SETTINGS;
  }
}

const CARD_COLUMNS_CLASS: Record<CardSettings['columns'], string> = {
  1: 'grid-cols-1',
  2: 'grid-cols-1 lg:grid-cols-2',
  3: 'grid-cols-1 lg:grid-cols-2 xl:grid-cols-3',
};

const DENSITY_CLASS: Record<CardSettings['density'], { card: string; title: string; body: string }> = {
  compact: { card: 'p-3.5 gap-3', title: 'text-sm', body: 'text-[11px]' },
  cozy: { card: 'p-5 gap-4', title: 'text-base', body: 'text-xs' },
};

// Static map — Tailwind's JIT can't see dynamically interpolated classes.
const LINE_CLAMP_CLASS: Record<CardSettings['summaryLines'], string> = {
  0: '',
  2: 'line-clamp-2',
  3: 'line-clamp-3',
  4: 'line-clamp-4',
};



function FilterSelect({ value, onChange, placeholder, options }: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  options: readonly { value: string; label: string }[] | readonly string[];
}) {
  return (
    <div className="relative h-9">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`h-9 appearance-none rounded-lg bg-accent/30 border pl-3 pr-8 text-[12px] font-mono cursor-pointer focus:outline-none focus:border-primary/60 transition-colors ${
          value ? 'text-primary border-primary/40 bg-primary/10' : 'text-muted-foreground border-border/30'
        }`}
      >
        <option value="">{placeholder}</option>
        {options.map((o) => {
          const val = typeof o === 'string' ? o : o.value;
          const label = typeof o === 'string' ? o : o.label;
          return <option key={val} value={val} className="bg-background text-foreground">{label}</option>;
        })}
      </select>
      <span className={`pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[9px] ${value ? 'text-primary' : 'text-muted-foreground/60'}`}>▼</span>
    </div>
  );
}

export function MarketNews({ onDiscussNews, onAnalyzeTicker, fullPage = false, onNewsStatusChange }: MarketNewsProps) {
  const [selectedNews, setSelectedNews] = useState<NewsItem | null>(null);
  const [newsList, setNewsList] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [pendingQ, setPendingQ] = useState('');
  const [cards, setCards] = useState<CardSettings>(DEFAULT_CARD_SETTINGS);
  const [showCustomize, setShowCustomize] = useState(false);

  useEffect(() => {
    setCards(loadCardSettings());
  }, []);

  const updateCards = (patch: Partial<CardSettings>) => {
    setCards((prev) => {
      const next = { ...prev, ...patch };
      try { window.localStorage.setItem(CARD_SETTINGS_KEY, JSON.stringify(next)); } catch { /* private mode */ }
      return next;
    });
  };

  const resetCards = () => {
    try { window.localStorage.removeItem(CARD_SETTINGS_KEY); } catch { /* ignore */ }
    setCards(DEFAULT_CARD_SETTINGS);
  };

  const activeFilterCount = useMemo(
    () => Object.values(filters).filter(Boolean).length,
    [filters]
  );

  const fetchNews = async (pageNum = 1, f: FilterState = filters) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ page: String(pageNum), limit: '10' });
      if (f.category) params.set('category', f.category);
      if (f.region) params.set('region', f.region);
      if (f.tier) params.set('tier', f.tier);
      if (f.sentiment) params.set('sentiment', f.sentiment);
      if (f.q) params.set('q', f.q);
      const res = await fetch(`/api/news?${params.toString()}`);
      const data = await res.json();
      const news = data.news || [];
      if (news.length > 0) {
        setNewsList(news);
        setPage(pageNum);
        setTotalPages(data.pagination?.totalPages || 1);
        setTotalItems(data.pagination?.total || news.length);
        const bullishCount = news.filter((n: { sentiment: string }) => n.sentiment === 'bullish').length;
        const bearishCount = news.filter((n: { sentiment: string }) => n.sentiment === 'bearish').length;
        onNewsStatusChange?.(bullishCount >= bearishCount);
      } else {
        // Fallback to built-in demo data if the feed is empty/unreachable.
        // (Only for unfiltered first page — a filtered empty result is real.)
        if (pageNum === 1 && activeFilterCount === 0) {
          setNewsList(NEWS_MOCK);
          setTotalItems(NEWS_MOCK.length);
          const bullishCount = NEWS_MOCK.filter(n => n.sentiment === 'bullish').length;
          const bearishCount = NEWS_MOCK.filter(n => n.sentiment === 'bearish').length;
          onNewsStatusChange?.(bullishCount >= bearishCount);
        } else {
          setNewsList([]);
          setTotalItems(0);
        }
        setPage(pageNum);
        setTotalPages(1);
      }
    } catch (e) {
      console.error("[MarketNews] Error fetching news:", e);
      if (pageNum === 1 && activeFilterCount === 0) {
        setNewsList(NEWS_MOCK);
        setTotalItems(NEWS_MOCK.length);
      } else {
        setNewsList([]);
        setTotalItems(0);
      }
      setPage(pageNum);
      setTotalPages(1);
      const bullishCount = NEWS_MOCK.filter(n => n.sentiment === 'bullish').length;
      const bearishCount = NEWS_MOCK.filter(n => n.sentiment === 'bearish').length;
      onNewsStatusChange?.(bullishCount >= bearishCount);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNews(1);
    // fetchNews is stable per-render; only run on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDiscuss = (item?: NewsItem) => {
    const target = item || selectedNews;
    if (target) {
      onDiscussNews?.(target);
      setSelectedNews(null);
    }
  };

  const handleAnalyze = (item?: NewsItem) => {
    const target = item || selectedNews;
    if (target && target.ticker) {
      onAnalyzeTicker?.(target.ticker);
      setSelectedNews(null);
    }
  };

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= totalPages) {
      fetchNews(newPage);
    }
  };

  const applyFilters = (next: FilterState) => {
    setFilters(next);
    fetchNews(1, next);
  };

  const setFilter = (patch: Partial<FilterState>) => {
    const next = { ...filters, ...patch };
    // Toggling filters off entirely resets to the default view.
    if (!next.category && !next.region && !next.tier && !next.sentiment && !next.q) {
      applyFilters(EMPTY_FILTERS);
    } else {
      applyFilters(next);
    }
  };

  const clearFilters = () => {
    setPendingQ('');
    applyFilters(EMPTY_FILTERS);
  };

  if (loading) {
    const loadingBar = <TopLoader />;

    if (fullPage) {
      return (
        <>
          {loadingBar}
          <div className="w-full flex flex-col gap-4">
            {[1, 2, 3, 4, 5].map(i => (
              <div key={i} className="flex flex-col md:flex-row md:items-center justify-between gap-4 border border-border/10 rounded-2xl p-5">
                <div className="flex-1 space-y-3">
                  <div className="flex gap-2">
                    <Skeleton className="h-4 w-16" />
                    <Skeleton className="h-4 w-12" />
                    <Skeleton className="h-4 w-20" />
                  </div>
                  <Skeleton className="h-6 w-3/4" />
                  <div className="space-y-1.5">
                    <Skeleton className="h-3.5 w-full" />
                    <Skeleton className="h-3.5 w-5/6" />
                  </div>
                </div>
                <div className="shrink-0 min-w-[200px] border-t md:border-t-0 md:border-l border-border/10 pt-4 md:pt-0 md:pl-6 space-y-3">
                  <Skeleton className="h-5 w-24 rounded-full ml-auto" />
                  <div className="flex gap-2">
                    <Skeleton className="h-8.5 flex-1 rounded-xl" />
                    <Skeleton className="h-8.5 flex-1 rounded-xl" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      );
    }
    return (
      <>
        {loadingBar}
        <div className="w-full flex flex-col rounded-2xl p-4 gap-4 border border-border/10">
          <Skeleton className="h-4 w-28" />
          <div className="space-y-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="p-3 border border-border/10 rounded-xl space-y-2">
                <div className="flex justify-between">
                  <Skeleton className="h-3 w-12" />
                  <Skeleton className="h-3 w-10" />
                </div>
                <Skeleton className="h-4 w-5/6" />
                <Skeleton className="h-3 w-16 rounded-full" />
              </div>
            ))}
          </div>
        </div>
      </>
    );
  }

  if (error && newsList.length === 0) {
    return (
      <div className="w-full text-center py-10 font-mono text-xs text-muted-foreground border border-dashed border-border/25 rounded-2xl p-6 bg-card/10">
        <p className="text-rose-400 font-bold mb-2">Error: {error}</p>
        <button onClick={() => fetchNews()} className="px-4 py-2 bg-primary text-primary-foreground font-semibold rounded-xl cursor-pointer hover:bg-primary/90 transition-all">
          Retry News Feed Load
        </button>
      </div>
    );
  }

  if (fullPage) {
    return (
      <div className="w-full flex flex-col gap-6 select-none">
        {/* ─── Filter Bar ─── */}
        <div className="w-full rounded-2xl border border-border/10 bg-[#0f0f0f]/60 backdrop-blur-xl p-4 flex flex-col lg:flex-row lg:items-center gap-3">
          <form
            className="flex items-center gap-2 flex-1 min-w-0"
            onSubmit={(e) => { e.preventDefault(); setFilter({ q: pendingQ.trim() }); }}
          >
            <div className="relative flex-1 min-w-0 max-w-md">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                value={pendingQ}
                onChange={(e) => setPendingQ(e.target.value)}
                placeholder="Search headlines, keywords, tickers..."
                className="h-9 w-full rounded-lg bg-accent/30 border border-border/30 pl-9 pr-8 text-[12px] font-mono text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-primary/60 transition-colors"
              />
              {pendingQ && (
                <button
                  type="button"
                  onClick={() => { setPendingQ(''); if (filters.q) setFilter({ q: '' }); }}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground cursor-pointer"
                >
                  <X size={13} />
                </button>
              )}
            </div>
            <button
              type="submit"
              className="h-9 px-4 shrink-0 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 text-[12px] font-semibold cursor-pointer transition-colors"
            >
              Search
            </button>
          </form>

          <div className="flex items-center gap-2 flex-wrap">
            <FilterSelect
              value={filters.category}
              placeholder="Category"
              options={CATEGORIES}
              onChange={(v) => setFilter({ category: v })}
            />
            <FilterSelect
              value={filters.region}
              placeholder="Region"
              options={REGIONS}
              onChange={(v) => setFilter({ region: v })}
            />
            <FilterSelect
              value={filters.tier}
              placeholder="Source Tier"
              options={TIERS}
              onChange={(v) => setFilter({ tier: v })}
            />
            <FilterSelect
              value={filters.sentiment}
              placeholder="Sentiment"
              options={SENTIMENTS}
              onChange={(v) => setFilter({ sentiment: v })}
            />
            {activeFilterCount > 0 && (
              <button
                onClick={clearFilters}
                className="h-9 px-3 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/25 text-[11px] font-mono font-semibold cursor-pointer transition-colors inline-flex items-center gap-1.5"
              >
                <X size={12} /> Clear ({activeFilterCount})
              </button>
            )}
          </div>
        </div>

        {/* ─── Result count + Customize ─── */}
        <div className="flex items-center justify-between gap-3 font-mono text-[11px] text-muted-foreground px-1 flex-wrap">
          <span className="flex items-center gap-2 min-w-0">
            <Newspaper size={12} className="text-primary" />
            <span><span className="text-foreground font-bold">{totalItems}</span> articles</span>
            <span className="text-[10px] text-muted-foreground font-mono hidden md:inline">
              {activeFilterCount > 0 ? `filtered · page ${page} of ${totalPages}` : `page ${page} of ${totalPages}`}
            </span>
          </span>
          <button
            onClick={() => setShowCustomize((v) => !v)}
            className={`flex items-center gap-1.5 text-xs font-bold tracking-wider border rounded-lg px-3.5 py-2 transition-all cursor-pointer shrink-0 ${
              showCustomize
                ? 'text-primary bg-primary/10 border-primary/40'
                : 'text-muted-foreground hover:text-primary bg-accent/40 hover:bg-accent/70 border-border/40'
            }`}
            title="Customize how cards look"
          >
            <SlidersHorizontal size={14} /> Customize
          </button>
        </div>

        {/* Inline config panel — expands in flow, pushes content down */}
        {showCustomize && (
          <div className="p-3 sm:p-4 rounded-xl bg-[#0f0f0f]/70 dark:bg-[#0f0f0f]/70 bg-white/80 backdrop-blur-xl border border-white/10 dark:border-white/5 shadow-lg w-full max-w-full overflow-hidden animate-fade-in-up space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-[10px] font-bold text-foreground uppercase tracking-wider">Card Preferences</p>
              <button
                onClick={resetCards}
                className="text-[10px] font-bold text-muted-foreground hover:text-rose-400 uppercase tracking-wider cursor-pointer transition-colors"
              >
                Reset to defaults
              </button>
            </div>

            {/* Layout */}
            <div>
              <p className="text-[9px] uppercase font-bold text-muted-foreground/70 tracking-wider mb-1.5">Layout</p>
              <div className="flex flex-wrap gap-1.5">
                <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider self-center">Columns:</span>
                {[1, 2, 3].map((n) => (
                  <button
                    key={n}
                    onClick={() => updateCards({ columns: n as CardSettings['columns'] })}
                    className={`px-2.5 py-1.5 rounded-lg text-[11px] font-bold transition-all cursor-pointer border whitespace-nowrap ${
                      cards.columns === n ? 'bg-primary/15 text-primary border-primary/40' : 'text-muted-foreground border-border/40 hover:bg-accent/40'
                    }`}
                  >
                    {n === 1 ? 'Single' : `${n} cols`}
                  </button>
                ))}
                <span className="mx-2 w-px self-stretch bg-border/60" aria-hidden />
                <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider self-center">Density:</span>
                {(['compact', 'cozy'] as const).map((d) => (
                  <button
                    key={d}
                    onClick={() => updateCards({ density: d })}
                    className={`px-2.5 py-1.5 rounded-lg text-[11px] font-bold transition-all cursor-pointer border capitalize whitespace-nowrap ${
                      cards.density === d ? 'bg-primary/15 text-primary border-primary/40' : 'text-muted-foreground border-border/40 hover:bg-accent/40'
                    }`}
                  >
                    {d}
                  </button>
                ))}
                <span className="mx-2 w-px self-stretch bg-border/60" aria-hidden />
                <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider self-center">Summary:</span>
                {([2, 3, 4, 0] as const).map((n) => (
                  <button
                    key={n}
                    onClick={() => updateCards({ summaryLines: n })}
                    className={`px-2.5 py-1.5 rounded-lg text-[11px] font-bold transition-all cursor-pointer border whitespace-nowrap ${
                      cards.summaryLines === n ? 'bg-primary/15 text-primary border-primary/40' : 'text-muted-foreground border-border/40 hover:bg-accent/40'
                    }`}
                  >
                    {n === 0 ? 'Full' : `${n} lines`}
                  </button>
                ))}
              </div>
            </div>

            {/* Visibility toggles */}
            <div>
              <p className="text-[9px] uppercase font-bold text-muted-foreground/70 tracking-wider mb-1.5">Show on cards</p>
              <div className="flex flex-wrap gap-1.5">
                {([
                  ['showSummary', 'Summary'],
                  ['showBadges', 'Badges'],
                  ['showTimestamp', 'Timestamp'],
                  ['showSentiment', 'Sentiment'],
                  ['showButtons', 'Buttons'],
                  ['glow', 'Glow'],
                ] as [keyof CardSettings, string][]).map(([key, label]) => {
                  const on = Boolean(cards[key]);
                  return (
                    <button
                      key={key}
                      onClick={() => updateCards({ [key]: !on } as Partial<CardSettings>)}
                      className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-bold transition-all cursor-pointer border whitespace-nowrap ${
                        on ? 'bg-primary/10 border-primary/40 text-primary' : 'bg-transparent border-border/40 text-muted-foreground opacity-60 hover:opacity-100'
                      }`}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${on ? 'bg-primary' : 'bg-border'}`} />
                      {label}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        <div className={`${CARD_COLUMNS_CLASS[cards.columns]} grid gap-4.5 w-full`}>
          {newsList.length === 0 && (
            <div className="w-full text-center py-12 font-mono text-xs text-muted-foreground border border-dashed border-border/25 rounded-2xl bg-card/10">
              <p className="mb-3">No articles match the current filters.</p>
              <button onClick={clearFilters} className="px-4 py-2 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 rounded-xl text-[11px] font-semibold cursor-pointer transition-colors">
                Clear Filters
              </button>
            </div>
          )}
          {newsList.map(item => {
            const isBullish = item.sentiment === 'bullish';
            const isBearish = item.sentiment === 'bearish';
            const dens = DENSITY_CLASS[cards.density];

            // Dynamic card colors & glows based on sentiment score
            const borderStyle = isBullish
              ? 'border-emerald-500/25 dark:border-emerald-500/15 hover:border-emerald-500/60'
              : isBearish
              ? 'border-rose-500/25 dark:border-rose-500/15 hover:border-rose-500/60'
              : 'border-white/10 dark:border-white/5 hover:border-primary/50';

            const bgGradient = isBullish
              ? 'bg-gradient-to-br from-emerald-500/[0.03] via-[#0f0f0f]/60 to-[#0f0f0f]/30'
              : isBearish
              ? 'bg-gradient-to-br from-rose-500/[0.03] via-[#0f0f0f]/60 to-[#0f0f0f]/30'
              : 'bg-[#0f0f0f]/60';

            const summaryClass =
              cards.showSummary && cards.summaryLines > 0
                ? LINE_CLAMP_CLASS[cards.summaryLines]
                : '';

            return (
              <div
                key={item.id}
                onClick={() => setSelectedNews(item)}
                className={`rounded-2xl backdrop-blur-xl border hover:shadow-lg transition-all duration-300 flex flex-col justify-between relative overflow-hidden text-left shadow-sm group cursor-pointer hover:scale-[1.005] ${dens.card} ${borderStyle} ${bgGradient}`}
              >
                {/* Ambient glow badge based on sentiment */}
                {cards.glow && (
                  <div
                    className={`absolute top-0 right-0 -translate-y-1/2 translate-x-1/2 w-48 h-48 rounded-full blur-[60px] pointer-events-none opacity-20 transition-all duration-300 ${
                      isBullish ? 'bg-emerald-500' : isBearish ? 'bg-rose-500' : 'bg-primary'
                    }`}
                  />
                )}

                <div className="flex-1 min-w-0 space-y-2.5 relative z-10">
                  {cards.showBadges && (
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[10px] font-bold text-muted-foreground font-mono uppercase bg-accent/60 px-2 py-0.5 rounded border border-border/40">
                        {item.source}
                      </span>
                      {item.category && (
                        <span className="text-[10px] font-bold text-primary/80 font-mono uppercase bg-primary/5 border border-primary/15 px-2 py-0.5 rounded">
                          {item.category}
                        </span>
                      )}
                      {item.ticker && (
                        <span className="text-[10px] font-extrabold text-primary font-mono bg-primary/10 border border-primary/20 px-2 py-0.5 rounded">
                          {item.ticker}
                        </span>
                      )}
                      {cards.showTimestamp && (
                        <span className="text-[10px] text-muted-foreground font-mono">{item.timestamp}</span>
                      )}
                    </div>
                  )}

                  <h3 className={`font-semibold leading-snug text-foreground group-hover:text-primary transition-colors ${dens.title}`}>
                    {item.headline}
                  </h3>

                  {cards.showSummary && (
                    <p className={`${dens.body} text-muted-foreground leading-relaxed ${summaryClass}`}>
                      {item.summary || 'Open the article for the full story.'}
                    </p>
                  )}

                  {cards.showSentiment && (
                    <div className="flex items-center gap-3 pt-0.5">
                      <span
                        className={`text-[9px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full ${
                          isBullish
                            ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/35 shadow-[0_0_8px_rgba(16,185,129,0.08)]'
                            : isBearish
                            ? 'bg-rose-500/10 text-rose-400 border border-rose-500/35 shadow-[0_0_8px_rgba(244,63,94,0.08)]'
                            : 'bg-neutral-500/10 text-neutral-400 border border-neutral-500/35'
                        }`}
                      >
                        {item.sentiment}
                      </span>
                      <span className="text-[10px] text-muted-foreground/80 font-mono">
                        Swing Est: {item.impactPercent > 0 ? '+' : ''}{item.impactPercent}%
                      </span>
                    </div>
                  )}
                </div>

                {/* Footer action row — full width, below the content */}
                {cards.showButtons && (
                  <div className="flex items-center gap-2 border-t border-border/40 pt-3 relative z-10">
                    {item.ticker && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={(e) => { e.stopPropagation(); handleAnalyze(item); }}
                        className="text-[11px] h-8 rounded-lg px-4 font-mono border border-border hover:bg-accent cursor-pointer"
                      >
                        Chart {item.ticker}
                      </Button>
                    )}
                    {item.url && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={(e) => { e.stopPropagation(); window.open(item.url, '_blank'); }}
                        className="text-[11px] h-8 rounded-lg px-4 font-mono border border-border hover:bg-accent cursor-pointer text-primary"
                      >
                        Read Article
                      </Button>
                    )}
                    <span className="flex-1" />
                    <Button
                      size="sm"
                      onClick={(e) => { e.stopPropagation(); handleDiscuss(item); }}
                      className="text-[11px] h-8 rounded-lg px-4 inline-flex items-center justify-center gap-1.5 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 hover:border-primary/40 font-semibold cursor-pointer transition-all"
                    >
                      <Sparkles size={11} /> Discuss with AI
                    </Button>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Pagination Controls */}
        {totalPages > 1 && (() => {
          // Compact windowed page list: 1 … (p-1) p (p+1) … last
          const windowSize = 1;
          const pageNumbers: (number | '…')[] = [];
          const push = (n: number | '…') => {
            if (pageNumbers[pageNumbers.length - 1] !== n) pageNumbers.push(n);
          };
          push(1);
          if (page - windowSize > 2) push('…');
          for (let i = Math.max(2, page - windowSize); i <= Math.min(totalPages - 1, page + windowSize); i++) push(i);
          if (page + windowSize < totalPages - 1) push('…');
          if (totalPages > 1) push(totalPages);
          const pageBtn = (n: number, active: boolean) => (
            <button
              key={n}
              onClick={() => handlePageChange(n)}
              className={`h-8.5 min-w-[34px] px-2 rounded-lg text-[12px] font-mono font-semibold cursor-pointer transition-all border ${
                active
                  ? 'bg-primary/15 text-primary border-primary/40 shadow-[0_0_10px_rgba(139,92,246,0.15)]'
                  : 'bg-accent/30 text-muted-foreground border-border/30 hover:border-primary/30 hover:text-foreground'
              }`}
            >
              {n}
            </button>
          );
          const navBtn = (label: string, target: number, disabled: boolean, arrow: React.ReactNode) => (
            <button
              onClick={() => !disabled && handlePageChange(target)}
              disabled={disabled}
              className="h-8.5 px-3 rounded-lg text-[12px] font-semibold cursor-pointer transition-all border inline-flex items-center gap-1.5 bg-accent/30 text-muted-foreground border-border/30 hover:border-primary/30 hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:border-border/30 disabled:hover:text-muted-foreground"
            >
              {arrow} {label}
            </button>
          );
          return (
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 mt-8 p-4 bg-[#0f0f0f]/40 border border-border/10 rounded-2xl font-mono select-none">
              <span className="text-[11px] text-muted-foreground order-2 sm:order-1">
                Showing page <span className="text-foreground font-bold">{page}</span> of{' '}
                <span className="text-foreground font-bold">{totalPages}</span>
                {totalItems > 0 && <> · <span className="text-foreground font-bold">{totalItems}</span> articles</>}
              </span>

              <div className="flex items-center gap-1.5 order-1 sm:order-2">
                {navBtn('Prev', page - 1, page <= 1, <span aria-hidden>&larr;</span>)}
                {pageNumbers.map((n, idx) =>
                  n === '…' ? (
                    <span key={`ellipsis-${idx}`} className="h-8.5 min-w-[24px] inline-flex items-center justify-center text-muted-foreground/50 text-[12px]">…</span>
                  ) : (
                    pageBtn(n, n === page)
                  )
                )}
                {navBtn('Next', page + 1, page >= totalPages, <span aria-hidden>&rarr;</span>)}
              </div>
            </div>
          );
        })()}
      </div>
    );
  }

  return (
    <div className="w-full flex flex-col bg-[#0f0f0f]/60 dark:bg-[#0f0f0f]/60 bg-white/70 backdrop-blur-xl border border-white/10 dark:border-white/5 rounded-2xl p-4 overflow-hidden relative">
      <div className="flex items-center gap-2 mb-4 shrink-0">
        <Newspaper className="text-primary w-4.5 h-4.5" />
        <span className="font-serif text-sm font-semibold tracking-tight">AI Financial Briefings</span>
      </div>

      {/* News list */}
      <div className="space-y-3.5 overflow-y-auto max-h-[300px] scrollbar-hide pr-0.5">
        {newsList.map(item => {
          const isBullish = item.sentiment === 'bullish';
          const isBearish = item.sentiment === 'bearish';

          const cardBorder = isBullish
            ? 'border-emerald-500/15 hover:border-emerald-500/40 bg-emerald-950/[0.01]'
            : isBearish
            ? 'border-rose-500/15 hover:border-rose-500/40 bg-rose-950/[0.01]'
            : 'border-border/10 bg-background/10 hover:border-border/30';

          return (
            <div
              key={item.id}
              onClick={() => setSelectedNews(item)}
              className={`p-3 rounded-xl border hover:bg-accent/30 hover:shadow-md transition-all duration-300 flex flex-col gap-1.5 cursor-pointer text-left group ${cardBorder}`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold text-muted-foreground font-mono uppercase bg-accent/40 px-1.5 py-0.5 rounded">
                    {item.source}
                  </span>
                  {item.category && (
                    <span className="text-[10px] font-bold text-primary/80 font-mono uppercase bg-primary/5 border border-primary/15 px-1.5 py-0.5 rounded">
                      {item.category}
                    </span>
                  )}
                  {item.ticker && (
                    <span className="text-[10px] font-extrabold text-primary font-mono bg-primary/10 border border-primary/20 px-1.5 py-0.5 rounded">
                      {item.ticker}
                    </span>
                  )}
                </div>
                <span className="text-[9px] text-muted-foreground font-mono">{item.timestamp}</span>
              </div>

              <h3 className="text-xs font-semibold leading-snug text-foreground group-hover:text-primary transition-colors">
                {item.headline}
              </h3>

              {/* Sentiment Badge */}
              <div className="flex items-center justify-between mt-0.5">
                <span
                  className={`text-[9px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full ${
                    isBullish
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                      : isBearish
                      ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                      : 'bg-neutral-500/10 text-neutral-400 border border-neutral-500/20'
                  }`}
                >
                  {item.sentiment}
                </span>
                <span className="text-[9px] text-muted-foreground/80 font-mono">
                  Impact: {item.impactPercent > 0 ? '+' : ''}
                  {item.impactPercent}%
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* News Details / AI Briefing Modal */}
      {selectedNews && (
        <Dialog open={!!selectedNews} onOpenChange={open => !open && setSelectedNews(null)}>
          <DialogContent className="sm:max-w-[480px] bg-background/90 backdrop-blur-xl border border-border/40 text-foreground rounded-2xl shadow-2xl p-6 overflow-hidden">
            {/* Ambient Background Blur Glow */}
            <div
              className={`absolute top-0 right-0 -translate-y-1/2 translate-x-1/2 w-72 h-72 rounded-full blur-[70px] pointer-events-none ${
                selectedNews.sentiment === 'bullish'
                  ? 'bg-emerald-500/10'
                  : selectedNews.sentiment === 'bearish'
                  ? 'bg-rose-500/10'
                  : 'bg-primary/10'
              }`}
            />

            <DialogHeader className="text-left relative z-10 pt-2">
              <div className="flex items-center gap-2 mb-3">
                <span className="text-[10px] font-bold text-muted-foreground font-mono bg-accent px-2 py-1 rounded">
                  {selectedNews.source}
                </span>
                {selectedNews.category && (
                  <span className="text-[10px] font-bold text-primary/80 font-mono uppercase bg-primary/5 border border-primary/15 px-2 py-1 rounded">
                    {selectedNews.category}
                  </span>
                )}
                {selectedNews.ticker && (
                  <span className="text-[10px] font-extrabold text-primary font-mono bg-primary/10 border border-primary/20 px-2 py-1 rounded">
                    {selectedNews.ticker}
                  </span>
                )}
                <span className="text-[10px] text-muted-foreground font-mono ml-auto">{selectedNews.timestamp}</span>
              </div>
              <DialogTitle className="text-lg font-serif font-semibold leading-snug">
                {selectedNews.url ? (
                  <a 
                    href={selectedNews.url} 
                    target="_blank" 
                    rel="noopener noreferrer" 
                    className="hover:text-primary hover:underline decoration-primary transition-all cursor-pointer"
                  >
                    {selectedNews.headline}
                  </a>
                ) : (
                  selectedNews.headline
                )}
              </DialogTitle>
              <div className="flex items-center gap-3 mt-3 border-b border-border/20 pb-3">
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  Sentiment:
                  <span
                    className={`font-semibold capitalize px-2.5 py-0.5 rounded-full text-[10px] ${
                      selectedNews.sentiment === 'bullish'
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                        : selectedNews.sentiment === 'bearish'
                        ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                        : 'bg-neutral-500/10 text-neutral-400 border border-neutral-500/20'
                    }`}
                  >
                    {selectedNews.sentiment}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground ml-auto">
                  Est. Price Swing: <span className="font-bold font-mono text-foreground">{selectedNews.impactPercent}%</span>
                </div>
              </div>
            </DialogHeader>

            <div className="relative z-10 py-4 space-y-3.5 text-left text-xs leading-relaxed text-muted-foreground">
              <div>
                <span className="text-[10px] uppercase font-bold text-foreground tracking-wider block mb-1">Briefing Overview</span>
                <p>{selectedNews.summary}</p>
              </div>

              <div className="p-3 bg-primary/5 border border-primary/20 rounded-xl">
                <span className="text-[10px] uppercase font-bold text-primary tracking-wider flex items-center gap-1.5 mb-1.5">
                  <Sparkles size={12} /> AI Analyst Assessment
                </span>
                <p className="text-[11px] leading-relaxed text-foreground">
                  The news aligns with strong underlying trend momentum. We recommend initiating a deep asset sweep to identify optimal option strategies or evaluate watchlists for volume surges.
                </p>
              </div>
            </div>

            <div className="flex gap-2 mt-4 relative z-10 border-t border-border/20 pt-4 flex-wrap">
              <Button
                variant="outline"
                onClick={() => setSelectedNews(null)}
                className="flex-1 min-w-[80px] rounded-xl text-xs py-2.5 h-auto border border-border/40 cursor-pointer"
              >
                Close
              </Button>
              {selectedNews.url && (
                <Button
                  onClick={() => window.open(selectedNews.url, '_blank')}
                  className="flex-1 min-w-[100px] rounded-xl bg-accent hover:bg-accent/80 text-accent-foreground border border-border/40 text-xs py-2.5 h-auto cursor-pointer"
                >
                  Read Source
                </Button>
              )}
              {selectedNews.ticker && (
                <Button
                  onClick={() => handleAnalyze()}
                  className="flex-1 min-w-[100px] rounded-xl bg-accent hover:bg-accent/80 text-accent-foreground border border-border/40 text-xs py-2.5 h-auto cursor-pointer"
                >
                  <Eye size={13} className="mr-1.5" /> Chart {selectedNews.ticker}
                </Button>
              )}
              <Button
                onClick={() => handleDiscuss()}
                className="flex-1 min-w-[120px] inline-flex items-center justify-center gap-1.5 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 hover:border-primary/40 text-xs py-2.5 h-auto rounded-xl font-semibold cursor-pointer transition-all hover:scale-105"
              >
                <Sparkles size={13} /> Discuss
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
