'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import * as echarts from 'echarts';
import type { EChartsOption } from 'echarts';
import {
  X, TrendingUp, BarChart2, Layers,
  HelpCircle, Landmark, Gauge, ChartCandlestick, ScrollText,
} from '@/lib/icons';
import { ChartWidget } from '@/components/chart/chart-widget';
import { cn } from '@/lib/utils';
import { describeSeriesSource } from '@/lib/chart/observation-freshness';
import { formatPriceWithCurrency } from '@/lib/market-currency';
import { countryToMarketId } from '@/lib/markets';
import { useFundamentals } from '@/components/screens/fundamentals/use-fundamentals';
import {
  FundamentalsBody,
  type FundamentalSectionId,
  LoadingState as FundamentalsLoading,
  UnavailableState as FundamentalsUnavailable,
  ErrorState as FundamentalsError,
} from '@/components/screens/fundamentals/panel';
import { FilingsSection } from '@/components/screens/fundamentals/filings-section';
import { computeTechnical } from '@/lib/company/technical';
import { computeCompanyRisk } from '@/lib/company/risk';
import { useCompanyNews } from '@/lib/company/use-company-news';
import { useCompanyResearch } from '@/lib/company/use-company-research';
import {
  AiResearchSection,
  CompanyNewsSection,
  TechnicalRiskSection,
  SectionShell,
  ValuationNote,
  LeadershipSection,
  ResearchedFinancialsSection,
} from '@/components/screens/company/sections';
import { StockIntelligencePanel } from '@/components/screens/stock-detail/charts/intelligence-panel';
import { SourceVerificationPanel } from '@/components/screens/stock-detail/verification-panel';

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
  forwardPE?: string;
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
  forwardPE = 'N/A',
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
  const [chartView, setChartView] = useState<'interactive' | 'history'>('interactive');
  const [fundSection, setFundSection] = useState<FundamentalSectionId>('overview');
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
  const effForwardPe = forwardPE !== 'N/A'
    ? forwardPE
    : (detail?.forwardPE && detail.forwardPE !== 'N/A' ? detail.forwardPE : 'N/A');
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
  // with derived 1W/1M/3M performance. Powers the history chart, the
  // performance chips and the deterministic technical snapshot.
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
  const [historyStatus, setHistoryStatus] = useState<'loading' | 'ready' | 'empty' | 'error'>('loading');
  const [historyRange, setHistoryRange] = useState<'1mo' | '3mo' | '6mo'>('3mo');
  useEffect(() => {
    if (!mounted) return;
    let cancelled = false;
    setHistoryStatus('loading');
    (async () => {
      try {
        const res = await fetch(
          `/api/price-history?symbol=${encodeURIComponent(symbol)}&market=${encodeURIComponent(effCountry || 'US')}&range=${historyRange}`,
          { signal: AbortSignal.timeout(25000) },
        );
        const data = await res.json();
        if (cancelled) return;
        if (Array.isArray(data.series) && data.series.length >= 2) {
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
          setHistoryStatus('ready');
        } else {
          setHistory(null);
          setHistoryStatus('empty');
        }
      } catch {
        if (!cancelled) {
          setHistory(null);
          setHistoryStatus('error');
        }
      }
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

  // Non-derived providers behind the fundamentals snapshot (for the section subtitle).
  const fundSources = fund.data ? fund.data.contributors.filter((c) => c !== 'derived') : [];

  // Live growth series used by the chart toolbar performance chips.
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
    <div className="tv-overlay fixed inset-0 z-[95] flex h-[100dvh] w-full flex-col bg-black/90 backdrop-blur-md text-foreground animate-fade-in font-sans">
      {/* Header */}
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-border/30 px-4 py-2.5 glass-card-subtle shadow-sm md:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 text-primary">
            <BarChart2 className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
              <span className="shrink-0 rounded-lg bg-accent/60 px-2 py-0.5 font-mono text-base font-bold text-foreground md:text-lg">
                {symbol}
              </span>
              <h1 className="truncate font-serif text-sm font-semibold text-foreground md:text-base">{effName}</h1>
              {effSector && (
                <span className="hidden shrink-0 rounded-md bg-accent/40 px-2 py-0.5 text-[10px] text-muted-foreground md:inline">
                  {effSector}
                </span>
              )}
              {effCountry && (
                <span
                  title="Market / exchange"
                  className="hidden shrink-0 rounded-md border border-primary/20 bg-primary/10 px-2 py-0.5 font-mono text-[10px] text-primary md:inline"
                >
                  {effCountry}
                </span>
              )}
            </div>
            <p className="mt-0.5 truncate text-[10px] text-muted-foreground">
              {isCryptoAsset ? 'Crypto asset' : 'Equity'}
              {effIndustry ? ` · ${effIndustry}` : ''}
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2 md:gap-3">
          <div className="text-right">
            <div className="font-mono text-base font-extrabold leading-tight text-foreground md:text-xl">
              {formatPriceWithCurrency(effCountry, canonicalPrice)}
            </div>
            <div className="flex items-center justify-end gap-1.5 font-mono text-[10px] md:text-[11px]">
              <span className={isPositive ? 'text-emerald-400' : 'text-rose-400'}>
                {isPositive ? '▲ +' : '▼ '}{canonicalChange.toFixed(2)}%
              </span>
              {quote && (
                <span
                  title={quote.updatedAt ? `Updated ${new Date(quote.updatedAt).toLocaleString()}` : undefined}
                  className={quote.stale ? 'text-amber-400' : 'text-muted-foreground/70'}
                >
                  · {quote.stale ? 'stale' : 'live'}{quote.source ? ` · ${quote.source}` : ''}
                </span>
              )}
            </div>
          </div>
          <button
            onClick={() => setShowGlossary((v) => !v)}
            title="What these numbers mean"
            className="rounded-xl border border-border/40 p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground cursor-pointer"
          >
            <HelpCircle size={16} />
          </button>
          <button
            onClick={onClose}
            title="Back to screener (Esc)"
            className="rounded-xl border border-border/40 p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground cursor-pointer"
          >
            <X size={17} />
          </button>
        </div>
      </header>

      <div className="tv-metrics-rail min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <div className="mx-auto w-full max-w-[1600px] space-y-4 p-4 md:p-6">

          {/* Key statistics — one surface instead of four separate cards */}
          <SectionShell
            icon={<Gauge size={14} className="text-primary" />}
            title="Key statistics"
            subtitle={detail?.updatedAt ? `updated ${new Date(detail.updatedAt).toLocaleString()}` : 'latest available snapshot'}
          >
            <div className={cn(
              'grid grid-cols-2 gap-2 sm:grid-cols-4',
              isCryptoAsset ? 'xl:grid-cols-6' : 'xl:grid-cols-8',
            )}>
              {isCryptoAsset ? (
                <>
                  <MetricCard label="Market Cap" value={effMarketCap} hint={GLOSSARY.marketCap} />
                  <MetricCard label="Rank" value={effRank < 9999 ? `#${effRank}` : 'N/A'} hint="Size position among all cryptocurrencies." />
                  <MetricCard label="Circulating" value={effCirc} />
                  <MetricCard label="Total Supply" value={effTotal} />
                  <MetricCard label="Max Supply" value={effMax} />
                  <MetricCard label="Volume" value={effVolume} sub="Today" hint={GLOSSARY.volume} />
                </>
              ) : (
                <>
                  <MetricCard label="Market Cap" value={effMarketCap} sub={capTier.label !== 'N/A' ? capTier.label : undefined} hint={GLOSSARY.marketCap} />
                  <MetricCard label="P/E Ratio" value={effPe} sub={peRead?.label} hint={GLOSSARY.peRatio} />
                  <MetricCard label="Forward P/E" value={effForwardPe} hint={GLOSSARY.forwardPE} />
                  <MetricCard label="EPS" value={effEps} sub="Trailing" hint={GLOSSARY.eps} />
                  <MetricCard label="Dividend Yield" value={effDividendYield} sub={effDividendRate !== 'N/A' ? `${effDividendRate}/sh` : undefined} hint={GLOSSARY.dividendYield} />
                  <MetricCard label="Beta" value={effBeta} sub="vs market" hint={GLOSSARY.beta} />
                  <MetricCard label="Volume" value={effVolume} sub="Today" hint={GLOSSARY.volume} />
                  <MetricCard label="Short Float" value={effShortFloat} hint="Shares sold short as a percentage of the float." />
                </>
              )}
            </div>

            <div className="grid grid-cols-2 gap-x-4 gap-y-2 border-t border-border/10 pt-3 sm:grid-cols-4">
              <StatRow label="Open" value={effDayOpen != null ? formatPriceWithCurrency(effCountry, effDayOpen) : '—'} hint={GLOSSARY.open} />
              <StatRow label="Day High" value={effDayHigh != null ? formatPriceWithCurrency(effCountry, effDayHigh) : '—'} />
              <StatRow label="Day Low" value={effDayLow != null ? formatPriceWithCurrency(effCountry, effDayLow) : '—'} />
              <StatRow label="Prev Close" value={effPrevClose != null ? formatPriceWithCurrency(effCountry, effPrevClose) : '—'} hint={GLOSSARY.prevClose} />
            </div>

            {!isCryptoAsset && has52w && (
              <div className="border-t border-border/10 pt-3">
                <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                  <span>52-Week Range</span>
                  {rangePct != null && <span className="font-mono text-foreground">{Math.round(rangePct)}% of range</span>}
                </div>
                <div className="relative mt-2 h-1.5 w-full rounded-full bg-accent/40">
                  {rangePct != null && (
                    <div
                      className="absolute top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full bg-primary ring-2 ring-background transition-all"
                      style={{ left: `calc(${rangePct}% - 5px)` }}
                    />
                  )}
                </div>
                <div className="mt-1.5 flex justify-between font-mono text-[10px] text-muted-foreground">
                  <span>{formatPriceWithCurrency(effCountry, eff52Low!)}</span>
                  <span>{formatPriceWithCurrency(effCountry, eff52High!)}</span>
                </div>
              </div>
            )}

            {peRead && (
              <p className={cn(
                'border-t border-border/10 pt-2 text-[10px] leading-relaxed',
                peRead.tone === 'emerald' && 'text-emerald-300',
                peRead.tone === 'primary' && 'text-primary',
                peRead.tone === 'amber' && 'text-amber-300',
                peRead.tone === 'rose' && 'text-rose-300',
              )}>
                <span className="font-bold">{peRead.label}:</span> {peRead.note}
              </p>
            )}
          </SectionShell>

          {/* Chart — one card, switchable views, performance inline */}
          <SectionShell
            icon={<ChartCandlestick size={14} className="text-primary" />}
            title="Price chart"
            subtitle={describeSeriesSource(history?.source, history?.freshness as never, history?.observationTime)}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Performance</span>
              {([
                ['1W', history?.perf?.week],
                ['1M', history?.perf?.month ?? spark?.changePct],
                ['3M', history?.perf?.quarter],
              ] as [string, number | undefined][]).map(([label, val]) => (
                <span key={label} className="flex items-center gap-1 rounded-md border border-border/30 px-1.5 py-0.5">
                  <span className="text-[9px] font-mono text-muted-foreground">{label}</span>
                  <span className={cn(
                    'text-[10px] font-mono font-bold',
                    val == null ? 'text-muted-foreground/50' : val >= 0 ? 'text-emerald-400' : 'text-rose-400',
                  )}>
                    {val == null ? '—' : `${val >= 0 ? '+' : ''}${val.toFixed(2)}%`}
                  </span>
                </span>
              ))}
              <div className="ml-auto flex flex-wrap items-center gap-1.5">
                <div className="flex items-center gap-0.5 rounded-lg bg-accent/30 p-0.5">
                  {(['interactive', 'history'] as const).map((view) => (
                    <button
                      key={view}
                      onClick={() => setChartView(view)}
                      className={cn(
                        'rounded-md px-2 py-1 text-[10px] font-bold transition-colors cursor-pointer',
                        chartView === view
                          ? 'bg-muted-foreground/20 text-foreground'
                          : 'text-muted-foreground hover:text-foreground',
                      )}
                    >
                      {view === 'interactive' ? 'Interactive' : 'History'}
                    </button>
                  ))}
                </div>
                {chartView === 'history' && (
                  <div className="flex items-center gap-0.5 rounded-lg bg-accent/30 p-0.5">
                    {(['1mo', '3mo', '6mo'] as const).map((r) => (
                      <button
                        key={r}
                        onClick={() => setHistoryRange(r)}
                        className={cn(
                          'rounded-md px-2 py-1 text-[10px] font-bold font-mono transition-colors cursor-pointer',
                          historyRange === r
                            ? 'bg-primary/15 text-primary'
                            : 'text-muted-foreground hover:text-foreground',
                        )}
                      >
                        {r.replace('mo', 'M')}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <div className="h-[clamp(340px,48vh,520px)] min-h-[340px] w-full">
              {chartView === 'interactive' ? (
                <ChartWidget symbol={symbol} market={effCountry || 'US'} className="h-full" />
              ) : history && history.bars.length >= 2 ? (
                <PriceVolumeChart bars={history.bars} currency={history.currency} />
              ) : (
                <div className="flex h-full items-center justify-center px-4 text-center font-mono text-[11px] text-muted-foreground/60">
                  {history
                    ? 'No price history available yet'
                    : historyStatus === 'error'
                      ? 'Price history is unavailable right now'
                      : historyStatus === 'empty'
                        ? 'No price history available yet'
                        : 'Loading price history…'}
                </div>
              )}
            </div>
          </SectionShell>

          {/* Cross-source charts: price, drawdown, benchmark return, valuation, earnings surprise */}
          <StockIntelligencePanel symbol={symbol} market={fundamentalsMarket} />
          <SourceVerificationPanel
            symbol={symbol}
            name={stockName}
            market={fundamentalsMarket}
            price={price}
            enabled={mounted}
          />

          <AiResearchSection research={research} variant="brief" />

          {/* Fundamentals — tabbed so four deep sections never stack at once */}
          {fund.loading && (
            <SectionShell icon={<TrendingUp size={14} className="text-primary" />} title="Fundamentals" subtitle="loading filings-backed data">
              <FundamentalsLoading />
            </SectionShell>
          )}
          {!fund.loading && fund.unavailable && (
            <FundamentalsUnavailable symbol={symbol} market={fundamentalsMarket} reason={fund.error} />
          )}
          {!fund.loading && fund.error && !fund.unavailable && (
            <FundamentalsError message={fund.error} onRetry={fund.refresh} />
          )}
          {!fund.loading && fund.data && fund.data.periods.length > 0 && (
            <SectionShell
              icon={<TrendingUp size={14} className="text-primary" />}
              title="Fundamentals"
              subtitle={`${fund.data.provenance} · ${fundSources.length} source${fundSources.length === 1 ? '' : 's'}${fund.data.currency ? ` · ${fund.data.currency}` : ''}`}
              right={<span className="text-[9px] font-mono text-muted-foreground">filings-backed</span>}
            >
              <FundamentalsBody
                data={fund.data}
                section={fundSection}
                onSectionChange={setFundSection}
                compact
              />
              <ValuationNote />
            </SectionShell>
          )}
          {!fund.loading && (!fund.data || fund.data.periods.length === 0) && (
            <ResearchedFinancialsSection research={research} symbol={symbol} />
          )}

          {/* Filings are independent of fundamentals: a company with no
              statement data must still be able to open its official filing list. */}
          {!fund.loading && !(fund.data && fund.data.periods.length > 0) && (
            <SectionShell
              icon={<ScrollText size={14} className="text-primary" />}
              title="Filings"
              subtitle="official filing index"
            >
              <FilingsSection symbol={symbol} market={fundamentalsMarket} />
            </SectionShell>
          )}

          {/* Recent news — clamped list */}
          <CompanyNewsSection news={news} />

          {/* Crypto tokenomics */}
          {isCryptoAsset && (
            <SectionShell
              icon={<Landmark size={14} className="text-primary" />}
              title="Tokenomics"
              subtitle={effName}
            >
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
                    <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                      <span>Circulating Ratio</span><span className="font-mono text-foreground">{ratioPercent}%</span>
                    </div>
                    <div className="font-mono text-xs text-primary">{barStr}</div>
                    <p className="text-[10px] text-muted-foreground">Share of all coins already released — higher means less future dilution.</p>
                  </div>
                );
              })()}
              <div className="grid grid-cols-2 gap-2">
                <MetricCard
                  label="All-Time High"
                  value={effAth}
                  sub={`${Math.abs(effAthChange).toFixed(1)}% below ATH${effAthDate && effAthDate !== 'N/A' ? ` · ${new Date(effAthDate).toLocaleDateString()}` : ''}`}
                  hint="Highest price ever reached."
                />
                <MetricCard
                  label="All-Time Low"
                  value={effAtl}
                  sub={`${Math.abs(effAtlChange).toFixed(1)}% above ATL${effAtlDate && effAtlDate !== 'N/A' ? ` · ${new Date(effAtlDate).toLocaleDateString()}` : ''}`}
                  hint="Lowest price ever reached."
                />
              </div>
              {effFdv !== 'N/A' && <MetricCard label="Fully Diluted Value" value={effFdv} hint="Total value if every possible coin were in circulation." />}
            </SectionShell>
          )}

          {/* Technical & risk — one card, two internal columns */}
          <TechnicalRiskSection tech={technical} risks={risks} />

          {/* Company profile + leadership — one compact card */}
          <SectionShell
            icon={<Layers size={14} className="text-primary" />}
            title="Company profile"
            subtitle={effName}
            right={<span className="text-[9px] font-mono text-muted-foreground">{detail?.securityType || (isCryptoAsset ? 'Crypto' : 'Stock')}</span>}
          >
            <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
              <div className="space-y-1.5">
                <ProfileRow k="Sector" v={effSector || 'N/A'} />
                <ProfileRow k="Industry" v={effIndustry || 'N/A'} />
                <ProfileRow k="Security Type" v={detail?.securityType || (isCryptoAsset ? 'Crypto' : 'Stock')} />
                <ProfileRow k="Exchange / Market" v={isCryptoAsset ? 'Global Crypto' : (effCountry || 'US')} />
                {detail?.updatedAt && <ProfileRow k="Last Updated" v={new Date(detail.updatedAt).toLocaleString()} />}
              </div>
              {!isCryptoAsset && (
                <div className="min-w-0 border-t border-border/10 pt-4 md:border-l md:border-t-0 md:pl-5 md:pt-0">
                  <h3 className="mb-2 flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                    <Landmark size={12} className="text-primary" /> Leadership
                    <span className="ml-auto font-normal normal-case tracking-normal text-[9px]">provider-disclosed</span>
                  </h3>
                  <LeadershipSection
                    officers={fund.data?.company.leadership ?? []}
                    companyName={fund.data?.company.name ?? effName}
                    bare
                  />
                </div>
              )}
            </div>
          </SectionShell>

        </div>
      </div>

      {/* Glossary — anchored to the header instead of floating over content */}
      {showGlossary && (
        <div className="fixed right-3 top-[100px] z-[70] max-h-[calc(100dvh-6rem)] w-[min(420px,calc(100vw-1.5rem))] space-y-2 overflow-y-auto rounded-2xl border border-border/40 glass-card-strong p-4 shadow-2xl animate-fade-in md:top-[68px]">
          <h3 className="flex items-center gap-1.5 text-xs font-bold text-primary">
            <HelpCircle size={13} /> What these numbers mean
          </h3>
          {[
            ['Market Cap', GLOSSARY.marketCap],
            ['P/E Ratio', GLOSSARY.peRatio],
            ['Forward P/E', GLOSSARY.forwardPE],
            ['EPS', GLOSSARY.eps],
            ['Dividend Yield', GLOSSARY.dividendYield],
            ['Volume', GLOSSARY.volume],
            ['Change', GLOSSARY.change],
            ['Open / Prev Close', `${GLOSSARY.open} ${GLOSSARY.prevClose}`],
            ['Beta', GLOSSARY.beta],
            ['52-Week Range', GLOSSARY.range],
            ['RSI (on chart)', GLOSSARY.rsi],
          ].map(([k, v2]) => (
            <div key={k} className="border-b border-border/10 pb-1.5 text-[11px] leading-relaxed last:border-0">
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
    <div className="min-w-0 rounded-xl border border-border/30 glass-card-subtle px-3 py-2.5" title={hint || undefined}>
      <div className="truncate text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={cn(
        'truncate font-mono text-sm font-bold text-foreground',
        tone === 'emerald' && 'text-emerald-400',
        tone === 'rose' && 'text-rose-400',
      )}>{value}</div>
      {sub && <div className="truncate text-[10px] text-muted-foreground/80">{sub}</div>}
    </div>
  );
}

function StatRow({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="min-w-0" title={hint || undefined}>
      <div className="truncate text-[9px] font-bold uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="truncate font-mono text-[11px] font-semibold text-foreground">{value}</div>
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

// Price + volume in one chart: the daily close line sits above the volume
// bars, sharing one x-axis and one zoom window. This replaces the old
// three-chart stack (price history, performance bars, daily volume).
function PriceVolumeChart({ bars, currency }: { bars: PriceBar[]; currency: string }) {
  const dates = bars.map((b) => b.date);
  const closes = bars.map((b) => b.close);
  const volumes = bars.map((b) => b.volume ?? 0);
  const upFlags = bars.map((b, i) => (i === 0 ? true : b.close >= bars[i - 1].close));
  const up = closes[closes.length - 1] >= closes[0];
  const lineColor = up ? '#34d399' : '#fb7185';
  const axisColor = 'rgba(160,160,160,0.8)';

  const option: EChartsOption = {
    backgroundColor: 'transparent',
    grid: [
      { left: 8, right: 8, top: 12, height: '58%', containLabel: true },
      { left: 8, right: 8, top: '72%', height: '16%', containLabel: true },
    ],
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
        const p = (params as Array<{ axisValue?: string }>)[0];
        if (!p?.axisValue) return '';
        const bar = bars.find((b) => b.date === p.axisValue);
        if (!bar) return '';
        const fmt = (n: number | null) => (n == null ? '—' : n.toLocaleString('en-US', { maximumFractionDigits: 4 }));
        const fmtVol = (n: number | null) => {
          if (n == null) return '—';
          if (n >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
          if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
          if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
          return n.toLocaleString('en-US');
        };
        return (
          `<b>${bar.date}</b><br/>` +
          `Close: ${currency} ${fmt(bar.close)}<br/>` +
          `Open: ${currency} ${fmt(bar.open)}<br/>` +
          `High: ${currency} ${fmt(bar.high)}<br/>` +
          `Low: ${currency} ${fmt(bar.low)}<br/>` +
          `Volume: ${fmtVol(bar.volume)}`
        );
      },
    },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    xAxis: [
      {
        type: 'category',
        data: dates,
        gridIndex: 0,
        boundaryGap: false,
        axisLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
        axisLabel: { show: false },
        axisTick: { show: false },
      },
      {
        type: 'category',
        data: dates,
        gridIndex: 1,
        boundaryGap: true,
        axisLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
        axisLabel: { color: axisColor, fontSize: 9, fontFamily: 'monospace' },
        axisTick: { show: false },
      },
    ],
    yAxis: [
      {
        type: 'value',
        gridIndex: 0,
        scale: true,
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.03)' } },
        axisLabel: {
          color: axisColor,
          fontSize: 9,
          fontFamily: 'monospace',
          formatter: (v: number) => v.toLocaleString('en-US', { maximumFractionDigits: 2 }),
        },
      },
      {
        type: 'value',
        gridIndex: 1,
        splitNumber: 2,
        splitLine: { show: false },
        axisLabel: {
          color: axisColor,
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
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1] },
      { type: 'slider', xAxisIndex: [0, 1], height: 12, bottom: 2, borderColor: 'transparent' },
    ],
    series: [
      {
        name: 'Close',
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
      {
        name: 'Volume',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volumes.map((v, i) => ({
          value: v,
          itemStyle: { color: upFlags[i] ? 'rgba(52,211,153,0.55)' : 'rgba(251,113,133,0.55)' },
        })),
        barMaxWidth: 8,
      },
    ],
  };

  const ref = useEChart(option, [bars, currency]);
  return <div ref={ref} className="h-full w-full" />;
}
