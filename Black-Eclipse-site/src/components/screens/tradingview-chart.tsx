'use client';

import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { X, TrendingUp, TrendingDown, BarChart2, ShieldAlert, DollarSign, Globe, Percent, Flame, Layers, Info, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn, getTradingViewSymbol } from '@/lib/utils';

interface TradingViewChartProps {
  symbol: string;
  onClose: () => void;
  stockName?: string;
  peRatio?: string;
  marketCap?: string;
  dividendYield?: string;
  shortFloat?: string;
  price?: number;
  changePercent?: number;
  volume?: string;
  sector?: string;
  industry?: string;
  country?: string;
  circulatingSupply?: string;
  totalSupply?: string;
  maxSupply?: string;
  ath?: string;
  atl?: string;
  rank?: number;
  athChangePercent?: number;
  atlChangePercent?: number;
  athDate?: string;
  atlDate?: string;
  marketCapRaw?: number;
  volumeRaw?: number;
  circulatingSupplyRaw?: number;
  maxSupplyRaw?: number;
}

export function TradingViewChart({ 
  symbol, 
  onClose,
  stockName,
  peRatio = 'N/A',
  marketCap = 'N/A',
  dividendYield = 'N/A',
  shortFloat = 'N/A',
  price = 0,
  changePercent = 0,
  volume = 'N/A',
  sector = '',
  industry = '',
  country = '',
  circulatingSupply = 'N/A',
  totalSupply = 'N/A',
  maxSupply = 'N/A',
  ath = 'N/A',
  atl = 'N/A',
  rank = 9999,
  athChangePercent = 0,
  atlChangePercent = 0,
  athDate = '',
  atlDate = '',
  marketCapRaw = 0,
  volumeRaw = 0,
  circulatingSupplyRaw = 0,
  maxSupplyRaw = 0
}: TradingViewChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [activeTab, setActiveTab] = useState<'chart' | 'fundamentals'>('chart');
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);
  
  const isCrypto = symbol.endsWith('USD') || symbol.endsWith('USDT') || symbol.includes('-');

  // Interactive Chart script loading
  useEffect(() => {
    if (!containerRef.current || activeTab !== 'chart') return;

    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/tv.js';
    script.type = 'text/javascript';
    script.async = true;
    script.onload = () => {
      interface TradingViewWindow extends Window {
        TradingView?: {
          widget: new (options: Record<string, string | number | boolean>) => unknown;
        };
      }
      const tvWindow = window as unknown as TradingViewWindow;
      if (typeof window !== 'undefined' && tvWindow.TradingView) {
        new tvWindow.TradingView.widget({
          width: '100%',
          height: '100%',
          symbol: getTradingViewSymbol(symbol, isCrypto || country === 'CRYPTO'),
          interval: 'D',
          timezone: 'Etc/UTC',
          theme: 'dark',
          style: '1',
          locale: 'en',
          toolbar_bg: '#111',
          enable_publishing: false,
          hide_side_toolbar: false,
          allow_symbol_change: true,
          container_id: 'tradingview_widget_container',
        });
      }
    };
    document.head.appendChild(script);

    return () => {
      script.remove();
    };
  }, [symbol, activeTab, mounted]);

  const isPositive = changePercent >= 0;

  if (!mounted) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 bg-black/90 backdrop-blur-md flex flex-col h-[100dvh] w-full text-foreground animate-fade-in font-sans">
      {/* Header Panel */}
      <div className="flex items-center justify-between border-b border-border/30 px-6 py-4 bg-card/45 backdrop-blur-md shadow-sm shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-none bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
            <BarChart2 className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xl font-bold bg-accent/60 px-2 py-0.5 rounded text-foreground">{symbol}</span>
              <h1 className="font-serif text-lg font-semibold text-foreground truncate max-w-[200px] md:max-w-[400px]">
                {stockName || symbol}
              </h1>
              {sector && (
                <span className="text-[10px] bg-accent/40 text-muted-foreground px-2 py-0.5 rounded hidden md:inline">
                  {sector}
                </span>
              )}
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              Interactive terminal node for stock & digital assets. Bloomberg-lite pricing matrix.
            </p>
          </div>
        </div>
        
        {/* Real-time ticker details in header */}
        <div className="hidden md:flex items-center gap-6 text-right mr-4">
          <div>
            <div className="text-[9px] uppercase font-bold tracking-wider text-muted-foreground">Last Price</div>
            <div className="font-mono text-base font-extrabold text-foreground">${price.toFixed(price < 1 ? 4 : 2)}</div>
          </div>
          <div>
            <div className="text-[9px] uppercase font-bold tracking-wider text-muted-foreground">24H Change</div>
            <div className={`font-mono text-sm font-bold ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
              {isPositive ? '▲ +' : '▼ '}{changePercent.toFixed(2)}%
            </div>
          </div>
        </div>

        <button
          onClick={onClose}
          className="p-2 rounded-none hover:bg-accent text-muted-foreground hover:text-foreground cursor-pointer transition-colors border border-border/40"
        >
          <X size={18} />
        </button>
      </div>

      {/* Main Grid: Control Tabs & Displays */}
      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden min-h-0">
        {/* Left Column: Interactive Area based on selected Tab */}
        <div className="flex-1 h-full relative border-r border-border/20 bg-black/20 flex flex-col">
          {/* Internal Tab Menu */}
          <div className="flex items-center gap-1.5 p-3 bg-card/25 border-b border-border/10">
            <button
              onClick={() => setActiveTab('chart')}
              className={`px-4 py-1.5 rounded-none text-xs font-bold transition-all ${
                activeTab === 'chart' ? 'bg-primary text-primary-foreground shadow-md' : 'text-muted-foreground hover:text-foreground hover:bg-accent/40'
              }`}
            >
              Interactive Chart
            </button>
            <button
              onClick={() => setActiveTab('fundamentals')}
              className={`px-4 py-1.5 rounded-none text-xs font-bold transition-all ${
                activeTab === 'fundamentals' ? 'bg-primary text-primary-foreground shadow-md' : 'text-muted-foreground hover:text-foreground hover:bg-accent/40'
              }`}
            >
              All Metrics
            </button>
          </div>

          <div className="flex-1 w-full h-full relative min-h-0 overflow-y-auto">
            {activeTab === 'chart' && (
              <div id="tradingview_widget_container" ref={containerRef} className="w-full h-full bg-background" />
            )}

            {activeTab === 'fundamentals' && (
              <div className="p-6 md:p-8 space-y-6">
                <div>
                  <h3 className="text-sm font-bold text-primary flex items-center gap-2 border-b border-border/20 pb-2">
                    <Layers size={14} /> {(isCrypto || country === 'CRYPTO') ? 'Market Intelligence & Tokenomics' : 'Full Fundamental Profile'}
                  </h3>
                </div>

                {(isCrypto || country === 'CRYPTO') ? (
                  <div className="space-y-6">
                    {/* Market Intelligence Grid */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      {/* Market Cap Card */}
                      <div className="space-y-1 p-4 rounded-none border border-border/60 bg-card/30">
                        <span className="text-[9px] uppercase font-bold text-muted-foreground tracking-widest block font-mono">Market Cap</span>
                        <div className="text-xl font-bold text-foreground font-mono">{marketCap}</div>
                        <p className="text-[10px] text-muted-foreground">Measures total network value.</p>
                      </div>

                      {/* Liquidity Card */}
                      <div className="space-y-1 p-4 rounded-none border border-border/60 bg-card/30">
                        <span className="text-[9px] uppercase font-bold text-muted-foreground tracking-widest block font-mono">24H Trading Volume</span>
                        <div className="text-xl font-bold text-foreground font-mono">{volume}</div>
                        <p className="text-[10px] text-muted-foreground">Indicates market activity and liquidity.</p>
                      </div>

                      {/* Circulating Ratio Card */}
                      <div className="space-y-1.5 p-4 rounded-none border border-border/60 bg-card/30">
                        <span className="text-[9px] uppercase font-bold text-muted-foreground tracking-widest block font-mono">Circulating Ratio</span>
                        {(() => {
                          const ratio = maxSupplyRaw && maxSupplyRaw > 0 ? (circulatingSupplyRaw || 0) / maxSupplyRaw : 1;
                          const ratioPercent = (ratio * 100).toFixed(1);
                          const filledBars = Math.round(ratio * 10);
                          const emptyBars = 10 - filledBars;
                          const barStr = '██████████'.slice(0, filledBars) + '░░░░░░░░░░'.slice(0, emptyBars);
                          return (
                            <>
                              <div className="text-xl font-bold text-foreground font-mono">{ratioPercent}%</div>
                              <div className="flex flex-col gap-1">
                                <div className="text-primary font-mono text-xs">{barStr}</div>
                                <p className="text-[10px] text-muted-foreground">Supply already released into the market.</p>
                              </div>
                            </>
                          );
                        })()}
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      {/* Circulating Supply Card */}
                      <div className="space-y-1 p-4 rounded-none border border-border/60 bg-card/30 font-mono">
                        <span className="text-[9px] uppercase font-bold text-muted-foreground tracking-widest block font-sans">Circulating Supply</span>
                        <div className="text-lg font-bold text-foreground">{circulatingSupply}</div>
                      </div>

                      {/* Total Supply Card */}
                      <div className="space-y-1 p-4 rounded-none border border-border/60 bg-card/30 font-mono">
                        <span className="text-[9px] uppercase font-bold text-muted-foreground tracking-widest block font-sans">Total Supply</span>
                        <div className="text-lg font-bold text-foreground">{totalSupply}</div>
                      </div>

                      {/* Max Supply Card */}
                      <div className="space-y-1 p-4 rounded-none border border-border/60 bg-card/30 font-mono">
                        <span className="text-[9px] uppercase font-bold text-muted-foreground tracking-widest block font-sans">Max Supply</span>
                        <div className="text-lg font-bold text-foreground">{maxSupply}</div>
                      </div>
                    </div>

                    {/* Historical Price Intelligence Section */}
                    <div>
                      <h3 className="text-sm font-bold text-primary flex items-center gap-2 border-b border-border/20 pb-2">
                        <TrendingUp size={14} /> Historical Price Intelligence
                      </h3>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {/* ATH Card */}
                      <div className="space-y-1 p-4 rounded-none border border-border/60 bg-card/30">
                        <span className="text-[9px] uppercase font-bold text-muted-foreground tracking-widest block font-mono">All-Time High (ATH)</span>
                        <div className="text-xl font-bold text-foreground font-mono">{ath}</div>
                        <p className="text-[11px] text-rose-400 font-bold flex items-center gap-1">
                          <TrendingDown className="w-3.5 h-3.5 text-rose-400" /> {Math.abs(athChangePercent).toFixed(1)}% below ATH
                        </p>
                        <p className="text-[10px] text-muted-foreground/70">Date: {athDate ? new Date(athDate).toLocaleDateString() : 'N/A'}</p>
                      </div>

                      {/* ATL Card */}
                      <div className="space-y-1 p-4 rounded-none border border-border/60 bg-card/30">
                        <span className="text-[9px] uppercase font-bold text-muted-foreground tracking-widest block font-mono">All-Time Low (ATL)</span>
                        <div className="text-xl font-bold text-foreground font-mono">{atl}</div>
                        <p className="text-[11px] text-emerald-400 font-bold flex items-center gap-1">
                          <TrendingUp className="w-3.5 h-3.5 text-emerald-400" /> {Math.abs(atlChangePercent).toFixed(1)}% above ATL
                        </p>
                        <p className="text-[10px] text-muted-foreground/70">Date: {atlDate ? new Date(atlDate).toLocaleDateString() : 'N/A'}</p>
                      </div>
                    </div>

                    {/* Range visual */}
                    <div className="p-5 rounded-none border border-border/60 bg-card/30 space-y-3">
                      <span className="text-[10px] uppercase font-bold text-muted-foreground tracking-widest block font-mono">Price Position Within Historical Range</span>
                      {(() => {
                        const athNum = parseFloat(String(ath).replace(/[^0-9.]/g, '')) || price * 1.5;
                        const atlNum = parseFloat(String(atl).replace(/[^0-9.]/g, '')) || price * 0.1;
                        const rangePercent = Math.round(((price - atlNum) / (athNum - atlNum || 1)) * 100);
                        
                        // ATL ─────────●────── ATH
                        const sliderLength = 30;
                        const activeDotIndex = Math.round((Math.min(100, Math.max(0, rangePercent)) / 100) * sliderLength);
                        const sliderStr = '──────────────────────────────'.split('')
                          .map((char, index) => index === activeDotIndex ? '●' : char)
                          .join('');

                        return (
                          <div className="space-y-2">
                            <div className="flex justify-between items-center text-[10px] text-muted-foreground font-bold tracking-wider">
                              <span>ATL (${atlNum.toFixed(2)})</span>
                              <span className="text-primary font-mono">{sliderStr}</span>
                              <span>ATH (${athNum.toFixed(2)})</span>
                            </div>
                            <p className="text-[11px] text-muted-foreground text-center font-mono">
                              Current Position: <span className="font-bold text-foreground">{Math.min(100, Math.max(0, rangePercent))}%</span> of historical range
                            </p>
                          </div>
                        );
                      })()}
                    </div>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {/* Section A */}
                    <div className="space-y-3 p-4 rounded-none border border-border/60 bg-card/30">
                      <h4 className="text-[10px] uppercase font-bold text-muted-foreground tracking-widest">
                        {isCrypto ? 'Token Value' : 'Valuation'}
                      </h4>
                      <div className="space-y-2">
                        <div className="flex justify-between items-center text-xs border-b border-border/10 pb-1.5">
                          <span className="text-muted-foreground">Market Capitalization</span>
                          <span className="font-mono font-bold text-foreground">{marketCap}</span>
                        </div>
                        {isCrypto ? (
                          <>
                            <div className="flex justify-between items-center text-xs border-b border-border/10 pb-1.5">
                              <span className="text-muted-foreground">All-Time High</span>
                              <span className="font-mono font-bold text-foreground">{ath}</span>
                            </div>
                            <div className="flex justify-between items-center text-xs border-b border-border/10 pb-1.5">
                              <span className="text-muted-foreground">All-Time Low</span>
                              <span className="font-mono font-bold text-foreground">{atl}</span>
                            </div>
                          </>
                        ) : (
                          <>
                            <div className="flex justify-between items-center text-xs border-b border-border/10 pb-1.5">
                              <span className="text-muted-foreground">P/E Ratio</span>
                              <span className="font-mono font-bold text-foreground">{peRatio}</span>
                            </div>
                            <div className="flex justify-between items-center text-xs border-b border-border/10 pb-1.5">
                              <span className="text-muted-foreground">Dividend Yield</span>
                              <span className="font-mono font-bold text-foreground">{dividendYield}</span>
                            </div>
                          </>
                        )}
                      </div>
                    </div>

                    {/* Section B */}
                    <div className="space-y-3 p-4 rounded-none border border-border/60 bg-card/30">
                      <h4 className="text-[10px] uppercase font-bold text-muted-foreground tracking-widest">
                        {isCrypto ? 'Tokenomics' : 'Market Stats'}
                      </h4>
                      <div className="space-y-2">
                        {isCrypto ? (
                          <>
                            <div className="flex justify-between items-center text-xs border-b border-border/10 pb-1.5">
                              <span className="text-muted-foreground">Circulating Supply</span>
                              <span className="font-mono font-bold text-foreground">{circulatingSupply}</span>
                            </div>
                            <div className="flex justify-between items-center text-xs border-b border-border/10 pb-1.5">
                              <span className="text-muted-foreground">Total Supply</span>
                              <span className="font-mono font-bold text-foreground">{totalSupply}</span>
                            </div>
                            <div className="flex justify-between items-center text-xs border-b border-border/10 pb-1.5">
                              <span className="text-muted-foreground">Max Supply</span>
                              <span className="font-mono font-bold text-foreground">{maxSupply}</span>
                            </div>
                          </>
                        ) : (
                          <>
                            <div className="flex justify-between items-center text-xs border-b border-border/10 pb-1.5">
                              <span className="text-muted-foreground">Short Interest Float</span>
                              <span className="font-mono font-bold text-foreground">{shortFloat}</span>
                            </div>
                            <div className="flex justify-between items-center text-xs border-b border-border/10 pb-1.5">
                              <span className="text-muted-foreground">24h Vol / Liquidity</span>
                              <span className="font-mono font-bold text-foreground">{volume}</span>
                            </div>
                            <div className="flex justify-between items-center text-xs border-b border-border/10 pb-1.5">
                              <span className="text-muted-foreground">Exchange Pool</span>
                              <span className="font-mono font-bold text-foreground">US Stock Market</span>
                            </div>
                          </>
                        )}
                      </div>
                    </div>

                    {/* Section C */}
                    <div className="space-y-3 p-4 rounded-none border border-border/60 bg-card/30">
                      <h4 className="text-[10px] uppercase font-bold text-muted-foreground tracking-widest">Profile Detail</h4>
                      <div className="space-y-2">
                        <div className="flex justify-between items-center text-xs border-b border-border/10 pb-1.5">
                          <span className="text-muted-foreground">Sector Group</span>
                          <span className="font-mono font-bold text-foreground truncate max-w-[120px]">{sector || 'N/A'}</span>
                        </div>
                        <div className="flex justify-between items-center text-xs border-b border-border/10 pb-1.5">
                          <span className="text-muted-foreground">Industry Subclass</span>
                          <span className="font-mono font-bold text-foreground truncate max-w-[120px]">{industry || 'N/A'}</span>
                        </div>
                        <div className="flex justify-between items-center text-xs border-b border-border/10 pb-1.5">
                          <span className="text-muted-foreground">Origin Region</span>
                          <span className="font-mono font-bold text-foreground">{country || 'US'}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                <div className="p-4 rounded-none border border-primary/20 bg-primary/5 text-xs text-muted-foreground leading-relaxed flex gap-3">
                  <Info className="text-primary w-5 h-5 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold text-foreground block mb-0.5">Terminal Notice</span>
                    This node receives cached feeds refreshed via the local JDdS daemon process loop. For granular technical indicators or full real-time analysis, check the Resources tab or use the advisor sidebar prompts.
                  </div>
                </div>
              </div>
            )}


          </div>
        </div>

        {/* Right Column: In-depth Summary Sidebar */}
        <div className="w-full lg:w-80 p-6 overflow-y-auto space-y-6 bg-card/10 flex flex-col justify-between shrink-0 scrollbar-hide">
          <div className="space-y-6">
            <div>
              <h2 className="font-serif text-sm font-bold border-b border-border/20 pb-2 flex items-center gap-2">
                <TrendingUp size={14} className="text-primary" /> Core Metrics Overview
              </h2>
            </div>

            {/* Quick metrics grid / swipeable on mobile */}
            <div className="flex overflow-x-auto lg:grid lg:grid-cols-2 gap-3 pb-2 lg:pb-0 scrollbar-none snap-x snap-mandatory">
              <div className="p-3 rounded-none border border-border/50 bg-card/65 font-mono min-w-[120px] lg:min-w-0 snap-start">
                <span className="text-[9px] text-muted-foreground uppercase font-bold tracking-wider block">Price</span>
                <div className="text-sm font-bold text-foreground mt-0.5">${price.toFixed(price < 1 ? 4 : 2)}</div>
              </div>
              <div className="p-3 rounded-none border border-border/50 bg-card/65 font-mono min-w-[120px] lg:min-w-0 snap-start">
                <span className="text-[9px] text-muted-foreground uppercase font-bold tracking-wider block">Change %</span>
                <div className={`text-sm font-bold mt-0.5 ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {isPositive ? '+' : ''}{changePercent.toFixed(2)}%
                </div>
              </div>
              <div className="p-3 rounded-none border border-border/50 bg-card/65 font-mono min-w-[120px] lg:min-w-0 snap-start">
                <span className="text-[9px] text-muted-foreground uppercase font-bold tracking-wider block">Market Cap</span>
                <div className="text-xs font-bold text-foreground mt-0.5 truncate">{marketCap}</div>
              </div>
              <div className="p-3 rounded-none border border-border/50 bg-card/65 font-mono min-w-[120px] lg:min-w-0 snap-start">
                <span className="text-[9px] text-muted-foreground uppercase font-bold tracking-wider block">{(isCrypto || country === 'CRYPTO') ? 'Rank' : 'P/E Ratio'}</span>
                <div className="text-xs font-bold text-foreground mt-0.5 truncate">{(isCrypto || country === 'CRYPTO') ? `#${rank || 'N/A'}` : peRatio}</div>
              </div>
            </div>

            {/* Asset Health Score Card */}
            {(isCrypto || country === 'CRYPTO') && (
              <div className="p-4 rounded-none border border-border/60 bg-card/45 space-y-2">
                <div className="text-[10px] text-muted-foreground font-bold tracking-wider uppercase">Asset Health Score</div>
                {(() => {
                  let score = 50;
                  const circRatio = maxSupplyRaw && maxSupplyRaw > 0 ? (circulatingSupplyRaw || 0) / maxSupplyRaw : 1;
                  score += Math.round(circRatio * 20);

                  if (marketCapRaw && marketCapRaw > 0 && volumeRaw) {
                    const volToCap = volumeRaw / marketCapRaw;
                    if (volToCap > 0.1) score += 15;
                    else if (volToCap > 0.02) score += 10;
                    else score += 5;
                  } else {
                    score += 10;
                  }

                  if (athChangePercent) {
                    if (athChangePercent >= -15) score += 15;
                    else if (athChangePercent >= -50) score += 10;
                    else score += 5;
                  } else {
                    score += 10;
                  }

                  const finalScore = Math.min(100, Math.max(0, score));
                  let healthLabel = 'Low Health';
                  let healthColor = 'text-rose-400 border-rose-500/25 bg-rose-500/5';
                  let HealthIcon = TrendingDown;
                  if (finalScore >= 75) {
                    healthLabel = 'Healthy';
                    healthColor = 'text-emerald-400 border-emerald-500/25 bg-emerald-500/5';
                    HealthIcon = TrendingUp;
                  } else if (finalScore >= 40) {
                    healthLabel = 'Mid Range';
                    healthColor = 'text-amber-400 border-amber-500/25 bg-amber-500/5';
                    HealthIcon = Info;
                  }

                  return (
                    <div className="flex items-center justify-between font-mono">
                      <div className="text-xl font-black text-foreground">{finalScore} <span className="text-xs text-muted-foreground font-normal">/ 100</span></div>
                      <span className={cn("inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded border", healthColor)}>
                        <HealthIcon className="w-3 h-3 text-inherit" /> {healthLabel}
                      </span>
                    </div>
                  );
                })()}
              </div>
            )}

            {/* 52-Week Visual Slider */}
            {!isCrypto && country !== 'CRYPTO' && (
              <div className="p-4 rounded-none border border-border/60 bg-card/45 space-y-2">
                <div className="flex justify-between items-center text-[10px] text-muted-foreground font-bold tracking-wider uppercase">
                  <span>52W Range</span>
                  <span className="text-foreground">{shortFloat !== 'N/A' ? `Short: ${shortFloat}` : ''}</span>
                </div>
                <div className="relative h-1 bg-accent/40 rounded-full w-full mt-1.5">
                  <div className="absolute top-1/2 left-[45%] -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-primary ring-2 ring-background" />
                </div>
                <div className="flex justify-between font-mono text-[9px] text-muted-foreground">
                  <span>Low</span>
                  <span>High</span>
                </div>
              </div>
            )}

            <div className="p-4 rounded-none border border-emerald-500/20 bg-emerald-500/5 space-y-1">
              <h3 className="text-xs font-bold text-emerald-400 flex items-center gap-1">
                <ShieldAlert size={12} /> Core Asset Sync
              </h3>
              <p className="text-[10px] text-muted-foreground leading-relaxed">
                Database registers updates within ingestion buffers dynamically. If parameters require deep analysis or report compilations, launch the AI prompt below.
              </p>
            </div>
          </div>

          <div className="pt-6 border-t border-border/10 flex flex-col gap-2 shrink-0">
            <Button
              className="w-full bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 hover:border-primary/40 font-semibold py-2.5 rounded-none text-xs cursor-pointer flex items-center justify-center gap-1.5 transition-all hover:scale-[1.02]"
            >
              <Sparkles size={12} /> Run AI Research Agent
            </Button>
            <Button
              variant="outline"
              onClick={onClose}
              className="w-full border-border hover:bg-accent hover:text-foreground font-semibold py-2.5 rounded-none text-xs cursor-pointer"
            >
              Close Asset View
            </Button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
