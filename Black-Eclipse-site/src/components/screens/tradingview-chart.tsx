'use client';

import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  X, TrendingUp, TrendingDown, BarChart2, ShieldAlert, Layers, Info,
  Sparkles, BookOpen, HelpCircle, Landmark, Gauge,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn, getTradingViewSymbol } from '@/lib/utils';
import { formatPriceWithCurrency } from '@/lib/market-currency';

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
  fiftyTwoWeekHigh?: number | null;
  fiftyTwoWeekLow?: number | null;
  eps?: string;
  dayHigh?: number | null;
  dayLow?: number | null;
  dayOpen?: number | null;
  previousClose?: number | null;
  beta?: string;
  dividendRate?: string;
  fdv?: string;
}

// One-line plain-English explanations shown under each metric so new
// investors learn what the number means while they look at it.
const GLOSSARY: Record<string, string> = {
  marketCap: 'Total value of all shares combined — size of the company.',
  peRatio: 'Price vs yearly profit. Lower = cheaper per unit of profit (typically <20).',
  eps: 'Profit the company makes per share each year.',
  dividendYield: 'Cash paid to you yearly as a % of the price.',
  volume: 'Shares traded today — high volume means active interest.',
  change: "How much the price moved today vs yesterday's close.",
  range: "Where today's price sits between the year's low and high.",
  rsi: 'Momentum score on the chart: >70 overbought, <30 oversold.',
  beta: 'Volatility vs the whole market — 1 means it moves together with it.',
  open: 'The first price traded when the market opened today.',
  prevClose: "Yesterday's final price — today's change is measured from it.",
  forwardPE: 'Price vs next year\u2019s expected profit — shows if growth is affordable.',
  fdv: 'Value of all possible coins, even those not released yet.',
};

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
  maxSupplyRaw = 0,
  fiftyTwoWeekHigh = null,
  fiftyTwoWeekLow = null,
  eps = 'N/A',
  dayHigh = null,
  dayLow = null,
  dayOpen = null,
  previousClose = null,
  beta = 'N/A',
  dividendRate = 'N/A',
  fdv = 'N/A',
}: TradingViewChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [showGlossary, setShowGlossary] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const isCrypto = symbol.endsWith('USD') || symbol.endsWith('USDT') || symbol.includes('-');
  const isCryptoAsset = isCrypto || country === 'CRYPTO';

  // Exchange-qualified TradingView symbol — numeric tickers ("000006", "786",
  // "1301") only resolve with their exchange prefix (SZSE:, PSX:, TSE:...).
  const tvResolved = getTradingViewSymbol(symbol, isCryptoAsset, country || undefined);
  const tvSymbolDisplay = tvResolved;

  // Interactive Chart script loading (uses the reliable advanced-chart embed widget)
  useEffect(() => {
    if (!mounted) return;
    const container = containerRef.current;
    if (!container) return;

    container.innerHTML = '';

    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
    script.type = 'text/javascript';
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: tvResolved,
      interval: 'D',
      timezone: 'Etc/UTC',
      theme: 'dark',
      style: '1',
      locale: 'en',
      backgroundColor: 'rgba(0, 0, 0, 0)',
      gridColor: 'rgba(122, 255, 120, 0.05)',
      allow_symbol_change: true,
      hide_side_toolbar: false,
      hide_legend: false,
      studies: ['STD;RSI'],
    });
    container.appendChild(script);

    return () => {
      container.innerHTML = '';
    };
  }, [symbol, mounted, isCryptoAsset, tvResolved]);

  // ESC closes the overlay — a standard exit users expect.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const isPositive = changePercent >= 0;

  // Accurate 52-week range from real data; graceful fallback when missing.
  const has52w = !!(fiftyTwoWeekHigh && fiftyTwoWeekLow && fiftyTwoWeekHigh > fiftyTwoWeekLow);
  const rangePct = has52w
    ? Math.min(100, Math.max(0, ((price - fiftyTwoWeekLow!) / (fiftyTwoWeekHigh! - fiftyTwoWeekLow!)) * 100))
    : null;

  // Market-cap tier — helps users gauge company size at a glance.
  const capTier = (() => {
    const cap = marketCapRaw || parseFloat(String(marketCap).replace(/[^0-9.]/g, '')) || 0;
    if (cap >= 200e9) return { label: 'Mega Cap', hint: 'A market giant (>$200B)' };
    if (cap >= 10e9) return { label: 'Large Cap', hint: 'An established big company ($10B–200B)' };
    if (cap >= 2e9) return { label: 'Mid Cap', hint: 'A growing mid-size company ($2B–10B)' };
    if (cap >= 300e6) return { label: 'Small Cap', hint: 'A smaller, faster-moving company (<$2B)' };
    return { label: 'Micro Cap', hint: 'A very small company — higher risk' };
  })();

  // Valuation read: is the P/E cheap/expensive relative to typical markets?
  const peRead = (() => {
    const pe = parseFloat(peRatio);
    if (!Number.isFinite(pe) || pe <= 0) return null;
    if (pe < 12) return { label: 'Low P/E', tone: 'emerald', note: 'Cheap vs typical market (~15–25)' };
    if (pe <= 25) return { label: 'Fair P/E', tone: 'primary', note: 'In line with typical market (~15–25)' };
    if (pe <= 45) return { label: 'High P/E', tone: 'amber', note: 'Priced for strong growth' };
    return { label: 'Very High P/E', tone: 'rose', note: 'Expensive — future profit is priced in' };
  })();

  // ── Live growth series (1-month daily closes) ──────────────────────────
  // Fetched from /api/price-history (yfinance first, DB snapshot fallback).
  // Rendered as an inline SVG line chart — pure SVG, no chart lib needed.
  const [history, setHistory] = useState<{ points: number[]; source: string } | null>(null);
  useEffect(() => {
    if (!mounted) return;
    let cancelled = false;
    const controller = new AbortController();
    (async () => {
      try {
        const res = await fetch(
          `/api/price-history?symbol=${encodeURIComponent(symbol)}&market=${encodeURIComponent(country || 'US')}`,
          { signal: AbortSignal.timeout(20000) },
        );
        const data = await res.json();
        if (!cancelled && Array.isArray(data.points) && data.points.length >= 2) {
          setHistory({ points: data.points, source: data.source });
        }
      } catch { /* silent — sparkline is optional */ }
    })();
    return () => { cancelled = true; };
  }, [symbol, country, mounted]);

  if (!mounted) return null;

  // Sparkline geometry (viewBox 0 0 100 32).
  const spark = (() => {
    const pts = history?.points ?? [];
    if (pts.length < 2) return null;
    const min = Math.min(...pts);
    const max = Math.max(...pts);
    const span = max - min || 1;
    const coords = pts.map((p, i) => ({
      x: (i / (pts.length - 1)) * 100,
      y: 30 - ((p - min) / span) * 26,
    }));
    const line = coords.map((c, i) => `${i === 0 ? 'M' : 'L'}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ');
    const area = `${line} L100,32 L0,32 Z`;
    const up = pts[pts.length - 1] >= pts[0];
    return { line, area, up, changePct: ((pts[pts.length - 1] - pts[0]) / pts[0]) * 100 };
  })();

  return createPortal(
    <div className="tv-overlay fixed inset-0 z-50 bg-white/30 dark:bg-[#0f0f0f]/30 backdrop-blur-3xl flex flex-col h-[100dvh] w-full text-foreground animate-fade-in font-sans">
      {/* Header Panel */}
      <div className="flex items-center justify-between gap-4 border-b border-border/30 px-4 md:px-6 py-3 bg-white/40 dark:bg-[#0f0f0f]/40 backdrop-blur-xl shadow-sm shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shrink-0">
            <BarChart2 className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 min-w-0">
              <span className="font-mono text-lg md:text-xl font-bold bg-accent/60 px-2 py-0.5 rounded-lg text-foreground shrink-0">{symbol}</span>
              <h1 className="font-serif text-base md:text-lg font-semibold text-foreground truncate">
                {stockName || symbol}
              </h1>
              {sector && (
                <span className="text-[10px] bg-accent/40 text-muted-foreground px-2 py-0.5 rounded-lg hidden md:inline shrink-0">
                  {sector}
                </span>
              )}
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5 truncate">
              Live chart & key metrics — everything you need on one screen.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4 md:gap-6 shrink-0">
          {/* Real-time ticker details in header */}
          <div className="hidden sm:flex items-center gap-4 md:gap-6 text-right">
            <div>
              <div className="text-[9px] uppercase font-bold tracking-wider text-muted-foreground">Last Price</div>
              <div className="font-mono text-base font-extrabold text-foreground">{formatPriceWithCurrency(country, price)}</div>
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
            title="Back to screener (Esc)"
            className="p-2 rounded-xl hover:bg-accent text-muted-foreground hover:text-foreground cursor-pointer transition-colors border border-border/40"
          >
            <X size={18} />
          </button>
        </div>
      </div>

      {/* Main column: chart TOP, analytics scrolling BELOW */}
      <div className="flex-1 overflow-y-auto tv-metrics-rail min-h-0 p-3 space-y-3">
        {/* Growth sparkline (1-month live daily closes) */}
        <div className="rounded-2xl border border-border/40 bg-white/50 dark:bg-[#0f0f0f]/50 backdrop-blur-xl p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="flex items-center gap-2 text-xs font-bold text-foreground">
              <TrendingUp size={14} className="text-primary" /> 1-Month Growth
              <span className={`text-[10px] font-mono font-bold ${(spark?.changePct ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {spark ? `${spark.changePct >= 0 ? '+' : ''}${spark.changePct.toFixed(2)}%` : ''}
              </span>
            </span>
            <span className="text-[10px] font-mono text-muted-foreground/70">
              {history?.source === 'yfinance' ? 'live · Yahoo Finance' : history ? 'snapshot · cached' : 'loading…'}
            </span>
          </div>
          {spark ? (
            <svg viewBox="0 0 100 32" preserveAspectRatio="none" className="w-full h-16">
              <defs>
                <linearGradient id={`sparkFill-${symbol.replace(/[^A-Z0-9]/gi, '')}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={spark.up ? '#34d399' : '#fb7185'} stopOpacity="0.35" />
                  <stop offset="100%" stopColor={spark.up ? '#34d399' : '#fb7185'} stopOpacity="0" />
                </linearGradient>
              </defs>
              <path d={spark.area} fill={`url(#sparkFill-${symbol.replace(/[^A-Z0-9]/gi, '')})`} />
              <path d={spark.line} fill="none" stroke={spark.up ? '#34d399' : '#fb7185'} strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
            </svg>
          ) : (
            <div className="h-16 flex items-center justify-center text-[11px] text-muted-foreground/60 font-mono">
              {history === null ? 'Loading growth data…' : 'No price history available yet'}
            </div>
          )}
        </div>

        {/* Interactive chart card */}
        <div className="h-[52dvh] min-h-[320px] flex flex-col rounded-2xl border border-border/40 bg-white/40 dark:bg-[#0f0f0f]/40 backdrop-blur-xl overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2 border-b border-border/20 shrink-0">
            <span className="flex items-center gap-2 text-xs font-bold text-foreground">
              <Gauge size={14} className="text-primary" /> Interactive Chart
              <span className="text-[10px] font-medium text-muted-foreground/70 hidden md:inline">RSI momentum is on the lower pane</span>
            </span>
            <span className="text-[10px] font-mono text-muted-foreground/70">{tvSymbolDisplay}</span>
          </div>
          <div id="tradingview_widget_container" ref={containerRef} className="flex-1 w-full bg-background/40 dark:bg-transparent min-h-0" />
        </div>

        {/* Analytics grid below the chart */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
          {/* Core metrics */}
          <div className="rounded-2xl border border-border/40 bg-white/50 dark:bg-[#0f0f0f]/50 backdrop-blur-xl p-4 space-y-3">
            <h2 className="font-serif text-sm font-bold border-b border-border/20 pb-2 flex items-center gap-2">
              <TrendingUp size={14} className="text-primary" /> Core Metrics
            </h2>
            <div className="grid grid-cols-2 gap-2.5">
              <MetricCard label="Price" value={formatPriceWithCurrency(country, price)} />
              <MetricCard label="Change %" value={`${isPositive ? '+' : ''}${changePercent.toFixed(2)}%`} tone={isPositive ? 'emerald' : 'rose'} hint={GLOSSARY.change} />
              <MetricCard label="Market Cap" value={marketCap} sub={capTier.label} hint={GLOSSARY.marketCap} />
              <MetricCard label="P/E Ratio" value={peRatio} sub={peRead?.label} hint={GLOSSARY.peRatio} />
              {!isCryptoAsset && <MetricCard label="EPS" value={eps} hint={GLOSSARY.eps} />}
              {!isCryptoAsset && <MetricCard label="Dividend Yield" value={dividendYield} hint={GLOSSARY.dividendYield} />}
              {isCryptoAsset && <MetricCard label="Rank" value={rank && rank < 9999 ? `#${rank}` : 'N/A'} hint="Size position among all cryptocurrencies." />}
              <MetricCard label="Volume" value={volume} hint={GLOSSARY.volume} />
            </div>
            {peRead && (
              <div className={cn(
                'rounded-xl border px-3 py-2 text-[11px] leading-relaxed',
                peRead.tone === 'emerald' && 'border-emerald-500/25 bg-emerald-500/5 text-emerald-300',
                peRead.tone === 'primary' && 'border-primary/25 bg-primary/5 text-primary',
                peRead.tone === 'amber' && 'border-amber-500/25 bg-amber-500/5 text-amber-300',
                peRead.tone === 'rose' && 'border-rose-500/25 bg-rose-500/5 text-rose-300',
              )}>
                <span className="font-bold">{peRead.label}:</span> {peRead.note}
              </div>
            )}
          </div>

          {/* 52-week range with REAL data */}
          {!isCryptoAsset && (
            <div className="rounded-2xl border border-border/40 bg-white/50 dark:bg-[#0f0f0f]/50 backdrop-blur-xl p-4 space-y-2">
              <div className="flex items-center justify-between text-[10px] text-muted-foreground font-bold tracking-wider uppercase">
                <span>52-Week Range</span>
                {rangePct != null && <span className="text-foreground font-mono">{Math.round(rangePct)}% of range</span>}
              </div>
              <div className="relative h-1.5 bg-accent/40 rounded-full w-full mt-1.5">
                {rangePct != null && (
                  <div
                    className="absolute top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-primary ring-2 ring-background transition-all"
                    style={{ left: `calc(${rangePct}% - 5px)` }}
                  />
                )}
                {rangePct == null && <div className="absolute top-1/2 left-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-muted-foreground/50 ring-2 ring-background" />}
              </div>
              <div className="flex justify-between font-mono text-[10px] text-muted-foreground">
                <span>{has52w ? formatPriceWithCurrency(country, fiftyTwoWeekLow!) : 'Low N/A'}</span>
                <span className="text-[9px] text-muted-foreground/60 font-sans max-w-[60%] text-center truncate">{GLOSSARY.range}</span>
                <span>{has52w ? formatPriceWithCurrency(country, fiftyTwoWeekHigh!) : 'High N/A'}</span>
              </div>
            </div>
          )}

          {/* Today's session — OHLC vs previous close */}
          {(dayOpen != null || dayHigh != null || previousClose != null) && (
            <div className="rounded-2xl border border-border/40 bg-card/25 backdrop-blur-xl p-4 space-y-2.5">
              <h2 className="font-serif text-sm font-bold border-b border-border/20 pb-2 flex items-center gap-2">
                <Gauge size={14} className="text-primary" /> Today&apos;s Session
              </h2>
              <div className="grid grid-cols-4 gap-2">
                <MetricCard label="Open" value={dayOpen != null ? formatPriceWithCurrency(country, dayOpen) : '—'} hint="First traded price today." />
                <MetricCard label="High" value={dayHigh != null ? formatPriceWithCurrency(country, dayHigh) : '—'} />
                <MetricCard label="Low" value={dayLow != null ? formatPriceWithCurrency(country, dayLow) : '—'} />
                <MetricCard label="Prev Close" value={previousClose != null ? formatPriceWithCurrency(country, previousClose) : '—'} hint="Yesterday's final price — the base for today's change." />
              </div>
              {previousClose != null && previousClose > 0 && dayHigh != null && dayLow != null && dayHigh > dayLow && (
                (() => {
                  const posPct = Math.min(100, Math.max(0, ((price - dayLow) / (dayHigh - dayLow)) * 100));
                  return (
                    <div className="space-y-1">
                      <div className="relative h-1 bg-accent/40 rounded-full">
                        <div className="absolute top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-primary ring-2 ring-background" style={{ left: `calc(${posPct}% - 4px)` }} />
                      </div>
                      <p className="text-[10px] text-muted-foreground text-center">Today&apos;s price vs its intraday range — near the top means buyers are in control.</p>
                    </div>
                  );
                })()
              )}
            </div>
          )}

          {/* Risk & income stats */}
          {!isCryptoAsset && (beta !== 'N/A' || dividendRate !== 'N/A' || peRatio !== 'N/A') && (
            <div className="rounded-2xl border border-border/40 bg-white/50 dark:bg-[#0f0f0f]/50 backdrop-blur-xl p-4 space-y-2.5">
              <h2 className="font-serif text-sm font-bold border-b border-border/20 pb-2 flex items-center gap-2">
                <ShieldAlert size={14} className="text-primary" /> Risk & Income
              </h2>
              <div className="grid grid-cols-2 gap-2">
                <MetricCard label="Beta (Volatility)" value={beta} hint="How much it swings vs the market: >1 = wilder, <1 = calmer." />
                <MetricCard label="Forward P/E" value={peRatio !== 'N/A' ? peRatio : 'N/A'} hint="Price vs yearly profit — see the P/E read below." />
                <MetricCard label="Dividend / Share" value={dividendRate !== 'N/A' ? dividendRate : 'None'} hint="Actual cash paid per share each year." />
                <MetricCard label="Annual Income" value={dividendRate !== 'N/A' && dividendRate !== 'None' && price > 0 ? `${((parseFloat(dividendRate) / price) * 100).toFixed(2)}%` : '—'} hint="Dividend as % of today's price (yield)." />
              </div>
              {(() => {
                const b = parseFloat(beta);
                if (!Number.isFinite(b) || b === 0) return null;
                const tone = b >= 1.5 ? 'rose' : b >= 1 ? 'amber' : 'emerald';
                const note = b >= 1.5 ? 'High volatility — expect big swings vs the market.' : b >= 1 ? 'Moves roughly with the market, slightly amplified.' : 'Calmer than the overall market.';
                return (
                  <div className={cn(
                    'rounded-xl border px-3 py-2 text-[11px] leading-relaxed',
                    tone === 'emerald' && 'border-emerald-500/25 bg-emerald-500/5 text-emerald-300',
                    tone === 'amber' && 'border-amber-500/25 bg-amber-500/5 text-amber-300',
                    tone === 'rose' && 'border-rose-500/25 bg-rose-500/5 text-rose-300',
                  )}>
                    <span className="font-bold">Beta {b.toFixed(2)}:</span> {note}
                  </div>
                );
              })()}
            </div>
          )}

          {/* Crypto tokenomics */}
          {isCryptoAsset && (
            <div className="rounded-2xl border border-border/40 bg-white/50 dark:bg-[#0f0f0f]/50 backdrop-blur-xl p-4 space-y-3">
              <h2 className="font-serif text-sm font-bold border-b border-border/20 pb-2 flex items-center gap-2">
                <Landmark size={14} className="text-primary" /> Tokenomics
              </h2>
              <div className="grid grid-cols-3 gap-2">
                <MetricCard label="Circulating" value={circulatingSupply} />
                <MetricCard label="Total" value={totalSupply} />
                <MetricCard label="Max" value={maxSupply} />
              </div>
              {(() => {
                const ratio = maxSupplyRaw && maxSupplyRaw > 0 ? (circulatingSupplyRaw || 0) / maxSupplyRaw : 1;
                const ratioPercent = (ratio * 100).toFixed(1);
                const filledBars = Math.round(ratio * 10);
                const emptyBars = 10 - filledBars;
                const barStr = '██████████'.slice(0, filledBars) + '░░░░░░░░░░'.slice(0, emptyBars);
                return (
                  <div className="rounded-xl border border-border/30 bg-background/40 px-3 py-2 space-y-1">
                    <div className="flex items-center justify-between text-[10px] uppercase font-bold text-muted-foreground tracking-widest">
                      <span>Circulating Ratio</span><span className="text-foreground font-mono">{ratioPercent}%</span>
                    </div>
                    <div className="text-primary font-mono text-xs">{barStr}</div>
                    <p className="text-[10px] text-muted-foreground">Share of all coins already released — higher means less future dilution.</p>
                  </div>
                );
              })()}
              <div className="grid grid-cols-2 gap-2">
                <MetricCard label="All-Time High" value={ath} sub={`${Math.abs(athChangePercent).toFixed(1)}% below ATH`} hint="Highest price ever reached." />
                <MetricCard label="All-Time Low" value={atl} sub={`${Math.abs(atlChangePercent).toFixed(1)}% above ATL`} hint="Lowest price ever reached." />
              </div>
              {fdv !== 'N/A' && (
                <MetricCard label="Fully Diluted Value" value={fdv} hint="Total value if every possible coin were in circulation." />
              )}
            </div>
          )}

          {/* Profile */}
          <div className="rounded-2xl border border-border/40 bg-white/50 dark:bg-[#0f0f0f]/50 backdrop-blur-xl p-4 space-y-2">
            <h2 className="font-serif text-sm font-bold border-b border-border/20 pb-2 flex items-center gap-2">
              <Layers size={14} className="text-primary" /> Company Profile
            </h2>
            <div className="grid grid-cols-1 gap-1.5 text-xs">
              <ProfileRow k="Sector" v={sector || 'N/A'} />
              <ProfileRow k="Industry" v={industry || 'N/A'} />
              <ProfileRow k="Exchange / Market" v={isCryptoAsset ? 'Global Crypto' : (country || 'US')} />
              {!isCryptoAsset && <ProfileRow k="Short Float" v={shortFloat} />}
            </div>
          </div>

          {/* Health score (crypto) */}
          {isCryptoAsset && (() => {
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
              <div className="rounded-2xl border border-border/40 bg-white/50 dark:bg-[#0f0f0f]/50 backdrop-blur-xl p-4 space-y-2">
                <div className="text-[10px] text-muted-foreground font-bold tracking-wider uppercase">Asset Health Score</div>
                <div className="flex items-center justify-between font-mono">
                  <div className="text-xl font-black text-foreground">{finalScore} <span className="text-xs text-muted-foreground font-normal">/ 100</span></div>
                  <span className={cn('inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-lg border', healthColor)}>
                    <HealthIcon className="w-3 h-3 text-inherit" /> {healthLabel}
                  </span>
                </div>
                <p className="text-[10px] text-muted-foreground">Blend of liquidity, supply maturity and distance from all-time highs.</p>
              </div>
            );
          })()}

          {/* Data provenance notice */}
          <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-4 space-y-1">
            <h3 className="text-xs font-bold text-emerald-400 flex items-center gap-1">
              <ShieldAlert size={12} /> Core Asset Sync
            </h3>
            <p className="text-[10px] text-muted-foreground leading-relaxed">
              Quotes refresh through the local JDDS daemon. For deep analysis or report compilations, launch the AI research agent below.
            </p>
          </div>

          {/* Actions */}
          <div className="flex flex-col gap-2 pb-2 xl:col-span-2">
            <Button
              className="w-full bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 hover:border-primary/40 font-semibold py-2.5 rounded-xl text-xs cursor-pointer flex items-center justify-center gap-1.5 transition-all hover:scale-[1.02]"
            >
              <Sparkles size={12} /> Run AI Research Agent
            </Button>
            <Button
              variant="outline"
              onClick={onClose}
              className="w-full border-border hover:bg-accent hover:text-foreground font-semibold py-2.5 rounded-xl text-xs cursor-pointer"
            >
              Back to Market Screener
            </Button>
          </div>
        </div>
      </div>

      {/* Learn-the-terms glossary toggle */}
      <button
        onClick={() => setShowGlossary(v => !v)}
        className="fixed bottom-4 left-4 z-[60] inline-flex items-center gap-1.5 text-[11px] font-bold text-muted-foreground hover:text-primary bg-card/80 hover:bg-accent border border-border/40 hover:border-primary/40 rounded-xl px-3 py-2 backdrop-blur-xl transition-all cursor-pointer"
      >
        <BookOpen size={13} /> {showGlossary ? 'Hide' : 'Learn the terms'}
      </button>
      {showGlossary && (
        <div className="fixed bottom-16 left-4 z-[60] w-[min(420px,calc(100vw-2rem))] rounded-2xl border border-border/40 bg-card/90 backdrop-blur-xl p-4 shadow-2xl space-y-2 animate-fade-in max-h-[50dvh] overflow-y-auto">
          <h3 className="text-xs font-bold text-primary flex items-center gap-1.5">
            <HelpCircle size={13} /> What these numbers mean
          </h3>
          {[
            ['Market Cap', GLOSSARY.marketCap],
            ['P/E Ratio', GLOSSARY.peRatio],
            ['Forward P/E', GLOSSARY.forwardPE],
            ['EPS', GLOSSARY.eps],
            ['Dividend Yield', GLOSSARY.dividendYield],
            ['Volume', GLOSSARY.volume],
            ['Open / Prev Close', `${GLOSSARY.open} ${GLOSSARY.prevClose}`],
            ['Beta', GLOSSARY.beta],
            ['52-Week Range', GLOSSARY.range],
            ['RSI (on chart)', GLOSSARY.rsi],
          ].map(([k, v]) => (
            <div key={k} className="text-[11px] leading-relaxed border-b border-border/10 pb-1.5 last:border-0">
              <span className="font-bold text-foreground">{k}:</span>{' '}
              <span className="text-muted-foreground">{v}</span>
            </div>
          ))}
        </div>
      )}
    </div>,
    document.body
  );
}

function MetricCard({ label, value, sub, tone, hint }: {
  label: string; value: string; sub?: string; tone?: 'emerald' | 'rose'; hint?: string;
}) {
  return (
    <div className="rounded-xl border border-border/40 bg-background/40 px-3 py-2 min-w-0" title={hint || undefined}>
      <div className="text-[9px] text-muted-foreground uppercase font-bold tracking-wider truncate">{label}</div>
      <div className={cn(
        'text-sm font-bold font-mono text-foreground truncate',
        tone === 'emerald' && 'text-emerald-400',
        tone === 'rose' && 'text-rose-400',
      )}>{value}</div>
      {sub && <div className="text-[9px] text-muted-foreground/80 truncate">{sub}</div>}
    </div>
  );
}

function ProfileRow({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border/10 pb-1.5 last:border-0">
      <span className="text-muted-foreground shrink-0">{k}</span>
      <span className="font-mono font-bold text-foreground truncate text-right">{v}</span>
    </div>
  );
}