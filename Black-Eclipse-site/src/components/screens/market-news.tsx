'use client';

import React, { useState, useEffect } from 'react';
import { Newspaper, Sparkles, MessageSquare, Eye } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { TopLoader } from '@/components/ui/top-loader';
import { Skeleton } from '@/components/ui/skeleton';

export interface NewsItem {
  id: string;
  source: string;
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

export function MarketNews({ onDiscussNews, onAnalyzeTicker, fullPage = false, onNewsStatusChange }: MarketNewsProps) {
  const [selectedNews, setSelectedNews] = useState<NewsItem | null>(null);
  const [newsList, setNewsList] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const fetchNews = (pageNum = 1) => {
    setLoading(true);
    setNewsList(NEWS_MOCK);
    setPage(pageNum);
    setTotalPages(1);
    setError(null);

    const bullishCount = NEWS_MOCK.filter(n => n.sentiment === 'bullish').length;
    const bearishCount = NEWS_MOCK.filter(n => n.sentiment === 'bearish').length;
    onNewsStatusChange?.(bullishCount >= bearishCount);
    setLoading(false);
  };

  useEffect(() => {
    fetchNews(1);
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
        <div className="flex flex-col gap-4.5 w-full">
          {newsList.map(item => {
            const isBullish = item.sentiment === 'bullish';
            const isBearish = item.sentiment === 'bearish';
            
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

            return (
              <div
                key={item.id}
                onClick={() => setSelectedNews(item)}
                className={`p-5 rounded-2xl backdrop-blur-xl border hover:shadow-lg transition-all duration-300 flex flex-col md:flex-row md:items-center justify-between gap-6 relative overflow-hidden text-left shadow-sm group cursor-pointer hover:scale-[1.005] ${borderStyle} ${bgGradient}`}
              >
                {/* Ambient glow badge based on sentiment */}
                <div
                  className={`absolute top-0 right-0 -translate-y-1/2 translate-x-1/2 w-48 h-48 rounded-full blur-[60px] pointer-events-none opacity-20 transition-all duration-300 ${
                    isBullish ? 'bg-emerald-500' : isBearish ? 'bg-rose-500' : 'bg-primary'
                  }`}
                />

                <div className="flex-1 min-w-0 space-y-2.5 relative z-10">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-bold text-muted-foreground font-mono uppercase bg-accent/60 px-2 py-0.5 rounded border border-border/40">
                      {item.source}
                    </span>
                    {item.ticker && (
                      <span className="text-[10px] font-extrabold text-primary font-mono bg-primary/10 border border-primary/20 px-2 py-0.5 rounded">
                        {item.ticker}
                      </span>
                    )}
                    <span className="text-[10px] text-muted-foreground font-mono">{item.timestamp}</span>
                  </div>

                  <h3 className="text-base font-semibold leading-snug text-foreground group-hover:text-primary transition-colors">
                    {item.headline}
                  </h3>

                  <p className="text-xs text-muted-foreground leading-relaxed">
                    {item.summary}
                  </p>
                </div>

                <div className="flex flex-col sm:flex-row md:flex-col items-stretch sm:items-center md:items-end gap-3 shrink-0 min-w-[200px] border-t md:border-t-0 md:border-l border-border/40 pt-4 md:pt-0 md:pl-6 relative z-10 justify-between">
                  {/* Sentiment metrics row */}
                  <div className="flex items-center justify-between md:justify-end gap-3 w-full">
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

                  {/* Action buttons row */}
                  <div className="flex gap-2 w-full mt-1">
                    {item.ticker && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={(e) => { e.stopPropagation(); handleAnalyze(item); }}
                        className="flex-1 text-[11px] h-8.5 rounded-xl font-mono border border-border hover:bg-accent cursor-pointer"
                      >
                        Chart
                      </Button>
                    )}
                    {item.url && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={(e) => { e.stopPropagation(); window.open(item.url, '_blank'); }}
                        className="flex-1 text-[11px] h-8.5 rounded-xl font-mono border border-border hover:bg-accent cursor-pointer text-primary"
                      >
                        Read Article
                      </Button>
                    )}
                    <Button
                      size="sm"
                      onClick={(e) => { e.stopPropagation(); handleDiscuss(item); }}
                      className="flex-1 inline-flex items-center justify-center gap-1.5 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 hover:border-primary/40 text-[11px] h-8.5 rounded-xl font-semibold cursor-pointer transition-all hover:scale-105"
                    >
                      <Sparkles size={11} /> Discuss with AI
                    </Button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Pagination Controls */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between mt-8 p-4 bg-[#0f0f0f]/40 border border-border/10 rounded-2xl font-mono text-xs select-none">
            <Button
              onClick={() => handlePageChange(page - 1)}
              disabled={page <= 1}
              variant="outline"
              className="px-4 py-2 rounded-xl text-xs cursor-pointer disabled:opacity-40"
            >
              &larr; Previous Page
            </Button>
            <span className="text-muted-foreground">
              Page <span className="text-foreground font-bold">{page}</span> of <span className="text-foreground font-bold">{totalPages}</span>
            </span>
            <Button
              onClick={() => handlePageChange(page + 1)}
              disabled={page >= totalPages}
              variant="outline"
              className="px-4 py-2 rounded-xl text-xs cursor-pointer disabled:opacity-40"
            >
              Next Page &rarr;
            </Button>
          </div>
        )}
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
