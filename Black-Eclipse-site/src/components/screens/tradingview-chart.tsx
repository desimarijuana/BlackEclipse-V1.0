'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import * as echarts from 'echarts';
import type { EChartsOption } from 'echarts';
import {
  X, TrendingUp, BarChart2, ShieldAlert, Layers,
  BookOpen, HelpCircle, Landmark, Gauge, ChartCandlestick, Activity,
} from '@/lib/icons';
import { ChartWidget } from '@/components/chart/chart-widget';
import { cn, getTradingViewSymbol } from '@/lib/utils';
import { describeSeriesSource } from '@/lib/chart/observation-freshness';
import { formatPriceWithCurrency } from '@/lib/market-currency';
import { countryToMarketId } from '@/lib/markets';
import { useFundamentals } from '@/components/screens/fundamentals/use-fundamentals';
import {
  FundamentalsFull,
  TickerHeader,
  LoadingState as FundamentalsLoading,
  UnavailableState as FundamentalsUnavailable,
  ErrorState as FundamentalsError,
} from '@/components/screens/fundamentals/panel';
import { computeTechnical } from '@/lib/company/technical';
import { computeCompanyRisk } from '@/lib/company/risk';
import { useCompanyNews } from '@/lib/company/use-company-news';
import { useCompanyResearch } from '@/lib/company/use-company-research';
import {
  AiResearchSection,
  CompanyNewsSection,
  TechnicalSection,
  RiskSection,
  ValuationNote,
  LeadershipSection,
  ResearchedFinancialsSection,
} from '@/components/screens/company/sections';

// Full detail record served by /api/asset-details — superset of the screener
// row so the overlay can render complete data for ANY asset type.
export interface AssetDetail {
  symbol: string;
  name: string;
  sector: string;
  industry: string;
  country: string;
  securityType: string;
  assetClass: string;
  marketId: string;
  currency: string;
  price: number;
  changePercent: number;
  volume: string;
  volumeRaw: number;
  marketCap: string;
  marketCapRaw: number;
  peRatio: string;
  forwardPE: string;
  dividendYield: string;
  dividendRate: string;
  eps: string;
  beta: string;
  dayHigh: number | null;
  dayLow: number | null;
  dayOpen: number | null;
  previousClose: number | null;
  fiftyTwoWeekHigh: number | null;
  fiftyTwoWeekLow: number | null;
  rank?: number;
  circulatingSupply: string;
  circulatingSupplyRaw?: number;
  totalSupply: string;
  maxSupply: string;
  maxSupplyRaw?: number;
  ath: string;
  atl: string;
  athChangePercent: number;
  atlChangePercent: number;
  fdv: string;
  source?: string | null;
  updatedAt?: string | null;
}

// One bar of the real daily OHLCV series served by /api/price-history.
export interface PriceBar {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number | null;
}

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
  const [showGlossary, setShowGlossary] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const isCrypto = symbol.endsWith('USD') || symbol.endsWith('USDT') || symbol.includes('-');
  const isCryptoAsset = isCrypto || country === 'CRYPTO';

  // The screener row carries a country name ("United States") or code ("US");
  // normalize to the JDDS market id the fundamentals providers key off.
  const fundamentalsMarket = countryToMarketId(country);

  // Provider → Normalization → JDDS snapshot. Loaded immediately so the company
  // profile, statements and valuation render inline on the single page.
  const fund = useFundamentals(symbol, fundamentalsMarket);

  // ── Full asset details ──────────────────────────────────────────────────
  // The screener row only carries partial data. Fetch the COMPLETE record
  // from /api/asset-details (works for every asset type in JDDS — stocks,
  // ETFs, funds, crypto, warrants, any market) and merge: live values win.
  const [detail, setDetail] = useState<AssetDetail | null>(null);
  // ── Canonical quote ──────────────────────────────────────────────────────
  // ONE live quote (with freshness + provenance) shared by the header AND the
  // metric cards, so the header can never show a different number than the
  // chart/metrics for the same instrument.
  const [quote, setQuote] = useState<{
    price: number; changePercent: number; currency?: string;
    source?: string; freshness?: string; stale?: boolean; updatedAt?: string;
  } | null>(null);
  useEffect(() => {
    if (!mounted) return;
    let cancelled = false;
    const controller = new AbortController();
    (async () => {
      try {
        const res = await fetch(
          `/api/asset-details?symbol=${encodeURIComponent(symbol)}&market=${encodeURIComponent(country || '')}`,
          { signal: controller.signal },
        );
        const data = await res.json();
        if (!cancelled && data?.found && data.asset) setDetail(data.asset as AssetDetail);
      } catch { /* silent — fallback data stays */ }
    })();
    return () => { cancelled = true; controller.abort(); };
  }, [symbol, country, mounted]);

  const effPrice = detail ? (price > 0 ? price : detail.price) : price;
  const effChange = detail && changePercent === 0 ? detail.changePercent : changePercent;
  const effMarketCap = marketCap !== 'N/A' ? marketCap : (detail?.marketCap ?? 'N/A');
  const effPe = peRatio !== 'N/A' ? peRatio : (detail?.peRatio ?? 'N/A');
  const effDividendYield = dividendYield !== 'N/A' && dividendYield !== 'None' ? dividendYield : (detail?.dividendYield ?? dividendYield);
  const effVolume = volume !== 'N/A' ? volume : (detail?.volume ?? 'N/A');
  const effSector = sector || detail?.sector || '';
  const effIndustry = industry || detail?.industry || '';
  const effCountry = country || detail?.marketId || '';
  const effShortFloat = shortFloat;
  const effEps = eps !== 'N/A' ? eps : (detail?.eps ?? 'N/A');
  const effBeta = beta !== 'N/A' ? beta : (detail?.beta ?? 'N/A');
  const effDividendRate = dividendRate !== 'N/A' ? dividendRate : (detail?.dividendRate ?? 'N/A');
  const effFdv = fdv !== 'N/A' ? fdv : (detail?.fdv ?? 'N/A');
  const effAth = ath !== 'N/A' ? ath : (detail?.ath ?? 'N/A');
  const effAtl = atl !== 'N/A' ? atl : (detail?.atl ?? 'N/A');
  const effAthChange = athChangePercent || detail?.athChangePercent || 0;
  const effAtlChange = atlChangePercent || detail?.atlChangePercent || 0;
  const effAthDate = athDate && athDate !== 'N/A' ? athDate : (detail?.updatedAt ?? '');
  const effAtlDate = atlDate && atlDate !== 'N/A' ? atlDate : (detail?.updatedAt ?? '');
  const effRank = rank && rank < 9999 ? rank : (detail?.rank ?? 9999);
  const effCirc = circulatingSupply !== 'N/A' ? circulatingSupply : (detail?.circulatingSupply ?? 'N/A');
  const effTotal = totalSupply !== 'N/A' ? totalSupply : (detail?.totalSupply ?? 'N/A');
  const effMax = maxSupply !== 'N/A' ? maxSupply : (detail?.maxSupply ?? 'N/A');
  const effCircRaw = circulatingSupplyRaw || detail?.circulatingSupplyRaw || 0;
  const effMaxRaw = maxSupplyRaw || detail?.maxSupplyRaw || 0;
  const eff52High = fiftyTwoWeekHigh ?? detail?.fiftyTwoWeekHigh ?? null;
  const eff52Low = fiftyTwoWeekLow ?? detail?.fiftyTwoWeekLow ?? null;
  const effDayHigh = dayHigh ?? detail?.dayHigh ?? null;
  const effDayLow = dayLow ?? detail?.dayLow ?? null;
  const effDayOpen = dayOpen ?? detail?.dayOpen ?? null;
  const effPrevClose = previousClose ?? detail?.previousClose ?? null;
  const effName = stockName || detail?.name || symbol;
  const effVolumeRaw = volumeRaw || detail?.volumeRaw || 0;
  const effMarketCapRaw = marketCapRaw || detail?.marketCapRaw || 0;

  // Fetch the canonical quote once (server-side resolution + freshness).
  useEffect(() => {
    if (!mounted) return;
    let cancelled = false;
    const controller = new AbortController();
    (async () => {
      try {
        const url = `/api/quote?symbols=${encodeURIComponent(symbol)}${effCountry ? `&market=${encodeURIComponent(effCountry)}` : ''}`;
        const res = await fetch(url, { signal: controller.signal });
        const data = await res.json();
        const q = Array.isArray(data.quotes) ? data.quotes.find((x: { found?: boolean }) => x.found) : null;
        if (!cancelled && q) {
          setQuote({
            price: Number(q.price) || 0,
            changePercent: Number(q.changePercent) || 0,
            currency: q.currency,
            source: q.source,
            freshness: q.freshness,
            stale: q.stale,
            updatedAt: q.updatedAt,
          });
        }
      } catch { /* silent — fall back to screener/detail values */ }
    })();
    return () => { cancelled = true; controller.abort(); };
  }, [symbol, effCountry, mounted]);

  // Canonical price/change: the live quote wins; otherwise the screener/detail
  // value. The header, metric cards and chart label all read from here.
  const canonicalPrice = quote && quote.price > 0 ? quote.price : effPrice;
  const canonicalChange = quote ? quote.changePercent : effChange;

  // Exchange-qualified TradingView symbol — numeric tickers ("000006", "786",
  // "1301") only resolve with their exchange prefix (SZSE:, PSX:, TSE:...).
  const tvResolved = getTradingViewSymbol(symbol, isCryptoAsset, effCountry || undefined);
  const tvSymbolDisplay = tvResolved;

  // ESC closes the overlay — a standard exit users expect.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const isPositive = canonicalChange >= 0;

  // ── Real price history ──────────────────────────────────────────────────
  // Fetched from /api/price-history — a REAL daily OHLCV series from the
  // Yahoo chart API (works for every market incl. PSX via .KA fallback),
  // with derived 1W/1M/3M performance. Powers the growth chart in All
  // Metrics, the performance bars, and the volume profile.
  const [history, setHistory] = useState<{
    bars: PriceBar[];
    points: number[];
    currency: string;
    perf: { week?: number; month?: number; quarter?: number };
    source: string;
    freshness?: string;
    observationTime?: string | null;
    stale?: boolean;
  } | null>(null);
  const [historyRange, setHistoryRange] = useState<'1mo' | '3mo' | '6mo'>('3mo');
  useEffect(() => {
    if (!mounted) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(
          `/api/price-history?symbol=${encodeURIComponent(symbol)}&market=${encodeURIComponent(effCountry || 'US')}&range=${historyRange}`,
          { signal: AbortSignal.timeout(25000) },
        );
        const data = await res.json();
        if (!cancelled && Array.isArray(data.series) && data.series.length >= 2) {
          setHistory({
            bars: data.series as PriceBar[],
            points: data.points as number[],
            currency: data.currency || '$',
            perf: data.perf || {},
            source: data.source,
            freshness: data.freshness,
            observationTime: data.observationTime ?? null,
            stale: data.stale,
          });
        } else if (!cancelled) {
          setHistory(null);
        }
      } catch { /* silent — charts are optional */ }
    })();
    return () => { cancelled = true; };
  }, [symbol, effCountry, mounted, historyRange]);

  // ── Single-page intelligence: news + AI research + deterministic analytics ──
  // One instance each so the page never starts duplicate requests.
  const news = useCompanyNews(symbol);
  const research = useCompanyResearch(symbol, effName, effCountry || fundamentalsMarket || 'US');
  const technical = useMemo(() => computeTechnical(history?.bars ?? []), [history?.bars]);
  const risks = useMemo(() => {
    const b = parseFloat(effBeta);
    return computeCompanyRisk({
      technical,
      periods: fund.data?.periods ?? [],
      beta: Number.isFinite(b) ? b : null,
      avgVolume: effVolumeRaw || null,
      insights: fund.data?.insights ?? [],
    });
  }, [technical, fund.data, effBeta, effVolumeRaw]);

  // Live growth series for the compact strip (1-month closes) — reused by
  // the All Metrics growth chart via the same payload.
  const spark = (() => {
    const pts = history?.points ?? [];
    if (pts.length < 2) return null;
    const up = pts[pts.length - 1] >= pts[0];
    const changePct = ((pts[pts.length - 1] - pts[0]) / pts[0]) * 100;
    return { up, changePct };
  })();

  // Accurate 52-week range from real data; graceful fallback when missing.
  const has52w = !!(eff52High && eff52Low && eff52High > eff52Low);
  const rangePct = has52w
    ? Math.min(100, Math.max(0, ((canonicalPrice - eff52Low!) / (eff52High! - eff52Low!)) * 100))
    : null;

  // Market-cap tier — helps users gauge company size at a glance.
  const capTier = (() => {
    const cap = effMarketCapRaw || parseFloat(String(effMarketCap).replace(/[^0-9.]/g, '')) || 0;
    if (cap >= 200e9) return { label: 'Mega Cap', hint: 'A market giant (>$200B)' };
    if (cap >= 10e9) return { label: 'Large Cap', hint: 'An established big company ($10B–200B)' };
    if (cap >= 2e9) return { label: 'Mid Cap', hint: 'A growing mid-size company ($2B–10B)' };
    if (cap >= 300e6) return { label: 'Small Cap', hint: 'A smaller, faster-moving company (<$2B)' };
    if (cap > 0) return { label: 'Micro Cap', hint: 'A very small company — higher risk' };
    return { label: 'N/A', hint: 'Market cap not reported for this asset.' };
  })();

  // Valuation read: is the P/E cheap/expensive relative to typical markets?
  const peRead = (() => {
    const pe = parseFloat(effPe);
    if (!Number.isFinite(pe) || pe <= 0) return null;
    if (pe < 12) return { label: 'Low P/E', tone: 'emerald', note: 'Cheap vs typical market (~15–25)' };
    if (pe <= 25) return { label: 'Fair P/E', tone: 'primary', note: 'In line with typical market (~15–25)' };
    if (pe <= 45) return { label: 'High P/E', tone: 'amber', note: 'Priced for strong growth' };
    return { label: 'Very High P/E', tone: 'rose', note: 'Expensive — future profit is priced in' };
  })();

  return createPortal(
    <div className="tv-overlay fixed inset-0 z-50 bg-black/90 backdrop-blur-md flex flex-col h-[100dvh] w-full text-foreground animate-fade-in font-sans">
      {/* Header Panel */}
      <div className="flex items-center justify-between gap-4 border-b border-border/30 px-4 md:px-6 py-3 glass-card-subtle shadow-sm shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shrink-0">
            <BarChart2 className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 min-w-0">
              <span className="font-mono text-lg md:text-xl font-bold bg-accent/60 px-2 py-0.5 rounded-lg text-foreground shrink-0">{symbol}</span>
              <h1 className="font-serif text-base md:text-lg font-semibold text-foreground truncate">
                {effName}
              </h1>
              {effSector && (
                <span className="text-[10px] bg-accent/40 text-muted-foreground px-2 py-0.5 rounded-lg hidden md:inline shrink-0">
                  {effSector}
                </span>
              )}
              {effCountry && (
                <span
                  title="Market / exchange"
                  className="text-[10px] bg-primary/10 text-primary border border-primary/20 px-2 py-0.5 rounded-lg hidden md:inline shrink-0 font-mono"
                >
                  {effCountry}
                </span>
              )}
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5 truncate">
              Interactive chart, filings-backed fundamentals &amp; key metrics.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4 md:gap-6 shrink-0">
          {/* Real-time ticker details in header */}
          <div className="hidden sm:flex items-center gap-4 md:gap-6 text-right">
            <div>
              <div className="text-[9px] uppercase font-bold tracking-wider text-muted-foreground">Last Price</div>
              <div className="font-mono text-base font-extrabold text-foreground">{formatPriceWithCurrency(effCountry, canonicalPrice)}</div>
              {quote && (
                <div className={cn('text-[9px] font-mono', quote.stale ? 'text-amber-400' : 'text-muted-foreground/70')}>
                  {quote.stale ? 'stale' : 'live'} · {quote.source ?? 'quote'}
                  {quote.updatedAt ? ` · ${new Date(quote.updatedAt).toLocaleString()}` : ''}
                </div>
              )}
            </div>
            <div>
              <div className="text-[9px] uppercase font-bold tracking-wider text-muted-foreground">24H Change</div>
              <div className={`font-mono text-sm font-bold ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                {isPositive ? '▲ +' : '▼ '}{canonicalChange.toFixed(2)}%
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

      {/* Main Grid: chart LEFT, information RIGHT (classic terminal layout) */}
      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden min-h-0">
        {/* Left Column: Interactive chart + growth sparkline */}
        <div className="flex-1 h-full relative flex flex-col min-w-0">
          {/* Single-page section rail — no Fundamentals / Technical tabs */}
          <div className="flex items-center gap-2 px-4 py-2 glass-card-subtle border-b border-border/10 shrink-0">
            <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Company Intelligence</span>
            <span className="ml-auto text-[10px] font-mono text-muted-foreground/70 hidden md:inline">{tvSymbolDisplay}</span>
          </div>

          {/* Performance strip — real values from the price-history API */}
          <div className="flex items-center gap-4 px-4 py-2 border-b border-border/10 glass-card-subtle shrink-0 overflow-x-auto scrollbar-none">
            <span className="flex items-center gap-1.5 text-[10px] font-bold text-foreground shrink-0">
              <Activity size={12} className="text-primary" /> Performance
            </span>
            {([
              ['1W', history?.perf?.week],
              ['1M', history?.perf?.month ?? spark?.changePct],
              ['3M', history?.perf?.quarter],
            ] as [string, number | undefined][]).map(([label, val]) => (
              <span key={label} className="flex items-center gap-1 shrink-0">
                <span className="text-[9px] font-mono text-muted-foreground">{label}</span>
                <span className={`text-[10px] font-mono font-bold ${val == null ? 'text-muted-foreground/50' : val >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {val == null ? '—' : `${val >= 0 ? '+' : ''}${val.toFixed(2)}%`}
                </span>
              </span>
            ))}
            <span className={cn(
              'ml-auto text-[9px] font-mono shrink-0',
              history?.stale ? 'text-amber-400' : 'text-muted-foreground/50',
            )}>
              {describeSeriesSource(history?.source, history?.freshness as never, history?.observationTime)}
            </span>
          </div>

          <div className="flex-1 w-full h-full relative min-h-0 overflow-y-auto tv-metrics-rail">
            <div className="p-4 md:p-6 text-xs w-full max-w-[1760px] mx-auto space-y-5">
              {/* Row 1 — chart (wide, left) beside the at-a-glance rail (right) */}
              <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
              <div className="xl:col-span-2 space-y-5">
              {/* C — Interactive chart (existing charting engine) */}
              <div className="rounded-2xl border border-border/40 glass-card p-4 space-y-3">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <h2 className="font-serif text-sm font-bold border-b border-border/20 pb-2 flex items-center gap-2">
                    <ChartCandlestick size={14} className="text-primary" /> Interactive Chart
                  </h2>
                  <span className="text-[10px] font-mono text-muted-foreground">{tvSymbolDisplay}</span>
                </div>
                <div className="w-full h-[420px] rounded-xl overflow-hidden">
                  <ChartWidget symbol={symbol} market={effCountry || 'US'} className="h-full" />
                </div>
              </div>

                {/* ── Live metrics (chart, performance, quote stats) ───────── */}
                {/* Real price history chart (ECharts) */}
                <div className="rounded-2xl border border-border/40 glass-card p-4 space-y-3">
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <h2 className="font-serif text-sm font-bold border-b border-border/20 pb-2 flex items-center gap-2">
                      <Activity size={14} className="text-primary" /> Price History
                      <span className={cn(
                        'text-[10px] font-mono font-normal',
                        history?.stale ? 'text-amber-400' : 'text-muted-foreground',
                      )}>
                        {describeSeriesSource(history?.source, history?.freshness as never, history?.observationTime)}
                      </span>
                    </h2>
                    <div className="flex items-center gap-1">
                      {(['1mo', '3mo', '6mo'] as const).map((r) => (
                        <button
                          key={r}
                          onClick={() => setHistoryRange(r)}
                          className={`px-2.5 py-1 rounded-lg text-[10px] font-bold font-mono transition-all cursor-pointer border ${
                            historyRange === r
                              ? 'bg-primary/15 text-primary border-primary/40'
                              : 'text-muted-foreground border-border/40 hover:bg-accent/40'
                          }`}
                        >
                          {r.toUpperCase()}
                        </button>
                      ))}
                    </div>
                  </div>
                  {history && history.bars.length >= 2 ? (
                    <PriceHistoryChart bars={history.bars} currency={history.currency} />
                  ) : (
                    <div className="h-40 flex items-center justify-center text-[11px] text-muted-foreground/60 font-mono">
                      {history === null ? 'Loading price history…' : 'No price history available yet'}
                    </div>
                  )}
                </div>

                {/* ── Performance bars (real % from the series) ──────────── */}
                <div className="rounded-2xl border border-border/40 glass-card p-4 space-y-3">
                  <h2 className="font-serif text-sm font-bold border-b border-border/20 pb-2 flex items-center gap-2">
                    <TrendingUp size={14} className="text-primary" /> Performance
                  </h2>
                  <PerformanceBars
                    week={history?.perf?.week}
                    month={history?.perf?.month}
                    quarter={history?.perf?.quarter}
                  />
                </div>

                {/* ── Volume profile (real daily volume bars) ────────────── */}
                {history && history.bars.some((b) => (b.volume ?? 0) > 0) && (
                  <div className="rounded-2xl border border-border/40 glass-card p-4 space-y-3">
                    <h2 className="font-serif text-sm font-bold border-b border-border/20 pb-2 flex items-center gap-2">
                      <BarChart2 size={14} className="text-primary" /> Daily Volume
                    </h2>
                    <VolumeChart bars={history.bars} />
                  </div>
                )}
              </div>
              <div className="space-y-5">

                {/* AI overview — top-right so it is visible without scrolling */}
                <AiResearchSection research={research} variant="brief" />

                {/* Core metrics */}
                <div className="rounded-2xl border border-border/40 glass-card p-4 space-y-3">
                  <h2 className="font-serif text-sm font-bold border-b border-border/20 pb-2 flex items-center gap-2">
                    <TrendingUp size={14} className="text-primary" /> Core Metrics
                  </h2>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
                    <MetricCard label="Price" value={formatPriceWithCurrency(effCountry, canonicalPrice)} />
                    <MetricCard label="Change %" value={`${isPositive ? '+' : ''}${canonicalChange.toFixed(2)}%`} tone={isPositive ? 'emerald' : 'rose'} hint={GLOSSARY.change} />
                    <MetricCard label="Market Cap" value={effMarketCap} sub={capTier.label !== 'N/A' ? capTier.label : undefined} hint={GLOSSARY.marketCap} />
                    <MetricCard label="P/E Ratio" value={effPe} sub={peRead?.label} hint={GLOSSARY.peRatio} />
                    {!isCryptoAsset && <MetricCard label="EPS" value={effEps} hint={GLOSSARY.eps} />}
                    {!isCryptoAsset && <MetricCard label="Dividend Yield" value={effDividendYield} hint={GLOSSARY.dividendYield} />}
                    {isCryptoAsset && <MetricCard label="Rank" value={effRank < 9999 ? `#${effRank}` : 'N/A'} hint="Size position among all cryptocurrencies." />}
                    <MetricCard label="Volume" value={effVolume} hint={GLOSSARY.volume} />
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
                  <div className="rounded-2xl border border-border/40 glass-card p-4 space-y-2">
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
                      <span>{has52w ? formatPriceWithCurrency(effCountry, eff52Low!) : 'Low N/A'}</span>
                      <span className="text-[9px] text-muted-foreground/60 font-sans max-w-[60%] text-center truncate">{GLOSSARY.range}</span>
                      <span>{has52w ? formatPriceWithCurrency(effCountry, eff52High!) : 'High N/A'}</span>
                    </div>
                  </div>
                )}

                {/* Today's session — OHLC vs previous close */}
                {(effDayOpen != null || effDayHigh != null || effPrevClose != null) && (
                  <div className="rounded-2xl border border-border/40 glass-card p-4 space-y-2.5">
                    <h2 className="font-serif text-sm font-bold border-b border-border/20 pb-2 flex items-center gap-2">
                      <Gauge size={14} className="text-primary" /> Today&apos;s Session
                    </h2>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                      <MetricCard label="Open" value={effDayOpen != null ? formatPriceWithCurrency(effCountry, effDayOpen) : '—'} hint="First traded price today." />
                      <MetricCard label="High" value={effDayHigh != null ? formatPriceWithCurrency(effCountry, effDayHigh) : '—'} />
                      <MetricCard label="Low" value={effDayLow != null ? formatPriceWithCurrency(effCountry, effDayLow) : '—'} />
                      <MetricCard label="Prev Close" value={effPrevClose != null ? formatPriceWithCurrency(effCountry, effPrevClose) : '—'} hint="Yesterday's final price — the base for today's change." />
                    </div>
                  </div>
                )}

                {/* Risk & income stats */}
                {!isCryptoAsset && (effBeta !== 'N/A' || effDividendRate !== 'N/A' || effPe !== 'N/A') && (
                  <div className="rounded-2xl border border-border/40 glass-card p-4 space-y-2.5">
                    <h2 className="font-serif text-sm font-bold border-b border-border/20 pb-2 flex items-center gap-2">
                      <ShieldAlert size={14} className="text-primary" /> Risk &amp; Income
                    </h2>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                      <MetricCard label="Beta (Volatility)" value={effBeta} hint="How much it swings vs the market: >1 = wilder, <1 = calmer." />
                      <MetricCard label="Forward P/E" value={effPe} hint="Price vs yearly profit — see the P/E read above." />
                      <MetricCard label="Dividend / Share" value={effDividendRate !== 'N/A' ? effDividendRate : 'None'} hint="Actual cash paid per share each year." />
                      <MetricCard label="Annual Income" value={effDividendRate !== 'N/A' && effDividendRate !== 'None' && canonicalPrice > 0 ? `${((parseFloat(effDividendRate) / canonicalPrice) * 100).toFixed(2)}%` : '—'} hint="Dividend as % of today's price (yield)." />
                    </div>
                    {(() => {
                      const b = parseFloat(effBeta);
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
                  <div className="rounded-2xl border border-border/40 glass-card p-4 space-y-3">
                    <h2 className="font-serif text-sm font-bold border-b border-border/20 pb-2 flex items-center gap-2">
                      <Landmark size={14} className="text-primary" /> Tokenomics
                    </h2>
                    <div className="grid grid-cols-3 gap-2">
                      <MetricCard label="Circulating" value={effCirc} />
                      <MetricCard label="Total" value={effTotal} />
                      <MetricCard label="Max" value={effMax} />
                    </div>
                    {(() => {
                      const ratio = effMaxRaw && effMaxRaw > 0 ? effCircRaw / effMaxRaw : 1;
                      const ratioPercent = (ratio * 100).toFixed(1);
                      const filledBars = Math.round(ratio * 10);
                      const emptyBars = 10 - filledBars;
                      const barStr = '██████████'.slice(0, filledBars) + '░░░░░░░░░░'.slice(0, emptyBars);
                      return (
                        <div className="rounded-xl border border-border/30 glass-card-subtle px-3 py-2 space-y-1">
                          <div className="flex items-center justify-between text-[10px] uppercase font-bold text-muted-foreground tracking-widest">
                            <span>Circulating Ratio</span><span className="text-foreground font-mono">{ratioPercent}%</span>
                          </div>
                          <div className="text-primary font-mono text-xs">{barStr}</div>
                          <p className="text-[10px] text-muted-foreground">Share of all coins already released — higher means less future dilution.</p>
                        </div>
                      );
                    })()}
                    <div className="grid grid-cols-2 gap-2">
                      <MetricCard label="All-Time High" value={effAth} sub={`${Math.abs(effAthChange).toFixed(1)}% below ATH${effAthDate && effAthDate !== 'N/A' ? ` · ${new Date(effAthDate).toLocaleDateString()}` : ''}`} hint="Highest price ever reached." />
                      <MetricCard label="All-Time Low" value={effAtl} sub={`${Math.abs(effAtlChange).toFixed(1)}% above ATL${effAtlDate && effAtlDate !== 'N/A' ? ` · ${new Date(effAtlDate).toLocaleDateString()}` : ''}`} hint="Lowest price ever reached." />
                    </div>
                    {effFdv !== 'N/A' && (
                      <MetricCard label="Fully Diluted Value" value={effFdv} hint="Total value if every possible coin were in circulation." />
                    )}
                  </div>
                )}

                {/* Profile */}
                <div className="rounded-2xl border border-border/40 glass-card p-4 space-y-2">
                  <h2 className="font-serif text-sm font-bold border-b border-border/20 pb-2 flex items-center gap-2">
                    <Layers size={14} className="text-primary" /> Company Profile
                  </h2>
                  <div className="grid grid-cols-1 gap-1.5">
                    <ProfileRow k="Sector" v={effSector || 'N/A'} />
                    <ProfileRow k="Industry" v={effIndustry || 'N/A'} />
                    <ProfileRow k="Security Type" v={detail?.securityType || (isCryptoAsset ? 'Crypto' : 'Stock')} />
                    <ProfileRow k="Exchange / Market" v={isCryptoAsset ? 'Global Crypto' : (effCountry || 'US')} />
                    {!isCryptoAsset && <ProfileRow k="Short Float" v={effShortFloat} />}
                    {detail?.updatedAt && (
                      <ProfileRow k="Last Updated" v={new Date(detail.updatedAt).toLocaleString()} />
                    )}
                  </div>
                </div>

                {/* F — leadership & management (provider-disclosed) */}
                <LeadershipSection officers={fund.data?.company.leadership ?? []} companyName={fund.data?.company.name ?? effName} />
              </div>{/* end at-a-glance rail */}
              </div>{/* end Row 1 */}

              {/* Row 2 — filings financials (wide, left) beside recent news (right) */}
              <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
                <div className="xl:col-span-2 space-y-5">
                  {/* E/F/H — filings-backed fundamentals (provider snapshot) */}
                  {fund.loading && <FundamentalsLoading />}
                  {!fund.loading && fund.unavailable && (
                    <FundamentalsUnavailable symbol={symbol} market={fundamentalsMarket} reason={fund.error} />
                  )}
                  {!fund.loading && fund.error && !fund.unavailable && (
                    <FundamentalsError message={fund.error} onRetry={fund.refresh} />
                  )}
                  {!fund.loading && fund.data && fund.data.periods.length > 0 && (
                    <div className="flex flex-col gap-5">
                      <TickerHeader data={fund.data} />
                      <FundamentalsFull data={fund.data} compact />
                    </div>
                  )}

                  {/* Fallback: no filings-backed statements (all providers
                      missed, or the instrument has none — e.g. crypto). Eclipse
                      searches the web and shows the sourced findings. */}
                  {!fund.loading && (!fund.data || fund.data.periods.length === 0) && (
                    <div className="flex flex-col gap-5">
                      {fund.data && <TickerHeader data={fund.data} />}
                      <ResearchedFinancialsSection research={research} symbol={symbol} />
                    </div>
                  )}

                  {/* H — valuation caveat */}
                  <ValuationNote />
                </div>
                <div className="space-y-5">
                  {/* G — recent news & material events (JDDS feed) */}
                  <CompanyNewsSection news={news} />
                </div>
              </div>

              {/* Row 3 — technical & risk side by side */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                <TechnicalSection tech={technical} />
                <RiskSection risks={risks} />
              </div>

              {/* Row 4 — AI research conclusion (full width) */}
              <AiResearchSection research={research} variant="conclusion" />
              </div>
          </div>
        </div>

      </div>

      {/* Learn-the-terms glossary toggle */}
      <button
        onClick={() => setShowGlossary(v => !v)}
        className="fixed bottom-4 left-4 z-[60] inline-flex items-center gap-1.5 text-[11px] font-bold text-muted-foreground hover:text-primary glass-card-strong hover:bg-accent border border-border/40 hover:border-primary/40 rounded-xl px-3 py-2 transition-all cursor-pointer"
      >
        <BookOpen size={13} /> {showGlossary ? 'Hide' : 'Learn the terms'}
      </button>
      {showGlossary && (
        <div className="fixed bottom-16 left-4 z-[60] w-[min(420px,calc(100vw-2rem))] rounded-2xl border border-border/40 glass-card-strong p-4 shadow-2xl space-y-2 animate-fade-in max-h-[50dvh] overflow-y-auto">
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
          ].map(([k, v2]) => (
            <div key={k} className="text-[11px] leading-relaxed border-b border-border/10 pb-1.5 last:border-0">
              <span className="font-bold text-foreground">{k}:</span>{' '}
              <span className="text-muted-foreground">{v2}</span>
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
    <div className="rounded-xl border border-border/40 glass-card-subtle px-3 py-2 min-w-0" title={hint || undefined}>
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

// ── Shared ECharts init hook ─────────────────────────────────────────────
function useEChart(option: EChartsOption, deps: React.DependencyList) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chartRef.current = chart;
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return ref;
}

// Real interactive price line chart from the OHLCV series (ECharts, tooltip +
// area gradient, green/red by trend). Dark-theme to match the terminal.
function PriceHistoryChart({ bars, currency }: { bars: PriceBar[]; currency: string }) {
  const dates = bars.map((b) => b.date);
  const closes = bars.map((b) => b.close);
  const up = closes[closes.length - 1] >= closes[0];
  const lineColor = up ? '#34d399' : '#fb7185';

  const option: EChartsOption = {
    backgroundColor: 'transparent',
    grid: { left: 8, right: 8, top: 12, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(18,18,20,0.5)', appendTo: 'body',
      borderColor: 'rgba(255,255,255,0.12)',
      borderWidth: 1,
      padding: [10, 12],
      textStyle: { color: '#e5e5e5', fontSize: 11, fontFamily: 'monospace' },
      extraCssText:
        'backdrop-filter: blur(18px) saturate(1.35); border-radius: 14px; box-shadow: 0 8px 30px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.06);',
      formatter: (params: unknown) => {
        const p = (params as Array<{ axisValue: string; data: number }>)[0];
        if (!p) return '';
        const bar = bars.find((b) => b.date === p.axisValue);
        if (!bar) return '';
        const fmt = (n: number | null) => (n == null ? '—' : n.toLocaleString('en-US', { maximumFractionDigits: 4 }));
        return (
          `<b>${bar.date}</b><br/>` +
          `Close: ${currency} ${fmt(bar.close)}<br/>` +
          `Open: ${currency} ${fmt(bar.open)}<br/>` +
          `High: ${currency} ${fmt(bar.high)}<br/>` +
          `Low: ${currency} ${fmt(bar.low)}` +
          (bar.volume != null ? `<br/>Vol: ${bar.volume.toLocaleString('en-US')}` : '')
        );
      },
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
      axisLabel: { color: 'rgba(160,160,160,0.8)', fontSize: 9, fontFamily: 'monospace' },
      axisTick: { show: false },
      boundaryGap: false,
    },
    yAxis: {
      type: 'value',
      scale: true,
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.03)' } },
      axisLabel: {
        color: 'rgba(160,160,160,0.8)',
        fontSize: 9,
        fontFamily: 'monospace',
        formatter: (v: number) => v.toLocaleString('en-US', { maximumFractionDigits: 2 }),
      },
    },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 14, bottom: 2, borderColor: 'transparent' }],
    series: [
      {
        type: 'line',
        data: closes,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: lineColor, width: 2 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: lineColor + '55' },
            { offset: 1, color: lineColor + '00' },
          ]),
        },
      },
    ],
  };

  const ref = useEChart(option, [bars, currency]);
  return <div ref={ref} style={{ width: '100%', height: 300 }} />;
}

// Horizontal performance bars — 1W / 1M / 3M real % changes.
function PerformanceBars({ week, month, quarter }: { week?: number; month?: number; quarter?: number }) {
  const rows: Array<[string, number | undefined]> = [
    ['1 Week', week],
    ['1 Month', month],
    ['3 Months', quarter],
  ];
  const maxAbs = Math.max(...rows.map(([, v]) => Math.abs(v ?? 0)), 1);
  return (
    <div className="space-y-2.5">
      {rows.map(([label, val]) => {
        const has = val != null && Number.isFinite(val);
        const pos = has && (val as number) >= 0;
        const width = has ? Math.max(2, (Math.abs(val as number) / maxAbs) * 50) : 0;
        return (
          <div key={label} className="flex items-center gap-3">
            <span className="w-16 text-[10px] font-bold text-muted-foreground shrink-0">{label}</span>
            <div className="relative flex-1 h-4 flex items-center">
              <div className="absolute left-1/2 top-0 bottom-0 w-px bg-border/60" />
              {has && (
                <div
                  className={cn('absolute top-1 bottom-1 rounded-sm', pos ? 'bg-emerald-500/60' : 'bg-rose-500/60')}
                  style={pos ? { left: '50%', width: `${width}%` } : { right: '50%', width: `${width}%` }}
                />
              )}
            </div>
            <span className={cn(
              'w-16 text-right text-[10px] font-mono font-bold shrink-0',
              !has ? 'text-muted-foreground/50' : pos ? 'text-emerald-400' : 'text-rose-400',
            )}>
              {has ? `${pos ? '+' : ''}${(val as number).toFixed(2)}%` : '—'}
            </span>
          </div>
        );
      })}
      <p className="text-[10px] text-muted-foreground/60">
        Change from N trading days ago — computed from the real daily close series above.
      </p>
    </div>
  );
}

// Daily volume bars from the real series (ECharts, shares the tooltip style).
function VolumeChart({ bars }: { bars: PriceBar[] }) {
  const dates = bars.map((b) => b.date);
  const volumes = bars.map((b) => b.volume ?? 0);
  const upFlags = bars.map((b, i) => (i === 0 ? true : b.close >= bars[i - 1].close));

  const option: EChartsOption = {
    backgroundColor: 'transparent',
    grid: { left: 8, right: 8, top: 12, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(18,18,20,0.5)', appendTo: 'body',
      borderColor: 'rgba(255,255,255,0.12)',
      borderWidth: 1,
      padding: [10, 12],
      textStyle: { color: '#e5e5e5', fontSize: 11, fontFamily: 'monospace' },
      extraCssText:
        'backdrop-filter: blur(18px) saturate(1.35); border-radius: 14px; box-shadow: 0 8px 30px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.06);',
      formatter: (params: unknown) => {
        const p = (params as Array<{ axisValue: string; data: number }>)[0];
        if (!p) return '';
        return `<b>${p.axisValue}</b><br/>Volume: ${p.data.toLocaleString('en-US')}`;
      },
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
      axisLabel: { color: 'rgba(160,160,160,0.8)', fontSize: 9, fontFamily: 'monospace' },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.03)' } },
      axisLabel: {
        color: 'rgba(160,160,160,0.8)',
        fontSize: 9,
        fontFamily: 'monospace',
        formatter: (v: number) => {
          if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
          if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
          if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
          return String(v);
        },
      },
    },
    series: [
      {
        type: 'bar',
        data: volumes.map((v, i) => ({ value: v, itemStyle: { color: upFlags[i] ? 'rgba(52,211,153,0.55)' : 'rgba(251,113,133,0.55)' } })),
        barMaxWidth: 8,
      },
    ],
  };

  const ref = useEChart(option, [bars]);
  return <div ref={ref} style={{ width: '100%', height: 160 }} />;
}