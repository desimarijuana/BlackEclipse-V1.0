'use client';

import React, { useState, useEffect } from 'react';
import { Plus, Trash2, ArrowUpRight, ArrowDownRight, TrendingUp, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/components/auth/auth-context';

export interface WatchlistItem {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  sparkline: number[];
}

const DEFAULT_WATCHLIST: WatchlistItem[] = [
  { symbol: 'AAPL', name: 'Apple Inc.', price: 189.84, change: 2.34, changePercent: 1.25, sparkline: [186, 187, 185, 188, 189.84] },
  { symbol: 'NVDA', name: 'NVIDIA Corp.', price: 1096.50, change: 48.20, changePercent: 4.60, sparkline: [1020, 1040, 1035, 1070, 1096.5] },
  { symbol: 'TSLA', name: 'Tesla Inc.', price: 178.50, change: -4.30, changePercent: -2.35, sparkline: [185, 182, 180, 182, 178.5] },
  { symbol: 'MSFT', name: 'Microsoft Corp.', price: 429.20, change: -1.80, changePercent: -0.42, sparkline: [431, 432, 428, 430, 429.2] },
];

const PRESETS: Record<string, Omit<WatchlistItem, 'sparkline'>> = {
  AAPL: { symbol: 'AAPL', name: 'Apple Inc.', price: 189.84, change: 2.34, changePercent: 1.25 },
  NVDA: { symbol: 'NVDA', name: 'NVIDIA Corp.', price: 1096.50, change: 48.20, changePercent: 4.60 },
  TSLA: { symbol: 'TSLA', name: 'Tesla Inc.', price: 178.50, change: -4.30, changePercent: -2.35 },
  MSFT: { symbol: 'MSFT', name: 'Microsoft Corp.', price: 429.20, change: -1.80, changePercent: -0.42 },
  AMZN: { symbol: 'AMZN', name: 'Amazon.com, Inc.', price: 182.15, change: 1.95, changePercent: 1.08 },
  GOOGL: { symbol: 'GOOGL', name: 'Alphabet Inc.', price: 173.50, change: 0.90, changePercent: 0.52 },
  META: { symbol: 'META', name: 'Meta Platforms', price: 475.40, change: -8.20, changePercent: -1.70 },
  NFLX: { symbol: 'NFLX', name: 'Netflix Inc.', price: 645.20, change: 12.40, changePercent: 1.96 },
  AMD: { symbol: 'AMD', name: 'Advanced Micro Devices', price: 166.30, change: -3.10, changePercent: -1.83 },
  BTC: { symbol: 'BTC', name: 'Bitcoin', price: 67840.00, change: 1420.00, changePercent: 2.14 },
  ETH: { symbol: 'ETH', name: 'Ethereum', price: 3780.50, change: -45.50, changePercent: -1.19 },
};

interface PortfolioWatchlistProps {
  onAnalyzeTicker?: (ticker: string) => void;
  onSelectTicker?: (ticker: string) => void;
  fullPage?: boolean;
}

export function PortfolioWatchlist({ onAnalyzeTicker, onSelectTicker, fullPage = false }: PortfolioWatchlistProps) {
  const { user, requireAuth } = useAuth();
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>(DEFAULT_WATCHLIST);
  const [newTicker, setNewTicker] = useState('');
  const [suggestion, setSuggestion] = useState<string[]>([]);
  const [error, setError] = useState('');

  // Load watchlist on mount or when user changes
  useEffect(() => {
    const key = user ? `watchlist_${user.id}` : 'watchlist_guest';
    const saved = localStorage.getItem(key);
    if (saved) {
      try {
        setWatchlist(JSON.parse(saved));
      } catch {
        setWatchlist(DEFAULT_WATCHLIST);
      }
    } else {
      setWatchlist(DEFAULT_WATCHLIST);
    }
  }, [user]);

  const saveWatchlist = (items: WatchlistItem[]) => {
    setWatchlist(items);
    const key = user ? `watchlist_${user.id}` : 'watchlist_guest';
    localStorage.setItem(key, JSON.stringify(items));
  };

  const handleInputChange = (val: string) => {
    setNewTicker(val.toUpperCase());
    setError('');
    if (!val.trim()) {
      setSuggestion([]);
      return;
    }
    const filtered = Object.keys(PRESETS).filter(
      sym => sym.startsWith(val.toUpperCase()) && !watchlist.some(item => item.symbol === sym)
    );
    setSuggestion(filtered);
  };

  const handleAddTicker = (symbolToAdd?: string) => {
    const symbol = (symbolToAdd || newTicker).toUpperCase().trim();
    if (!symbol) return;

    requireAuth(() => {
      if (watchlist.some(item => item.symbol === symbol)) {
        setError('Stock already in watchlist');
        return;
      }

      // Generate a mock entry
      let newItem: WatchlistItem;
      if (PRESETS[symbol]) {
        const p = PRESETS[symbol];
        const basePrice = p.price;
        // Generate a random sparkline around base price
        const spark = [
          basePrice * 0.98,
          basePrice * 0.99,
          basePrice * 0.975,
          basePrice * 1.01,
          basePrice,
        ];
        newItem = {
          ...p,
          sparkline: spark,
        };
      } else {
        // Mock fallback for custom symbols
        const price = Math.random() * 400 + 10;
        const change = (Math.random() * 20 - 10);
        newItem = {
          symbol,
          name: `${symbol} Corp`,
          price,
          change,
          changePercent: parseFloat(((change / price) * 100).toFixed(2)),
          sparkline: [
            price * 0.97,
            price * 1.02,
            price * 0.99,
            price * 0.98,
            price,
          ],
        };
      }

      const updated = [...watchlist, newItem];
      saveWatchlist(updated);
      setNewTicker('');
      setSuggestion([]);
      setError('');
    });
  };

  const handleRemoveTicker = (e: React.MouseEvent, symbol: string) => {
    e.stopPropagation();
    requireAuth(() => {
      const updated = watchlist.filter(item => item.symbol !== symbol);
      saveWatchlist(updated);
    });
  };

  if (fullPage) {
    return (
      <div className="w-full flex flex-col gap-6 select-none animate-fade-in-up">
        {/* Search input header */}
        <div className="p-5 rounded-2xl bg-[#0f0f0f]/60 dark:bg-[#0f0f0f]/60 bg-white/70 backdrop-blur-xl border border-white/10 dark:border-white/5 flex items-center justify-between gap-4 flex-wrap shadow-md">
          <div className="flex items-center gap-3">
            <span className="text-xs font-semibold text-muted-foreground font-mono bg-accent/60 px-2.5 py-1.5 rounded-lg border border-border/40">
              {watchlist.length} Watched Assets
            </span>
          </div>
          <div className="relative flex items-center gap-2 max-w-sm w-full">
            <div className="relative flex-1">
              <input
                type="text"
                placeholder="Add Ticker (e.g. AMZN, BTC)"
                value={newTicker}
                onChange={e => handleInputChange(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleAddTicker()}
                className="w-full bg-background/60 border border-border rounded-xl px-3 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary placeholder:text-muted-foreground/60 transition-all font-mono"
              />
              {suggestion.length > 0 && (
                <div className="absolute top-full left-0 right-0 z-20 mt-1 bg-popover border border-border rounded-xl shadow-lg p-1.5 max-h-36 overflow-y-auto backdrop-blur-xl">
                  {suggestion.map(sym => (
                    <button
                      key={sym}
                      onClick={() => handleAddTicker(sym)}
                      className="w-full text-left px-2.5 py-1.5 rounded-lg text-xs hover:bg-accent text-foreground flex items-center justify-between font-mono cursor-pointer"
                    >
                      <span>{sym}</span>
                      <span className="text-[10px] text-muted-foreground">{PRESETS[sym].name}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <Button
              size="sm"
              onClick={() => handleAddTicker()}
              className="rounded-xl h-8.5 bg-primary hover:bg-primary/95 text-primary-foreground shrink-0 cursor-pointer px-4"
            >
              Add Asset
            </Button>
          </div>
        </div>

        {watchlist.length === 0 ? (
          <div className="py-20 text-center text-muted-foreground text-sm rounded-2xl bg-[#0f0f0f]/40 dark:bg-[#0f0f0f]/40 bg-white/50 backdrop-blur-xl border border-white/10 dark:border-white/5">
            Your watchlist is empty. Add assets above to track metrics.
          </div>
        ) : (
          <div className="flex flex-col gap-4.5 w-full">
            {watchlist.map(item => {
              const isPositive = item.changePercent >= 0;
              return (
                <div
                  key={item.symbol}
                  onClick={() => onSelectTicker?.(item.symbol)}
                  className="group p-4 px-6 rounded-2xl bg-[#0f0f0f]/60 dark:bg-[#0f0f0f]/60 bg-white/70 backdrop-blur-xl border border-white/10 dark:border-white/5 hover:border-primary/50 hover:shadow-lg hover:shadow-primary/5 transition-all duration-300 flex flex-col md:flex-row md:items-center justify-between gap-4 cursor-pointer relative overflow-hidden"
                >
                  {/* Left Section: Symbol, Name */}
                  <div className="flex items-center gap-4 min-w-[200px] shrink-0">
                    <div className="w-10 h-10 rounded-xl bg-accent border border-border/80 flex items-center justify-center font-bold text-foreground shrink-0">
                      {item.symbol.slice(0, 2)}
                    </div>
                    <div className="truncate">
                      <span className="font-mono text-sm font-bold tracking-tight text-foreground block">{item.symbol}</span>
                      <span className="text-[11px] text-muted-foreground truncate block max-w-[150px]">{item.name}</span>
                    </div>
                  </div>

                  {/* Sparkline (Wider) */}
                  <div className="flex-1 max-w-sm h-10 shrink-0 mx-2 hidden sm:block">
                    <svg className="w-full h-full overflow-visible">
                      <polyline
                        fill="none"
                        stroke={isPositive ? 'oklch(0.7 0.16 150)' : 'oklch(0.65 0.18 10)'}
                        strokeWidth="2"
                        points={item.sparkline
                          .map((price, idx) => {
                            const min = Math.min(...item.sparkline);
                            const max = Math.max(...item.sparkline);
                            const range = max - min || 1;
                            const x = (idx / (item.sparkline.length - 1)) * 320;
                            const y = 36 - ((price - min) / range) * 28 - 4;
                            return `${x},${y}`;
                          })
                          .join(' ')}
                      />
                    </svg>
                  </div>

                  {/* Pricing and changes */}
                  <div className="flex items-center gap-6 shrink-0 justify-between md:justify-end">
                    <div className="text-right">
                      <span className="font-mono text-sm font-extrabold text-foreground block">
                        ${item.price.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                      </span>
                      <span className="text-[10px] text-muted-foreground block font-mono">Last Price</span>
                    </div>

                    <div
                      className={`flex items-center gap-0.5 text-xs font-bold font-mono px-3 py-1 rounded-full border ${
                        isPositive
                          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/35'
                          : 'bg-rose-500/10 text-rose-400 border-rose-500/35'
                      }`}
                    >
                      {isPositive ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                      {isPositive ? '+' : ''}{item.changePercent}%
                    </div>
                  </div>

                  {/* Actions (Discuss, Remove) */}
                  <div className="flex items-center gap-3 shrink-0 pt-3 md:pt-0 border-t border-border/10 md:border-0 justify-end">
                    <Button
                      size="sm"
                      onClick={e => {
                        e.stopPropagation();
                        onAnalyzeTicker?.(item.symbol);
                      }}
                      className="inline-flex items-center gap-1.5 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 hover:border-primary/40 px-3 py-1.5 h-8.5 rounded-xl text-[11px] cursor-pointer font-semibold transition-all hover:scale-105"
                    >
                      <Sparkles size={12} className="mr-1.5 inline" /> AI Analyze
                    </Button>
                    <button
                      onClick={e => handleRemoveTicker(e, item.symbol)}
                      className="p-2 rounded-xl bg-destructive/10 text-destructive border border-destructive/20 hover:bg-destructive hover:text-destructive-foreground transition-colors cursor-pointer"
                      title="Remove Ticker"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>

                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="w-full flex flex-col bg-[#0f0f0f]/60 dark:bg-[#0f0f0f]/60 bg-white/70 backdrop-blur-xl border border-white/10 dark:border-white/5 rounded-2xl p-4 overflow-hidden relative">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <TrendingUp className="text-primary w-4.5 h-4.5" />
          <span className="font-serif text-sm font-semibold tracking-tight">Portfolio Watchlist</span>
        </div>
        <span className="text-[10px] text-muted-foreground bg-accent/60 px-2 py-0.5 rounded-full font-mono border border-border/30">
          {watchlist.length} Tickers
        </span>
      </div>

      {/* Add Stock Inputs */}
      <div className="relative mb-3.5 border-b border-border/20 pb-3">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              placeholder="Add Ticker (e.g. AMZN, GOOGL)"
              value={newTicker}
              onChange={e => handleInputChange(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleAddTicker()}
              className="w-full bg-background/50 border border-border rounded-xl px-3 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary placeholder:text-muted-foreground/60 transition-all font-mono"
            />
            {suggestion.length > 0 && (
              <div className="absolute top-full left-0 right-0 z-20 mt-1 bg-popover border border-border rounded-xl shadow-lg p-1.5 max-h-36 overflow-y-auto backdrop-blur-xl">
                {suggestion.map(sym => (
                  <button
                    key={sym}
                    onClick={() => handleAddTicker(sym)}
                    className="w-full text-left px-2.5 py-1.5 rounded-lg text-xs hover:bg-accent text-foreground flex items-center justify-between font-mono cursor-pointer"
                  >
                    <span>{sym}</span>
                    <span className="text-[10px] text-muted-foreground">{PRESETS[sym].name}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <Button
            size="icon-sm"
            onClick={() => handleAddTicker()}
            className="rounded-xl h-8 w-8 bg-primary hover:bg-primary/95 text-primary-foreground shrink-0 cursor-pointer"
          >
            <Plus size={14} />
          </Button>
        </div>
        {error && <span className="text-[10px] text-destructive mt-1 block font-medium">{error}</span>}
      </div>

      {/* Watchlist Item List */}
      <div className="space-y-2 overflow-y-auto max-h-[220px] scrollbar-hide pr-0.5">
        {watchlist.length === 0 ? (
          <div className="py-6 text-center text-muted-foreground text-xs border border-dashed border-border rounded-xl">
            Watchlist is empty
          </div>
        ) : (
          watchlist.map(item => {
            const isPositive = item.changePercent >= 0;
            return (
              <div
                key={item.symbol}
                onClick={() => onSelectTicker?.(item.symbol)}
                className="group p-2.5 rounded-xl border border-border bg-background/20 hover:bg-accent/30 hover:border-primary/30 transition-all duration-300 flex items-center justify-between cursor-pointer"
              >
                {/* Left Side: Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-xs font-bold tracking-tight text-foreground">{item.symbol}</span>
                    <TooltipAction ticker={item.symbol} onClick={onAnalyzeTicker} />
                  </div>
                  <p className="text-[10px] text-muted-foreground truncate max-w-[90px]">{item.name}</p>
                </div>

                {/* Center Side: Sparkline chart */}
                <div className="w-16 h-8 mx-2 shrink-0">
                  <svg className="w-full h-full overflow-visible">
                    <polyline
                      fill="none"
                      stroke={isPositive ? 'oklch(0.7 0.16 150)' : 'oklch(0.65 0.18 10)'}
                      strokeWidth="1.5"
                      points={item.sparkline
                        .map((price, idx) => {
                          const min = Math.min(...item.sparkline);
                          const max = Math.max(...item.sparkline);
                          const range = max - min || 1;
                          const x = (idx / (item.sparkline.length - 1)) * 64;
                          const y = 32 - ((price - min) / range) * 24 - 4; // Margin pad
                          return `${x},${y}`;
                        })
                        .join(' ')}
                    />
                  </svg>
                </div>

                {/* Right Side: Price metrics */}
                <div className="text-right shrink-0 flex flex-col items-end pl-1 relative">
                  <span className="font-mono text-xs font-semibold text-foreground">
                    ${item.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                  <div
                    className={`flex items-center gap-0.5 text-[10px] font-medium font-mono px-1.5 py-0.5 rounded-full mt-0.5 border ${
                      isPositive
                        ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                        : 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                    }`}
                  >
                    {isPositive ? <ArrowUpRight size={10} /> : <ArrowDownRight size={10} />}
                    {isPositive ? '+' : ''}
                    {item.changePercent}%
                  </div>

                  {/* Absolute Trash Icon Overlay on Hover */}
                  <button
                    onClick={e => handleRemoveTicker(e, item.symbol)}
                    className="absolute inset-y-0 right-0 flex items-center justify-center bg-background/95 hover:bg-destructive hover:text-destructive-foreground text-muted-foreground w-8 rounded-lg border border-border opacity-0 group-hover:opacity-100 transition-opacity duration-300 cursor-pointer shadow-md"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function TooltipAction({ ticker, onClick }: { ticker: string; onClick?: (t: string) => void }) {
  return (
    <button
      onClick={e => {
        e.stopPropagation();
        onClick?.(ticker);
      }}
      className="p-0.5 rounded-md hover:bg-primary/20 text-primary transition-colors cursor-pointer outline-none border border-transparent hover:border-primary/20"
      title="Analyze Stock with AI"
    >
      <Sparkles size={11} />
    </button>
  );
}

