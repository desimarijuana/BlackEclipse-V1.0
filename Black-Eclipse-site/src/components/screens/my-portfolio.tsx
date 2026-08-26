'use client';

import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import * as echarts from 'echarts';
import type { EChartsOption } from 'echarts';
import {
  Briefcase, ArrowUpRight, ArrowDownRight, Sparkles,
  Wallet, TrendingUp, History, PieChart,
  Plus, Trash2, Shield, Activity, PlusCircle,
  AlertCircle, BarChart2, DollarSign, Calendar,
  X, Search, Star, ChevronDown, ChevronUp, Flame} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { TopLoader } from '@/components/ui/top-loader';
import { SkeletonCardGrid, SkeletonHeader, SkeletonPanel, SkeletonTable } from '@/components/ui/skeleton';
import { usePortfolioEngine, PortfolioStats } from '@/hooks/use-portfolio-engine';

// ─── Shared panel / tile styling (site design system) ──────────────────────
const PANEL = 'bg-[#0f0f0f]/40 dark:bg-[#0f0f0f]/40 bg-white/50 backdrop-blur-xl border border-white/10 dark:border-white/5 rounded-2xl shadow-sm';
const TILE = 'bg-muted/10 border border-border/20 rounded-xl';
const UP = '#34d399';
const DOWN = '#fb7185';

export interface Transaction {
  id: string;
  type: 'BUY' | 'SELL' | 'DEPOSIT' | 'WITHDRAWAL';
  symbol: string;
  quantity: number;
  price: number;
  fee: number;
  date: string;
  notes?: string;
}

export interface Alert {
  id: string;
  symbol: string;
  type: 'PRICE_ABOVE' | 'PRICE_BELOW' | 'ALLOCATION_EXCEEDS' | 'DAILY_MOVE';
  target: number;
  isActive: boolean;
}

const DEFAULT_TRANSACTIONS: Transaction[] = [
  { id: 'tx-1', type: 'BUY', symbol: 'BTC', quantity: 0.25, price: 61500.00, fee: 15.00, date: '2026-06-01' },
  { id: 'tx-2', type: 'BUY', symbol: 'ETH', quantity: 4.20, price: 2950.00, fee: 12.50, date: '2026-06-02' },
  { id: 'tx-3', type: 'BUY', symbol: 'SOL', quantity: 25.00, price: 110.00, fee: 2.50, date: '2026-06-03' },
];

interface DemoAsset {
  symbol: string;
  name: string;
  price: number;
  changePercent: number;
  category: string;
  aiTag?: string;
}

const DEMO_LIVE_PRICES: DemoAsset[] = [
  { symbol: 'BTC', name: 'Bitcoin', price: 67840.00, changePercent: 2.14, category: 'Store of Value', aiTag: 'ETF inflows accelerating — spot demand absorbing supply near range highs.' },
  { symbol: 'ETH', name: 'Ethereum', price: 3500.20, changePercent: 2.41, category: 'Smart Contracts', aiTag: 'Staking yield compressing as inflows rise; watch L2 fee migration.' },
  { symbol: 'SOL', name: 'Solana', price: 168.40, changePercent: 3.82, category: 'Smart Contracts', aiTag: 'Highest beta position — DEX volumes driving outsized momentum.' },
  { symbol: 'BNB', name: 'BNB', price: 585.50, changePercent: -1.20, category: 'Exchange' },
  { symbol: 'XRP', name: 'Ripple', price: 0.53, changePercent: -0.84, category: 'Payments' },
  { symbol: 'DOGE', name: 'Dogecoin', price: 0.16, changePercent: 1.12, category: 'Meme', aiTag: 'Sentiment-driven; correlation to BTC spikes during risk-off moves.' },
  { symbol: 'ADA', name: 'Cardano', price: 0.45, changePercent: -1.32, category: 'Smart Contracts' },
];

// Per-asset risk profile used by stress testing, risk metrics & Monte Carlo.
const RISK: Record<string, { beta: number; vol: number; sharpe: number; mdd: number; target: number }> = {
  BTC:  { beta: 1.00, vol: 48.0, sharpe: 1.42, mdd: -32.0, target: 35 },
  ETH:  { beta: 1.18, vol: 62.0, sharpe: 1.10, mdd: -45.0, target: 25 },
  SOL:  { beta: 1.55, vol: 88.0, sharpe: 0.94, mdd: -62.0, target: 15 },
  BNB:  { beta: 0.92, vol: 52.0, sharpe: 1.05, mdd: -38.0, target: 10 },
  XRP:  { beta: 1.08, vol: 66.0, sharpe: 0.72, mdd: -52.0, target: 8 },
  DOGE: { beta: 1.42, vol: 95.0, sharpe: 0.58, mdd: -70.0, target: 4 },
  ADA:  { beta: 1.22, vol: 71.0, sharpe: 0.49, mdd: -58.0, target: 3 },
};

const CORR: Record<string, Record<string, number>> = {
  BTC:  { BTC: 1, ETH: 0.86, SOL: 0.78, BNB: 0.81, XRP: 0.72, DOGE: 0.74, ADA: 0.7 },
  ETH:  { ETH: 1, SOL: 0.82, BNB: 0.79, XRP: 0.68, DOGE: 0.71, ADA: 0.76 },
  SOL:  { SOL: 1, BNB: 0.7, XRP: 0.64, DOGE: 0.69, ADA: 0.73 },
  BNB:  { BNB: 1, XRP: 0.66, DOGE: 0.62, ADA: 0.65 },
  XRP:  { XRP: 1, DOGE: 0.6, ADA: 0.63 },
  DOGE: { DOGE: 1, ADA: 0.61 },
  ADA:  { ADA: 1 },
};

const STRESS_SCENARIOS = [
  { id: 'market', label: 'Market −25%', desc: 'Broad crypto drawdown — correlations converge toward 1 and alts bleed harder than majors.', mkt: -25, alt: 0 },
  { id: 'btc', label: 'BTC −10% / alts −25%', desc: 'Bitcoin-led flush where high-beta alts de-risk twice as fast.', mkt: -10, alt: -15 },
  { id: 'rates', label: 'Liquidity shock', desc: 'Rate scare drains leverage; thin-liquidity positions gap down.', mkt: -8, alt: -10 },
  { id: 'capitulation', label: 'Capitulation −45%', desc: 'Cycle-bottom event: forced deleveraging across the entire complex.', mkt: -30, alt: -15 },
  { id: 'meltup', label: 'Melt-up +20%', desc: 'Risk-on rally led by high-beta smart-contract assets.', mkt: 12, alt: 8 },
];

const ALERT_TYPES: Array<{ value: Alert['type']; label: string }> = [
  { value: 'PRICE_ABOVE', label: 'Price above' },
  { value: 'PRICE_BELOW', label: 'Price below' },
  { value: 'DAILY_MOVE', label: '24h move >' },
];

const AVAILABLE_CASH = 8450.32;

// ── Formatting helpers ──────────────────────────────────────────────────────
const fmtUsd = (n: number, dp = 2) =>
  `${n < 0 ? '-' : ''}$${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp })}`;
const fmtK = (n: number) => {
  const a = Math.abs(n);
  if (a >= 1e6) return `${n < 0 ? '-' : ''}$${(a / 1e6).toFixed(2)}M`;
  if (a >= 1000) return `$${Math.round(n / 1000)}k`;
  return `$${Math.round(n)}`;
};
const fmtPct = (n: number) => `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;

// Deterministic pseudo-random so charts stay stable across re-renders.
function seeded(seed: number, n: number): number[] {
  let s = seed % 2147483647;
  if (s <= 0) s += 2147483646;
  return Array.from({ length: n }, () => {
    s = (s * 16807) % 2147483647;
    return s / 2147483647;
  });
}

function cssVar(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

// ── Apache ECharts wrapper ──────────────────────────────────────────────────
interface EChartProps {
  option: EChartsOption;
  height?: number | string;
  className?: string;
  notMerge?: boolean;
}

function EChart({ option, height = 300, className, notMerge = true }: EChartProps) {
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
    chartRef.current?.setOption(option, notMerge);
  }, [option, notMerge]);

  return <div ref={ref} className={className} style={{ width: '100%', height }} />;
}

// Tiny inline sparkline for expanded holding rows.
function Sparkline({ up }: { up: boolean }) {
  const pts = up ? [30, 26, 27, 21, 17, 18, 11, 6] : [10, 14, 13, 19, 23, 22, 28, 34];
  const d = pts.map((y, i) => `${i === 0 ? 'M' : 'L'} ${(i / (pts.length - 1)) * 140} ${y}`).join(' ');
  return (
    <svg width="140" height="40" viewBox="0 0 140 40">
      <path d={d} fill="none" stroke={up ? UP : DOWN} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

// ── Live asset shape kept for compatibility with existing consumers ─────────
interface LiveAsset {
  symbol: string;
  name?: string;
  price: number;
  currentPrice?: number;
  changePercent?: number;
  exchange?: string;
  rank?: number;
}

interface MyPortfolioProps {
  onAnalyzeTicker: (ticker: string, customCtx?: string) => void;
  onMarketStatusChange?: (isBullish: boolean) => void;
}

export function MyPortfolio({ onAnalyzeTicker, onMarketStatusChange }: MyPortfolioProps) {

  // Customization states
  const [timeframe, setTimeframe] = useState<'1D' | '7D' | '1M' | 'ALL'>('1M');
  const [taxMethod, setTaxMethod] = useState<'FIFO' | 'LIFO'>('FIFO');

  // Dialog state
  const [isAddOpen, setIsAddOpen] = useState(false);

  // Add-transaction form states
  const [txType, setTxType] = useState<'BUY' | 'SELL'>('BUY');
  const [txSymbol, setTxSymbol] = useState('');
  const [txQty, setTxQty] = useState('');
  const [txPrice, setTxPrice] = useState('');
  const [txFee, setTxFee] = useState('0');
  const [txDate, setTxDate] = useState(new Date().toISOString().split('T')[0]);
  const [txTotalSpent, setTxTotalSpent] = useState('');

  // Symbol combobox
  const [symbolSearchQuery, setSymbolSearchQuery] = useState('');
  const [showSymbolDropdown, setShowSymbolDropdown] = useState(false);
  const symbolDropdownRef = useRef<HTMLDivElement>(null);

  // Table controls
  const [filterText, setFilterText] = useState('');
  const [sortCol, setSortCol] = useState<'symbol' | 'value' | 'day' | 'total'>('value');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);
  const [watchlist, setWatchlist] = useState<Record<string, boolean>>({});

  // Tools state
  const [stressId, setStressId] = useState('market');
  const [severity, setSeverity] = useState(1);
  const [wiSymbol, setWiSymbol] = useState('BTC');
  const [wiSide, setWiSide] = useState<'Buy' | 'Sell'>('Buy');
  const [wiQty, setWiQty] = useState('0.05');
  const [szEntry, setSzEntry] = useState('68000');
  const [szStop, setSzStop] = useState('64000');
  const [szTarget, setSzTarget] = useState('78000');
  const [szRisk, setSzRisk] = useState(1);
  const [mcYears, setMcYears] = useState(5);
  const [mcMonthly, setMcMonthly] = useState('500');

  // Alerts (inline builder + persisted ledger)
  const [alertType, setAlertType] = useState<Alert['type']>('PRICE_ABOVE');
  const [alertTarget, setAlertTarget] = useState('');

  // Live data state
  const [liveAssets, setLiveAssets] = useState<LiveAsset[]>([]);
  const [loadingLive, setLoadingLive] = useState(true);
  const [loadingPortfolio, setLoadingPortfolio] = useState(true);

  // Persistent state
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [isUpdating, setIsUpdating] = useState(false);

  const fetchLivePrices = useCallback((isInitial = false) => {
    if (isInitial) setLoadingLive(true);
    setLiveAssets(DEMO_LIVE_PRICES);
    if (isInitial) setLoadingLive(false);
  }, []);

  useEffect(() => {
    if (loadingPortfolio) return;
    const isInitial = liveAssets.length === 0;
    fetchLivePrices(isInitial);
    const interval = setInterval(() => fetchLivePrices(false), 15000);
    return () => clearInterval(interval);
  }, [loadingPortfolio, fetchLivePrices, liveAssets.length]);

  const loadPortfolioData = (showSkeleton = true) => {
    if (showSkeleton) setLoadingPortfolio(true);
    const savedTx = localStorage.getItem('portfolio_tx_guest');
    const savedAlerts = localStorage.getItem('portfolio_alerts_guest');
    const savedWatchlist = localStorage.getItem('portfolio_watchlist_guest');
    if (savedTx) setTransactions(JSON.parse(savedTx));
    else setTransactions(DEFAULT_TRANSACTIONS);
    if (savedAlerts) setAlerts(JSON.parse(savedAlerts));
    if (savedWatchlist) setWatchlist(JSON.parse(savedWatchlist));
    if (showSkeleton) setLoadingPortfolio(false);
  };

  useEffect(() => { loadPortfolioData(); }, []);

  // Fractional transaction auto-calculations
  const handleQtyChange = (val: string) => {
    setTxQty(val);
    const qty = parseFloat(val) || 0;
    const price = parseFloat(txPrice) || 0;
    setTxTotalSpent(val ? (qty * price).toFixed(2) : '');
  };
  const handlePriceChange = (val: string) => {
    setTxPrice(val);
    const price = parseFloat(val) || 0;
    const qty = parseFloat(txQty) || 0;
    setTxTotalSpent(txQty ? (qty * price).toFixed(2) : '');
  };
  const handleSpentChange = (val: string) => {
    setTxTotalSpent(val);
    const spent = parseFloat(val) || 0;
    const price = parseFloat(txPrice) || 0;
    if (price > 0) setTxQty(val ? String(spent / price) : '');
  };

  const filteredSymbolOptions = useMemo(() => {
    if (!symbolSearchQuery) return DEMO_LIVE_PRICES;
    const q = symbolSearchQuery.toUpperCase();
    return DEMO_LIVE_PRICES.filter(a =>
      a.symbol.toUpperCase().includes(q) || a.name.toUpperCase().includes(q)
    );
  }, [symbolSearchQuery]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (symbolDropdownRef.current && !symbolDropdownRef.current.contains(event.target as Node)) {
        setShowSymbolDropdown(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const persistTx = (next: Transaction[]) => {
    setTransactions(next);
    localStorage.setItem('portfolio_tx_guest', JSON.stringify(next));
  };

  const handleAddTransaction = () => {
    if (!txSymbol) return;
    setIsUpdating(true);
    const newTx: Transaction = {
      id: 'tx-' + Date.now(),
      type: txType,
      symbol: txSymbol.toUpperCase(),
      quantity: parseFloat(txQty) || 0,
      price: parseFloat(txPrice) || 0,
      fee: parseFloat(txFee) || 0,
      date: txDate,
    };
    persistTx([...transactions, newTx]);
    setTxSymbol('');
    setSymbolSearchQuery('');
    setTxQty('');
    setTxPrice('');
    setTxFee('0');
    setIsAddOpen(false);
    setIsUpdating(false);
  };

  const handleDeleteTransaction = (symbol: string) => {
    persistTx(transactions.filter(t => t.symbol !== symbol));
  };

  const toggleStar = (symbol: string) => {
    const next = { ...watchlist, [symbol]: !watchlist[symbol] };
    setWatchlist(next);
    localStorage.setItem('portfolio_watchlist_guest', JSON.stringify(next));
  };

  const handleAddAlert = () => {
    const v = parseFloat(alertTarget);
    if (!isFinite(v)) return;
    const newAlert: Alert = {
      id: 'alert-' + Date.now(),
      symbol: wiSymbol.toUpperCase(),
      type: alertType,
      target: v,
      isActive: true,
    };
    const next = [...alerts, newAlert];
    setAlerts(next);
    localStorage.setItem('portfolio_alerts_guest', JSON.stringify(next));
    setAlertTarget('');
  };

  const handleDeleteAlert = (id: string) => {
    const next = alerts.filter(a => a.id !== id);
    setAlerts(next);
    localStorage.setItem('portfolio_alerts_guest', JSON.stringify(next));
  };

  const stats: PortfolioStats = usePortfolioEngine(transactions, liveAssets, taxMethod);

  useEffect(() => {
    if (!loadingLive && !loadingPortfolio && onMarketStatusChange) {
      onMarketStatusChange(stats.dailyChangeValue >= 0);
    }
  }, [stats.dailyChangeValue, loadingLive, loadingPortfolio, onMarketStatusChange]);

  const priceOf = useCallback((sym: string) =>
    DEMO_LIVE_PRICES.find(a => a.symbol === sym)?.price ?? 0, []);
  const dayOf = useCallback((sym: string) =>
    DEMO_LIVE_PRICES.find(a => a.symbol === sym)?.changePercent ?? 0, []);
  const metaOf = useCallback((sym: string) =>
    DEMO_LIVE_PRICES.find(a => a.symbol === sym), []);

  const totalCost = stats.costBasis || 1;
  const weightOf = useCallback((h: PortfolioStats['holdings'][number]) =>
    stats.totalValue > 0 ? h.value / stats.totalValue : 0, [stats.totalValue]);

  const wsum = useCallback((fn: (r: typeof RISK[string]) => number) =>
    stats.holdings.reduce((acc, h) => acc + fn(RISK[h.symbol] ?? RISK.BTC) * weightOf(h), 0),
    [stats.holdings, weightOf]);

  const pBeta = wsum(r => r.beta);
  const pVol = wsum(r => r.vol);
  const pSharpe = wsum(r => r.sharpe);
  const pMdd = wsum(r => r.mdd);

  // Theme tokens resolved once per render for ECharts.
  const theme = useMemo(() => ({
    primary: cssVar('--primary', '#7aff78'),
    foreground: cssVar('--foreground', '#f4f4f5'),
    muted: cssVar('--muted-foreground', '#9ca3af'),
    border: 'rgba(255,255,255,0.08)',
    tooltipBg: cssVar('--popover', '#141414'),
    tooltipBorder: 'rgba(255,255,255,0.12)',
    fontMono: 'JetBrains Mono, IBM Plex Mono, SF Mono, Consolas, monospace',
  }), []);

  // ── Performance history (per timeframe) ───────────────────────────────────
  const performanceSeries = useMemo(() => {
    const points = timeframe === '1D' ? 24 : timeframe === '7D' ? 7 * 4 : timeframe === '1M' ? 30 : 90;
    const noise = seeded(timeframe.length * 7919 + Math.round(stats.unrealizedPnL), points);
    let base = stats.totalValue - stats.unrealizedPnL;
    const step = stats.unrealizedPnL / points;
    const portData: number[] = [];
    for (let i = 0; i < points; i++) {
      base += step + (noise[i] - 0.5) * (base * 0.014);
      portData.push(Math.max(base, 1));
    }
    portData[points - 1] = stats.totalValue;

    const benchData = portData.map(v => {
      const start = portData[0];
      return start + ((v / start) - 1) * start * 0.55;
    });

    const labels: string[] = [];
    const now = new Date();
    for (let i = points - 1; i >= 0; i--) {
      const d = new Date(now);
      if (timeframe === '1D') d.setHours(d.getHours() - i);
      else d.setDate(d.getDate() - i);
      labels.push(
        timeframe === '1D'
          ? d.toLocaleTimeString('en-US', { hour: 'numeric' })
          : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
      );
    }

    return { labels, portData, benchData };
  }, [timeframe, stats.totalValue, stats.unrealizedPnL]);

  const perfDelta = useMemo(() => {
    const p = performanceSeries.portData;
    const b = performanceSeries.benchData;
    return {
      port: ((p[p.length - 1] / p[0]) - 1) * 100,
      bench: ((b[b.length - 1] / b[0]) - 1) * 100,
    };
  }, [performanceSeries]);

  const perfOption: EChartsOption = useMemo(() => ({
    animationDuration: 600,
    grid: { left: 8, right: 8, top: 24, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.foreground, fontFamily: theme.fontMono, fontSize: 11 },
      valueFormatter: (v) => fmtUsd(Number(v)),
      axisPointer: { lineStyle: { color: 'rgba(255,255,255,0.2)' } },
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: performanceSeries.labels,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: theme.muted, fontSize: 10, fontFamily: theme.fontMono },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: theme.border } },
      axisLabel: {
        color: theme.muted, fontSize: 10, fontFamily: theme.fontMono,
        formatter: (v: number) => fmtK(v),
      },
    },
    series: [
      {
        name: 'NAV',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: performanceSeries.portData,
        lineStyle: { width: 2, color: theme.primary },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(122,255,120,0.30)' },
            { offset: 1, color: 'rgba(122,255,120,0)' },
          ]),
        },
      },
      {
        name: 'Benchmark',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: performanceSeries.benchData,
        lineStyle: { width: 1.4, type: [4, 4], color: theme.muted },
        itemStyle: { color: theme.muted },
      },
    ],
  }), [performanceSeries, theme]);

  const CHART_COLORS = useMemo(() => ['#7aff78', 'oklch(0.70 0.15 280)', 'oklch(0.65 0.18 340)', 'oklch(0.80 0.14 70)', 'oklch(0.60 0.12 220)', 'oklch(0.75 0.15 130)', 'oklch(0.50 0.10 180)'], []);

// ── Allocation donut ──────────────────────────────────────────────────────

  const allocationOption: EChartsOption = useMemo(() => ({
    animationDuration: 600,
    tooltip: {
      trigger: 'item',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.foreground, fontFamily: theme.fontMono, fontSize: 11 },
      formatter: (p: unknown) => {
        const d = p as { name: string; value: number; percent: number };
        return `<b>${d.name}</b><br/>${fmtUsd(d.value)} · ${d.percent}%`;
      },
    },
    legend: { show: false },
    series: [{
      type: 'pie',
      radius: ['58%', '82%'],
      padAngle: 2,
      itemStyle: { borderRadius: 6, borderColor: 'transparent', borderWidth: 2 },
      label: { show: false },
      emphasis: { scaleSize: 4 },
      data: stats.holdings.map((h, i) => ({
        name: h.symbol,
        value: Number(h.value.toFixed(2)),
        itemStyle: { color: CHART_COLORS[i % CHART_COLORS.length] },
      })),
    }],
  }), [stats.holdings, theme, CHART_COLORS]);

  // ── Category exposure bars ────────────────────────────────────────────────
  const categoryRows = useMemo(() => {
    const map: Record<string, number> = {};
    stats.holdings.forEach(h => {
      const cat = metaOf(h.symbol)?.category ?? 'Other';
      map[cat] = (map[cat] ?? 0) + h.value;
    });
    const max = Math.max(...Object.values(map), 1);
    return Object.entries(map).sort((a, b) => b[1] - a[1]).map(([name, v]) => ({
      name,
      pct: (v / stats.totalValue) * 100,
      barPct: (v / max) * 100,
    }));
  }, [stats.holdings, stats.totalValue, metaOf]);

  // ── Rebalancing suggestions ───────────────────────────────────────────────
  const rebalanceRows = useMemo(() =>
    stats.holdings.map(h => {
      const cur = weightOf(h) * 100;
      const target = RISK[h.symbol]?.target ?? 10;
      const drift = cur - target;
      return {
        symbol: h.symbol,
        drift,
        curFmt: `${cur.toFixed(1)}%`,
        targetFmt: `${target}%`,
        driftFmt: `${drift >= 0 ? '+' : ''}${drift.toFixed(1)} pts`,
        action: Math.abs(drift) < 1.5 ? 'Hold'
          : drift > 0 ? `Trim ${fmtK((drift / 100) * stats.totalValue)}`
          : `Add ${fmtK((-drift / 100) * stats.totalValue)}`,
        color: Math.abs(drift) < 1.5 ? 'text-muted-foreground' : drift > 0 ? 'text-rose-400' : 'text-emerald-400',
      };
    }).sort((a, b) => Math.abs(b.drift) - Math.abs(a.drift)),
    [stats.holdings, stats.totalValue, weightOf]);

  // ── Holdings table rows ───────────────────────────────────────────────────
  const holdingsRows = useMemo(() => {
    const dir = sortDir === 'asc' ? 1 : -1;
    const key = { symbol: 'symbol', value: 'value', day: 'day', total: 'total' }[sortCol];
    return stats.holdings
      .map(h => ({ ...h, dayPct: dayOf(h.symbol), totalPct: (h.unrealizedPnL / (h.avgCost * h.quantity || 1)) * 100 }))
      .filter(h => h.symbol.toLowerCase().includes(filterText.toLowerCase()))
      .sort((a, b) => {
        const av = key === 'day' ? a.dayPct : key === 'total' ? a.totalPct : (a[key as 'symbol' | 'value'] as string | number);
        const bv = key === 'day' ? b.dayPct : key === 'total' ? b.totalPct : (b[key as 'symbol' | 'value'] as string | number);
        return (av > bv ? 1 : av < bv ? -1 : 0) * dir;
      });
  }, [stats.holdings, sortCol, sortDir, filterText, dayOf]);

  const arrowFor = (col: typeof sortCol) => sortCol === col ? (sortDir === 'asc' ? ' ↑' : ' ↓') : '';
  const toggleSort = (col: typeof sortCol) => () => {
    if (sortCol === col) setSortDir(d => (d === 'desc' ? 'asc' : 'desc'));
    else { setSortCol(col); setSortDir('desc'); }
  };

  // ── Recent transactions (running balance) ─────────────────────────────────
  const recentTransactions = useMemo(() => {
    let balance = stats.totalValue;
    return [...transactions]
      .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
      .slice(0, 8)
      .map(t => {
        balance += t.type === 'SELL' ? t.quantity * t.price : -(t.quantity * t.price);
        return {
          ...t,
          sideColor: t.type === 'BUY' ? 'text-emerald-400' : t.type === 'SELL' ? 'text-rose-400' : 'text-muted-foreground',
          balanceFmt: fmtUsd(balance),
        };
      });
  }, [transactions, stats.totalValue]);

  const watchlistRows = useMemo(() =>
    Object.entries(watchlist).filter(([, v]) => v).map(([sym]) => {
      const asset = metaOf(sym);
      return {
        symbol: sym,
        price: asset?.price ?? 0,
        dayPct: asset?.changePercent ?? 0,
      };
    }).filter(w => w.price > 0),
    [watchlist, metaOf]);

  // ── Stress test ───────────────────────────────────────────────────────────
  const stress = useMemo(() => {
    const scen = STRESS_SCENARIOS.find(s => s.id === stressId) ?? STRESS_SCENARIOS[0];
    const rows = stats.holdings.map(h => {
      const r = RISK[h.symbol] ?? RISK.BTC;
      const isMajor = ['BTC', 'ETH'].includes(h.symbol);
      const pct = (scen.mkt * (isMajor ? r.beta : r.beta) + scen.alt * (isMajor ? 0.4 : 1.1)) * severity;
      return { symbol: h.symbol, pct, dollar: h.value * (pct / 100) };
    }).sort((a, b) => a.pct - b.pct);

    const dollar = rows.reduce((a, r) => a + r.dollar, 0);
    const worst = rows[0];
    return {
      scen, rows,
      dollar,
      worstSymbol: worst?.symbol ?? '—',
      worstPct: worst?.pct ?? 0,
    };
  }, [stressId, severity, stats.holdings]);

  const stressOption: EChartsOption = useMemo(() => ({
    animationDuration: 500,
    grid: { left: 8, right: 60, top: 6, bottom: 6, containLabel: true },
    tooltip: {
      trigger: 'item',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.foreground, fontFamily: theme.fontMono, fontSize: 11 },
      formatter: (p: unknown) => {
        const d = p as { name: string; value: number };
        return `<b>${d.name}</b><br/>${fmtPct(d.value)} · ${fmtUsd(stats.totalValue * (d.value / 100))}`;
      },
    },
    xAxis: {
      type: 'value',
      splitLine: { show: false },
      axisLabel: { show: false },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'category',
      data: stress.rows.map(r => r.symbol),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: theme.foreground, fontFamily: theme.fontMono, fontSize: 11, fontWeight: 600 },
    },
    series: [{
      type: 'bar',
      barWidth: 16,
      data: stress.rows.map(r => ({
        value: Number(r.pct.toFixed(2)),
        itemStyle: {
          color: new echarts.graphic.LinearGradient(1, 0, 0, 0, [
            { offset: 0, color: r.pct >= 0 ? 'rgba(52,211,153,0.85)' : 'rgba(251,113,133,0.9)' },
            { offset: 1, color: r.pct >= 0 ? 'rgba(52,211,153,0.25)' : 'rgba(251,113,133,0.3)' },
          ]),
          borderRadius: 4,
        },
        label: {
          show: true,
          position: 'right',
          formatter: (p: unknown) => fmtPct((p as { value: number }).value),
          color: r.pct >= 0 ? UP : DOWN,
          fontFamily: theme.fontMono,
          fontSize: 10.5,
        },
      })),
      markLine: {
        silent: true,
        symbol: 'none',
        data: [{ xAxis: 0 }],
        lineStyle: { color: 'rgba(255,255,255,0.25)', width: 1 },
        label: { show: false },
      },
    }],
  }), [stress, stats.totalValue, theme]);

  // ── Correlation heatmap ───────────────────────────────────────────────────
  const corrSymbols = useMemo(() => stats.holdings.map(h => h.symbol), [stats.holdings]);
  const corrData = useMemo(() => {
    const cells: Array<[number, number, number]> = [];
    corrSymbols.forEach((a, i) => corrSymbols.forEach((b, j) => {
      cells.push([j, i, a === b ? 1 : (CORR[a]?.[b] ?? 0.5)]);
    }));
    const pairs: number[] = [];
    corrSymbols.forEach((a, i) => corrSymbols.forEach((b, j) => { if (j > i) pairs.push(CORR[a]?.[b] ?? 0.5); }));
    const avg = pairs.length ? pairs.reduce((x, y) => x + y, 0) / pairs.length : 0;
    return { cells, avg };
  }, [corrSymbols]);

  const corrOption: EChartsOption = useMemo(() => ({
    tooltip: {
      position: 'top',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.foreground, fontFamily: theme.fontMono, fontSize: 11 },
      formatter: (p: unknown) => {
        const d = p as { data: [number, number, number] };
        return `<b>${corrSymbols[d.data[1]]} × ${corrSymbols[d.data[0]]}</b><br/>ρ = ${d.data[2].toFixed(2)}`;
      },
    },
    grid: { left: 44, right: 8, top: 8, bottom: 44 },
    xAxis: {
      type: 'category', data: corrSymbols,
      splitArea: { show: false },
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: theme.muted, fontSize: 10, fontFamily: theme.fontMono },
    },
    yAxis: {
      type: 'category', data: corrSymbols,
      splitArea: { show: false },
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: theme.muted, fontSize: 10, fontFamily: theme.fontMono },
    },
    visualMap: {
      show: false, min: 0, max: 1, calculable: false, orient: 'horizontal',
      inRange: { color: ['rgba(122,255,120,0.06)', 'rgba(122,255,120,0.55)'] },
    },
    series: [{
      type: 'heatmap',
      data: corrData.cells,
      label: {
        show: true,
        formatter: (p: unknown) => {
          const d = p as { data: [number, number, number]; dataIndex: number };
          const i = Math.floor(d.dataIndex / corrSymbols.length);
          const j = d.dataIndex % corrSymbols.length;
          return i === j ? '—' : d.data[2].toFixed(2);
        },
        color: theme.foreground,
        fontFamily: theme.fontMono,
        fontSize: 9,
      },
      itemStyle: { borderColor: 'rgba(255,255,255,0.04)', borderWidth: 2, borderRadius: 4 },
      emphasis: { itemStyle: { shadowBlur: 6, shadowColor: 'rgba(0,0,0,0.4)' } },
    }],
  }), [corrSymbols, corrData, theme]);

  // ── What-if trade ─────────────────────────────────────────────────────────
  const whatIf = useMemo(() => {
    const qty = Math.max(0, parseFloat(wiQty) || 0);
    const price = priceOf(wiSymbol);
    const holding = stats.holdings.find(h => h.symbol === wiSymbol);
    const heldQty = holding?.quantity ?? 0;
    const delta = wiSide === 'Buy' ? qty : -Math.min(qty, heldQty);
    const cost = delta * price;
    const newCash = AVAILABLE_CASH - cost;
    const newMap = new Map(stats.holdings.map(h => [h.symbol, h]));
    const ex = newMap.get(wiSymbol);
    const newVal = ((ex?.quantity ?? 0) + delta) * price;
    const projTotal = stats.totalValue + cost;
    const newWeight = projTotal > 0 ? (newVal / projTotal) * 100 : 0;
    const oldWeight = holding ? weightOf(holding) * 100 : 0;

    const projBeta = stats.holdings.reduce((a, h) => {
      const w = h.symbol === wiSymbol ? (newVal / (projTotal || 1)) : weightOf(h);
      return a + (RISK[h.symbol]?.beta ?? 1) * w;
    }, 0) + (!holding && delta > 0 ? (RISK[wiSymbol]?.beta ?? 1) * (newVal / (projTotal || 1)) : 0);

    return { qty, price, delta, cost, newCash, newWeight, oldWeight, newBeta: projBeta };
  }, [wiQty, wiSymbol, wiSide, stats.holdings, stats.totalValue, priceOf, weightOf]);

  // ── Position sizing ───────────────────────────────────────────────────────
  const sizing = useMemo(() => {
    const entry = parseFloat(szEntry) || 0;
    const stop = parseFloat(szStop) || 0;
    const target = parseFloat(szTarget) || 0;
    const perUnit = entry - stop;
    const riskDollar = stats.totalValue * (szRisk / 100);
    const units = perUnit > 0 ? riskDollar / perUnit : 0;
    const posValue = units * entry;
    const rr = perUnit > 0 ? (target - entry) / perUnit : 0;
    return { entry, stop, target, units, posValue, rr, riskDollar };
  }, [szEntry, szStop, szTarget, szRisk, stats.totalValue]);

  // ── Monte Carlo projection ────────────────────────────────────────────────
  const monteCarlo = useMemo(() => {
    const mu = 0.45;
    const sigma = pVol / 100 || 0.6;
    const years = mcYears;
    const monthly = Math.max(0, parseFloat(mcMonthly) || 0);
    const steps = Math.max(12, years * 12);
    const proj = (z: number, tYears: number) => {
      const g = Math.exp((mu - 0.5 * sigma * sigma) * tYears + z * sigma * Math.sqrt(tYears));
      const annual = tYears > 0 ? Math.pow(g, 1 / tYears) - 1 : mu;
      const contrib = monthly * 12 * (annual !== 0 ? ((Math.pow(1 + annual, tYears) - 1) / annual) : tYears);
      return stats.totalValue * g + contrib;
    };
    const months = Array.from({ length: steps + 1 }, (_, i) => i);
    const p05 = months.map(m => proj(-1.645, m / 12));
    const p50 = months.map(m => proj(0, m / 12));
    const p95 = months.map(m => proj(1.645, m / 12));
    const bandOuter = p95.map((v, i) => Math.max(0, v - p05[i]));
    const totalContrib = monthly * 12 * years;
    return {
      months, p05, p50, p95, bandOuter,
      end: { lo: p05[steps], mid: p50[steps], hi: p95[steps] },
      totalContrib,
    };
  }, [mcYears, mcMonthly, pVol, stats.totalValue]);

  const mcOption: EChartsOption = useMemo(() => ({
    animationDuration: 600,
    grid: { left: 8, right: 8, top: 16, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.foreground, fontFamily: theme.fontMono, fontSize: 11 },
      valueFormatter: (v) => fmtK(Number(v)),
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: monteCarlo.months.map(m => (m % 12 === 0 ? `Y${m / 12}` : '')),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: theme.muted, fontSize: 10, fontFamily: theme.fontMono, interval: 11 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: theme.border } },
      axisLabel: { color: theme.muted, fontSize: 10, fontFamily: theme.fontMono, formatter: (v: number) => fmtK(v) },
    },
    series: [
      {
        name: 'Floor (5th pct)',
        type: 'line', stack: 'band-outer', data: monteCarlo.p05, symbol: 'none',
        lineStyle: { opacity: 0 }, areaStyle: { opacity: 0 }, silent: true, tooltip: { show: false },
      },
      {
        name: 'Optimistic band',
        type: 'line', stack: 'band-outer', data: monteCarlo.bandOuter, symbol: 'none',
        lineStyle: { opacity: 0 },
        areaStyle: { color: 'rgba(122,255,120,0.10)' }, silent: true, tooltip: { show: false },
      },
      {
        name: 'Median path',
        type: 'line', data: monteCarlo.p50, symbol: 'none', smooth: true,
        lineStyle: { width: 2, color: theme.primary },
      },
      {
        name: 'Pessimistic (5%)',
        type: 'line', data: monteCarlo.p05, symbol: 'none', smooth: true,
        lineStyle: { width: 1, type: [3, 3], color: 'rgba(251,113,133,0.6)' },
      },
      {
        name: 'Optimistic (95%)',
        type: 'line', data: monteCarlo.p95, symbol: 'none', smooth: true,
        lineStyle: { width: 1, type: [3, 3], color: 'rgba(122,255,120,0.6)' },
      },
    ],
  }), [monteCarlo, theme]);

  // ── Return attribution diverging bars ─────────────────────────────────────
  const attributionRows = useMemo(() =>
    stats.holdings
      .map(h => ({
        symbol: h.symbol,
        pts: (h.unrealizedPnL / totalCost) * 100,
        dollar: h.unrealizedPnL,
      }))
      .sort((a, b) => b.pts - a.pts),
    [stats.holdings, totalCost]);

  const attributionOption: EChartsOption = useMemo(() => ({
    animationDuration: 500,
    grid: { left: 8, right: 56, top: 6, bottom: 6, containLabel: true },
    tooltip: {
      trigger: 'item',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.foreground, fontFamily: theme.fontMono, fontSize: 11 },
      formatter: (p: unknown) => {
        const d = p as { name: string; value: number; dataIndex: number };
        const row = attributionRows[d.dataIndex];
        return `<b>${d.name}</b><br/>${row.dollar >= 0 ? '+' : ''}${fmtUsd(row.dollar)} contribution`;
      },
    },
    xAxis: { type: 'value', splitLine: { show: false }, axisLabel: { show: false }, axisLine: { show: false }, axisTick: { show: false } },
    yAxis: {
      type: 'category',
      data: attributionRows.map(r => r.symbol),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: theme.foreground, fontFamily: theme.fontMono, fontSize: 11, fontWeight: 600 },
    },
    series: [{
      type: 'bar',
      barWidth: 12,
      data: attributionRows.map(r => ({
        value: Number(r.pts.toFixed(2)),
        itemStyle: {
          color: new echarts.graphic.LinearGradient(1, 0, 0, 0, [
            { offset: 0, color: r.pts >= 0 ? 'rgba(52,211,153,0.9)' : 'rgba(251,113,133,0.9)' },
            { offset: 1, color: r.pts >= 0 ? 'rgba(52,211,153,0.3)' : 'rgba(251,113,133,0.3)' },
          ]),
          borderRadius: 3,
        },
        label: {
          show: true, position: 'right',
          formatter: (p: unknown) => `${(p as { value: number }).value >= 0 ? '+' : ''}${(p as { value: number }).value.toFixed(1)} pts`,
          color: r.pts >= 0 ? UP : DOWN,
          fontFamily: theme.fontMono, fontSize: 10,
        },
      })),
      markLine: {
        silent: true, symbol: 'none', data: [{ xAxis: 0 }],
        lineStyle: { color: 'rgba(255,255,255,0.25)', width: 1 }, label: { show: false },
      },
    }],
  }), [attributionRows, theme]);

  // ── Cost basis comparison chart ───────────────────────────────────────────
  const costBasisOption: EChartsOption = useMemo(() => ({
    animationDuration: 500,
    grid: { left: 8, right: 8, top: 20, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.foreground, fontFamily: theme.fontMono, fontSize: 11 },
      valueFormatter: (v) => fmtUsd(Number(v), 2),
    },
    legend: {
      top: 0, right: 0, icon: 'roundRect', itemWidth: 10, itemHeight: 10,
      textStyle: { color: theme.muted, fontSize: 10, fontFamily: theme.fontMono },
    },
    xAxis: {
      type: 'category',
      data: stats.holdings.map(h => h.symbol),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: theme.foreground, fontFamily: theme.fontMono, fontWeight: 600, fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: theme.border } },
      axisLabel: { color: theme.muted, fontSize: 10, fontFamily: theme.fontMono, formatter: (v: number) => fmtK(v) },
    },
    series: [
      {
        name: 'Avg cost',
        type: 'bar', barWidth: 14, barGap: '20%',
        itemStyle: { color: 'rgba(251,191,36,0.65)', borderRadius: [4, 4, 0, 0] },
        data: stats.holdings.map(h => Number(h.avgCost.toFixed(2))),
      },
      {
        name: 'Live price',
        type: 'bar', barWidth: 14,
        itemStyle: { color: 'rgba(122,255,120,0.75)', borderRadius: [4, 4, 0, 0] },
        data: stats.holdings.map(h => Number(h.currentPrice.toFixed(2))),
      },
    ],
  }), [stats.holdings, theme]);

  // Risk headline label
  const divScore = useMemo(() => {
    const n = Math.max(stats.holdings.length, 1);
    if (stats.holdings.length === 0) return 0;
    const hhi = stats.holdings.reduce((a, h) => a + weightOf(h) * weightOf(h), 0);
    return Math.round((1 - (hhi - 1 / n) / (1 - 1 / n)) * 100);
  }, [stats.holdings, weightOf]);

  const bestMover = useMemo(() =>
    holdingsRows.length ? [...holdingsRows].sort((a, b) => b.dayPct - a.dayPct)[0] : null,
    [holdingsRows]);

  const riskLabel = useMemo(() => {
    if (stats.holdings.length === 0) return 'No risk data yet.';
    const maxAlloc = stats.holdings[0]?.allocation ?? 0;
    if (maxAlloc > 60) return 'High concentration — single-asset dominance.';
    if (maxAlloc > 40) return 'Moderate concentration — balanced exposure.';
    return 'Well diversified across the complex.';
  }, [stats.holdings]);

  const aiInsights = useMemo(() =>
    stats.holdings.filter(h => metaOf(h.symbol)?.aiTag).slice(0, 4)
      .map(h => ({ ticker: h.symbol, text: metaOf(h.symbol)!.aiTag! })),
    [stats.holdings, metaOf]);

  if (loadingLive || loadingPortfolio) {
    return (
      <>
        <TopLoader />
        <div className="space-y-6 p-6 md:p-10">
          <SkeletonHeader />
          <SkeletonCardGrid count={4} />
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <SkeletonPanel className="lg:col-span-2 h-96" />
            <SkeletonPanel className="h-96" />
          </div>
          <SkeletonTable rows={3} />
        </div>
      </>
    );
  }

  return (
    <div className="space-y-8 p-6 md:p-10 font-sans bg-transparent min-h-screen text-foreground animate-in fade-in duration-500 relative overflow-x-hidden">

      {/* ─── HEADER ─────────────────────────────────────────────────────────── */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 border-b border-border/40 pb-6">
        <div>
          <h1 className="text-3xl md:text-4xl font-serif font-semibold tracking-tight flex items-center gap-3 flex-wrap">
            <Briefcase className="h-9 w-9 text-primary" />
            My Portfolio
            <span className="bg-card/85 text-[10px] uppercase font-mono tracking-wider px-3 py-1 rounded-full text-primary border border-primary/20 flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-primary animate-ping"></span>
              Live Synced
            </span>
          </h1>
          <p className="text-muted-foreground text-sm mt-2">
            Holdings, performance, and AI-driven insights in real time.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center bg-card/40 border border-border/40 rounded-xl p-1">
            {(['FIFO', 'LIFO'] as const).map(m => (
              <button
                key={m}
                onClick={() => setTaxMethod(m)}
                className={`px-3 py-1.5 text-xs font-mono rounded-lg transition-all cursor-pointer ${
                  taxMethod === m ? 'bg-accent text-foreground font-semibold' : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {m}
              </button>
            ))}
          </div>
          <Button
            className="bg-primary hover:bg-primary/90 text-primary-foreground font-semibold rounded-xl px-5 py-5 text-sm transition-all shadow-lg shadow-primary/15 flex items-center gap-2 cursor-pointer"
            onClick={() => { setTxType('BUY'); setIsAddOpen(true); }}
          >
            <Plus className="w-4 h-4" />
            Add Transaction
          </Button>
        </div>
      </div>

      {/* ─── KPI BOARD ──────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div className={`${PANEL} p-6 relative overflow-hidden group hover:border-primary/45 transition-all`}>
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-mono tracking-wider uppercase text-muted-foreground flex items-center gap-2">
              <Wallet className="w-4 h-4 text-primary" /> Net Asset Value
            </span>
            <span className="text-xs font-mono text-muted-foreground">USD</span>
          </div>
          <span className="text-3xl font-mono font-bold tracking-tight block">{fmtUsd(stats.totalValue)}</span>
          <div className={`flex items-center gap-1.5 text-xs font-semibold mt-1 ${stats.dailyChangeValue >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {stats.dailyChangeValue >= 0 ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
            {fmtUsd(stats.dailyChangeValue)} ({fmtPct(stats.dailyChangePercent)}) today
          </div>
        </div>

        <div className={`${PANEL} p-6 group hover:border-primary/45 transition-all`}>
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-mono tracking-wider uppercase text-muted-foreground flex items-center gap-2">
              <Activity className="w-4 h-4 text-primary" /> Today&apos;s P/L
            </span>
          </div>
          <span className={`text-3xl font-mono font-bold tracking-tight block ${stats.dailyChangeValue >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {fmtUsd(stats.dailyChangeValue)}
          </span>
          <span className="text-xs text-muted-foreground mt-1 block">Mark-to-market, 24h window</span>
        </div>

        <div className={`${PANEL} p-6 group hover:border-primary/45 transition-all`}>
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-mono tracking-wider uppercase text-muted-foreground flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-primary" /> Unrealized P/L
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded bg-muted/50 border border-border/30 text-muted-foreground">All time</span>
          </div>
          <span className={`text-3xl font-mono font-bold tracking-tight block ${stats.unrealizedPnL >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {stats.unrealizedPnL >= 0 ? '+' : '-'}{fmtUsd(Math.abs(stats.unrealizedPnL))}
          </span>
          <div className="text-xs mt-1 flex items-center gap-1">
            <span className="text-muted-foreground">ROI</span>
            <span className={`font-semibold ${stats.roiPercent >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{fmtPct(stats.roiPercent)}</span>
          </div>
        </div>

        <div className={`${PANEL} p-6 group hover:border-primary/45 transition-all`}>
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-mono tracking-wider uppercase text-muted-foreground flex items-center gap-2">
              <DollarSign className="w-4 h-4 text-primary" /> Available Cash
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded bg-muted/50 border border-border/30 text-muted-foreground">Deployable</span>
          </div>
          <span className="text-3xl font-mono font-bold tracking-tight block">{fmtUsd(AVAILABLE_CASH)}</span>
          <span className="text-xs text-muted-foreground mt-1 block">Realized P/L {stats.realizedPnL >= 0 ? '+' : '-'}{fmtUsd(Math.abs(stats.realizedPnL))} · {taxMethod}</span>
        </div>
      </div>

      {/* ─── PERFORMANCE + ALLOCATION + AI INSIGHTS ─────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5 items-stretch">
        <div className={`${PANEL} lg:col-span-3 flex flex-col`}>
          <div className="p-5 border-b border-border/30 flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-3 flex-wrap">
              <h3 className="text-md font-serif font-semibold">Performance</h3>
              <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                <svg width="16" height="6"><line x1="0" y1="3" x2="16" y2="3" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3 3" /></svg>
                vs benchmark
                <span className={`font-mono font-semibold ${perfDelta.port >= perfDelta.bench ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {fmtPct(perfDelta.port - perfDelta.bench)}
                </span>
              </span>
            </div>
            <div className="flex bg-muted/20 border border-border/30 rounded-lg p-0.5">
              {(['1D', '7D', '1M', 'ALL'] as const).map(tf => (
                <button
                  key={tf}
                  onClick={() => setTimeframe(tf)}
                  className={`px-3 py-1 text-[10px] font-mono rounded-md transition-all cursor-pointer ${
                    timeframe === tf ? 'bg-accent text-foreground font-semibold' : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {tf}
                </button>
              ))}
            </div>
          </div>
          <div className="p-4 flex-1 min-h-[300px]">
            <EChart option={perfOption} height={320} />
          </div>
        </div>

        <div className="lg:col-span-2 flex flex-col gap-5">
          <div className={`${PANEL} p-5`}>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-md font-serif font-semibold flex items-center gap-2">
                <PieChart className="w-4 h-4 text-primary" /> Allocation
              </h3>
              <span className="text-[11px] font-mono text-muted-foreground">
                Top: <span className="text-primary font-semibold">{stats.holdings[0]?.symbol ?? '—'} {(stats.holdings[0]?.allocation ?? 0).toFixed(0)}%</span>
              </span>
            </div>
            {stats.holdings.length > 0 ? (
              <>
                <EChart option={allocationOption} height={170} />
                <div className="mt-3 space-y-1.5 max-h-[104px] overflow-y-auto pr-1">
                  {stats.holdings.slice(0, 6).map((h, i) => (
                    <div key={h.symbol} className="flex items-center gap-2 text-xs font-mono">
                      <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: CHART_COLORS[i % CHART_COLORS.length] }}></span>
                      <span className="font-semibold flex-1 truncate">{h.symbol}</span>
                      <span className="text-muted-foreground">{h.allocation.toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="text-xs text-muted-foreground font-mono text-center py-10">No active balances to chart.</p>
            )}
          </div>

          <div className="rounded-2xl p-5 flex-1 bg-primary/[0.06] border border-primary/20">
            <div className="flex items-center gap-2 mb-3">
              <Sparkles className="w-4 h-4 text-primary" />
              <h3 className="text-md font-serif font-semibold text-primary">AI Insights</h3>
            </div>
            <div className="space-y-2.5">
              {aiInsights.length > 0 ? aiInsights.map(ins => (
                <p key={ins.ticker} className="text-[12.5px] leading-relaxed text-foreground/80">
                  <span className="font-mono font-bold text-primary">{ins.ticker}</span> — {ins.text}
                </p>
              )) : (
                <p className="text-xs text-muted-foreground">No active insights — add holdings to generate signals.</p>
              )}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onAnalyzeTicker('PORTFOLIO')}
              className="mt-4 w-full border-primary/40 text-primary hover:bg-primary/10 font-mono text-xs cursor-pointer"
            >
              <Sparkles className="w-3.5 h-3.5 mr-1" />
              Discuss Portfolio With AI
            </Button>
          </div>
        </div>
      </div>

      {/* ─── RISK METRICS + CATEGORY EXPOSURE ───────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
        <div className={`${PANEL} lg:col-span-3 p-5`}>
          <h3 className="text-md font-serif font-semibold mb-4 flex items-center gap-2">
            <Shield className="w-4 h-4 text-primary" /> Risk &amp; Return Metrics
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {[
              { label: 'Beta vs BTC', value: pBeta.toFixed(2), note: pBeta > 1.2 ? 'High market sensitivity' : 'Market-like sensitivity' },
              { label: 'Volatility (ann.)', value: `${pVol.toFixed(1)}%`, note: pVol > 60 ? 'Above benchmark' : 'Moderate' },
              { label: 'Sharpe Ratio', value: pSharpe.toFixed(2), note: pSharpe > 1 ? 'Good risk-adj. return' : 'Weak risk-adjusted' },
              { label: 'Max Drawdown', value: `${pMdd.toFixed(1)}%`, note: 'Weighted historical' },
              {
                label: 'Diversification',
                value: `${divScore}/100`,
                note: `Top position ${(stats.holdings[0]?.allocation ?? 0).toFixed(0)}%`,
              },
              { label: 'Best 24h Mover', value: bestMover ? bestMover.symbol : '—', note: bestMover ? fmtPct(bestMover.dayPct) : 'No data', highlight: true },
            ].map(m => (
              <div key={m.label} className={`${TILE} p-3.5`}>
                <div className="text-[10.5px] text-muted-foreground mb-1.5">{m.label}</div>
                <div className={`font-mono text-lg font-bold ${m.highlight ? 'text-primary' : ''}`}>{m.value}</div>
                <div className="text-[10px] text-muted-foreground/70 mt-0.5">{m.note}</div>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-muted-foreground mt-4">{riskLabel}</p>
        </div>

        <div className={`${PANEL} lg:col-span-2 p-5`}>
          <h3 className="text-md font-serif font-semibold mb-4 flex items-center gap-2">
            <BarChart2 className="w-4 h-4 text-primary" /> Category Exposure
          </h3>
          <div className="space-y-3">
            {categoryRows.map(row => (
              <div key={row.name}>
                <div className="flex justify-between text-xs mb-1.5">
                  <span className="text-foreground/90">{row.name}</span>
                  <span className="font-mono text-muted-foreground">{row.pct.toFixed(1)}%</span>
                </div>
                <div className="h-1.5 bg-border/20 rounded-full overflow-hidden">
                  <div className="h-full rounded-full transition-all duration-500" style={{ width: `${row.barPct}%`, background: 'linear-gradient(90deg,#047857,#7aff78)' }}></div>
                </div>
              </div>
            ))}
            {categoryRows.length === 0 && <p className="text-xs text-muted-foreground font-mono text-center py-6">No exposure data.</p>}
          </div>
        </div>
      </div>

      {/* ─── REBALANCING SUGGESTIONS ────────────────────────────────────────── */}
      <div className={`${PANEL} p-5`}>
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <h3 className="text-md font-serif font-semibold flex items-center gap-2">
            <Flame className="w-4 h-4 text-primary" /> Rebalancing Suggestions
          </h3>
          <span className="text-[11px] text-muted-foreground">Drift vs. model target allocation</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
          {rebalanceRows.map(rb => (
            <div key={rb.symbol} className={`${TILE} p-3.5 min-w-0`}>
              <div className="flex items-baseline justify-between gap-2 mb-2.5">
                <span className="font-mono text-sm font-bold">{rb.symbol}</span>
                <span className={`text-[11px] font-bold ${rb.color} text-right`}>{rb.action}</span>
              </div>
              <div className="flex gap-3 flex-wrap text-[11px]">
                <div><div className="text-muted-foreground text-[10px]">Current</div><div className="font-mono">{rb.curFmt}</div></div>
                <div><div className="text-muted-foreground text-[10px]">Target</div><div className="font-mono">{rb.targetFmt}</div></div>
                <div><div className="text-muted-foreground text-[10px]">Drift</div><div className={`font-mono ${rb.color}`}>{rb.driftFmt}</div></div>
              </div>
            </div>
          ))}
          {rebalanceRows.length === 0 && <p className="text-xs text-muted-foreground col-span-full text-center py-4">No holdings to rebalance.</p>}
        </div>
      </div>

      {/* ─── HOLDINGS TABLE ─────────────────────────────────────────────────── */}
      <div className={`${PANEL} overflow-hidden`}>
        <div className="p-5 border-b border-border/30 flex items-center justify-between flex-wrap gap-3">
          <h3 className="text-md font-serif font-semibold flex items-center gap-2">
            <History className="w-5 h-5 text-primary" /> Active Holdings
          </h3>
          <input
            value={filterText}
            onChange={e => setFilterText(e.target.value)}
            placeholder="Filter by symbol…"
            className="bg-muted/20 border border-border/40 rounded-lg px-3 py-1.5 text-xs font-mono outline-none focus:border-primary/50 w-48"
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse min-w-[760px]">
            <thead>
              <tr className="border-b border-border/30 bg-muted/15 text-[10px] uppercase font-mono text-muted-foreground tracking-wider font-semibold">
                <th className="p-4 px-6 cursor-pointer select-none hover:text-foreground" onClick={toggleSort('symbol')}>Asset{arrowFor('symbol')}</th>
                <th className="p-4">Quantity</th>
                <th className="p-4">Avg Cost</th>
                <th className="p-4">Price</th>
                <th className="p-4 cursor-pointer select-none hover:text-foreground" onClick={toggleSort('value')}>Value{arrowFor('value')}</th>
                <th className="p-4 cursor-pointer select-none hover:text-foreground" onClick={toggleSort('day')}>24h %{arrowFor('day')}</th>
                <th className="p-4 cursor-pointer select-none hover:text-foreground" onClick={toggleSort('total')}>Unrealized P/L{arrowFor('total')}</th>
                <th className="p-4"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/20 text-sm font-mono">
              {holdingsRows.length === 0 ? (
                <tr><td colSpan={8} className="p-10 text-center text-muted-foreground">
                  No holdings match. Click &quot;Add Transaction&quot; to record buys/sells.
                </td></tr>
              ) : holdingsRows.map(h => {
                const up = h.dayPct >= 0;
                const expanded = expandedSymbol === h.symbol;
                return (
                  <React.Fragment key={h.symbol}>
                    <tr
                      className={`hover:bg-muted/10 transition-colors group cursor-pointer ${expanded ? 'bg-muted/10' : ''}`}
                      onClick={() => setExpandedSymbol(expanded ? null : h.symbol)}
                    >
                      <td className="p-4 px-6">
                        <div className="flex items-center gap-3">
                          <button
                            onClick={(e) => { e.stopPropagation(); toggleStar(h.symbol); }}
                            title="Toggle watchlist star"
                            className="cursor-pointer shrink-0"
                          >
                            <Star className={`w-4 h-4 ${watchlist[h.symbol] ? 'fill-primary text-primary' : 'text-muted-foreground/40 hover:text-primary/70'}`} />
                          </button>
                          <div>
                            <div className="font-bold">{h.symbol}</div>
                            <div className="text-[10px] text-muted-foreground">{metaOf(h.symbol)?.name ?? 'Crypto Asset'} · {metaOf(h.symbol)?.category ?? 'Other'}</div>
                          </div>
                        </div>
                      </td>
                      <td className="p-4 text-foreground/90">{h.quantity.toLocaleString(undefined, { maximumFractionDigits: 6 })}</td>
                      <td className="p-4 text-foreground/90">${h.avgCost.toLocaleString(undefined, { maximumFractionDigits: 4 })}</td>
                      <td className="p-4 text-foreground/90">${h.currentPrice.toLocaleString(undefined, { maximumFractionDigits: 4 })}</td>
                      <td className="p-4 font-bold">{fmtUsd(h.value)}</td>
                      <td className={`p-4 font-semibold ${up ? 'text-emerald-400' : 'text-rose-400'}`}>{fmtPct(h.dayPct)}</td>
                      <td className="p-4">
                        <div className={`font-semibold ${h.unrealizedPnL >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {h.unrealizedPnL >= 0 ? '+' : '-'}{fmtUsd(Math.abs(h.unrealizedPnL))}
                        </div>
                        <div className={`text-[10px] font-bold ${h.unrealizedPnL >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                          {fmtPct(h.totalPct)}
                        </div>
                      </td>
                      <td className="p-4 text-right">
                        <div className="flex items-center justify-end gap-1.5 opacity-60 group-hover:opacity-100 transition-opacity">
                          <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-primary hover:bg-muted/40 cursor-pointer"
                            onClick={(e) => { e.stopPropagation(); onAnalyzeTicker(h.symbol); }}
                            title="Analyze with AI">
                            <BarChart2 className="h-3.5 w-3.5" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-rose-500 hover:bg-rose-500/10 cursor-pointer"
                            onClick={(e) => { e.stopPropagation(); handleDeleteTransaction(h.symbol); }}
                            title="Remove all transactions for this asset">
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                          <span className="text-muted-foreground w-4 inline-flex justify-center">
                            {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                          </span>
                        </div>
                      </td>
                    </tr>
                    {expanded && (
                      <tr className="bg-muted/[0.03]">
                        <td colSpan={8} className="p-4 px-6 border-b border-border/10">
                          <div className="flex items-center gap-5 flex-wrap">
                            <Sparkline up={up} />
                            <p className="flex-1 text-[12.5px] text-foreground/80 min-w-[220px] font-sans">
                              {metaOf(h.symbol)?.aiTag ?? 'No active AI insight for this position.'}
                            </p>
                            <Button
                              size="sm"
                              onClick={(e) => { e.stopPropagation(); onAnalyzeTicker(h.symbol); }}
                              className="bg-primary/15 text-primary hover:bg-primary/25 border border-primary/30 text-xs font-bold cursor-pointer"
                            >
                              <Sparkles className="w-3.5 h-3.5 mr-1" /> Discuss With AI
                            </Button>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* ─── WATCHLIST + TRANSACTIONS ───────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
        <div className={`${PANEL} lg:col-span-2 p-5`}>
          <h3 className="text-md font-serif font-semibold mb-3 flex items-center gap-2">
            <Star className="w-4 h-4 fill-primary text-primary" /> Watchlist
          </h3>
          <div className="divide-y divide-border/20">
            {watchlistRows.length > 0 ? watchlistRows.map(w => (
              <div key={w.symbol} className="flex items-center justify-between py-2.5 cursor-pointer hover:bg-muted/10 rounded-lg px-2 -mx-2 transition-colors"
                onClick={() => onAnalyzeTicker(w.symbol)}>
                <div className="flex items-center gap-2">
                  <Star className="w-3 h-3 fill-primary text-primary" />
                  <span className="font-mono font-bold text-sm">{w.symbol}</span>
                  <span className="text-[10px] text-muted-foreground hidden sm:inline">{metaOf(w.symbol)?.name}</span>
                </div>
                <div className="text-right">
                  <div className="font-mono text-sm">${w.price.toLocaleString(undefined, { maximumFractionDigits: 4 })}</div>
                  <div className={`font-mono text-[11px] ${w.dayPct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{fmtPct(w.dayPct)}</div>
                </div>
              </div>
            )) : (
              <p className="text-xs text-muted-foreground font-mono text-center py-8">
                Star holdings above to pin them here.
              </p>
            )}
          </div>
        </div>

        <div className={`${PANEL} lg:col-span-3 p-5`}>
          <h3 className="text-md font-serif font-semibold mb-3 flex items-center gap-2">
            <Calendar className="w-4 h-4 text-primary" /> Recent Transactions
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono min-w-[520px]">
              <thead>
                <tr className="border-b border-border/30 text-[10px] uppercase text-muted-foreground font-semibold">
                  <th className="py-2 pr-3">Date</th><th className="pr-3">Symbol</th><th className="pr-3">Side</th>
                  <th className="pr-3">Qty</th><th className="pr-3">Price</th><th className="pr-3">Fee</th><th>Balance</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/20">
                {recentTransactions.map(t => (
                  <tr key={t.id} className="hover:bg-muted/5">
                    <td className="py-2.5 pr-3 text-muted-foreground">{t.date}</td>
                    <td className="pr-3 font-bold">{t.symbol}</td>
                    <td className={`pr-3 font-bold ${t.sideColor}`}>{t.type}</td>
                    <td className="pr-3">{t.quantity.toLocaleString(undefined, { maximumFractionDigits: 6 })}</td>
                    <td className="pr-3">${t.price.toLocaleString(undefined, { maximumFractionDigits: 4 })}</td>
                    <td className="pr-3 text-muted-foreground">${t.fee.toFixed(2)}</td>
                    <td>{t.balanceFmt}</td>
                  </tr>
                ))}
                {recentTransactions.length === 0 && (
                  <tr><td colSpan={7} className="py-6 text-center text-muted-foreground">No transactions recorded.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* ─── ANALYTICS TOOLS DIVIDER ────────────────────────────────────────── */}
      <div className="flex items-center gap-4 pt-2">
        <h2 className="text-xl font-serif font-bold tracking-tight whitespace-nowrap">Analytics Tools</h2>
        <div className="h-px flex-1" style={{ background: 'linear-gradient(90deg, rgba(122,255,120,0.4), rgba(255,255,255,0.05))' }}></div>
      </div>

      {/* ─── STRESS TEST + CORRELATION MATRIX ───────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
        <div className={`${PANEL} lg:col-span-3 p-5`}>
          <div className="flex items-baseline justify-between flex-wrap gap-2">
            <h3 className="text-md font-serif font-semibold">Stress Test</h3>
            <span className="text-[11px] text-muted-foreground">Beta-adjusted shock model</span>
          </div>
          <p className="text-[11.5px] text-muted-foreground mt-1 mb-3">{stress.scen.desc}</p>

          <div className="flex gap-2 flex-wrap mb-4">
            {STRESS_SCENARIOS.map(sc => (
              <button
                key={sc.id}
                onClick={() => setStressId(sc.id)}
                className={`px-3 py-1.5 text-[11px] font-bold rounded-lg border transition-all cursor-pointer ${
                  stressId === sc.id
                    ? 'border-primary/40 bg-primary/10 text-primary'
                    : 'border-border/40 text-muted-foreground hover:text-foreground'
                }`}
              >
                {sc.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-3 mb-4">
            <span className="text-[11px] text-muted-foreground whitespace-nowrap">Severity</span>
            <input type="range" min="0.5" max="2" step="0.1" value={severity}
              onChange={e => setSeverity(parseFloat(e.target.value))}
              className="flex-1 accent-[#7aff78]" />
            <span className="font-mono text-xs text-primary w-9">{severity.toFixed(1)}×</span>
          </div>

          <div className="grid grid-cols-3 gap-3 mb-4">
            <div className={`${TILE} p-3`}>
              <div className="text-[10px] text-muted-foreground mb-1">Projected Value</div>
              <div className="font-mono font-bold">{fmtK(stats.totalValue + stress.dollar)}</div>
            </div>
            <div className={`${TILE} p-3`}>
              <div className="text-[10px] text-muted-foreground mb-1">Impact</div>
              <div className={`font-mono font-bold ${stress.dollar >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {fmtUsd(stress.dollar, 0)}
              </div>
            </div>
            <div className={`${TILE} p-3`}>
              <div className="text-[10px] text-muted-foreground mb-1">Worst Asset</div>
              <div className="font-mono font-bold text-rose-400">
                {stress.worstSymbol} {fmtPct(stress.worstPct)}
              </div>
            </div>
          </div>

          <EChart option={stressOption} height={Math.max(140, stress.rows.length * 38 + 20)} />
        </div>

        <div className={`${PANEL} lg:col-span-2 p-5`}>
          <div className="flex items-baseline justify-between mb-3 flex-wrap gap-2">
            <h3 className="text-md font-serif font-semibold">Correlation Matrix</h3>
            <span className="text-[11px] text-muted-foreground">Rolling 90-day returns</span>
          </div>
          {corrSymbols.length > 1 ? (
            <>
              <EChart option={corrOption} height={Math.max(180, corrSymbols.length * 34 + 60)} />
              <p className="mt-3 pt-3 border-t border-border/20 text-[11.5px] text-muted-foreground leading-relaxed">
                Avg pairwise correlation{' '}
                <span className="font-mono font-bold text-foreground">{corrData.avg.toFixed(2)}</span>.
                {corrData.avg > 0.75
                  ? ' Holdings move largely together — diversification benefit is limited.'
                  : ' Reasonable spread of independent risk across the book.'}
              </p>
            </>
          ) : (
            <p className="text-xs text-muted-foreground font-mono text-center py-10">Add at least two assets to compute correlations.</p>
          )}
        </div>
      </div>

      {/* ─── WHAT-IF + POSITION SIZING + ALERTS ─────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* What-If Trade */}
        <div className={`${PANEL} p-5`}>
          <h3 className="text-md font-serif font-semibold mb-4">What-If Trade</h3>

          <select
            value={wiSymbol}
            onChange={e => setWiSymbol(e.target.value)}
            className="w-full bg-muted/20 border border-border/40 rounded-lg px-3 py-2 text-xs font-mono outline-none focus:border-primary/50 mb-2 cursor-pointer [&>option]:bg-[#111]"
          >
            {DEMO_LIVE_PRICES.map(a => <option key={a.symbol} value={a.symbol}>{a.symbol} — {a.name}</option>)}
          </select>

          <div className="flex gap-2 mb-3">
            {(['Buy', 'Sell'] as const).map(side => (
              <button
                key={side}
                onClick={() => setWiSide(side)}
                className={`flex-1 py-1.5 text-xs font-bold rounded-lg border transition-all cursor-pointer ${
                  wiSide === side
                    ? side === 'Buy' ? 'border-emerald-400/40 bg-emerald-400/10 text-emerald-400' : 'border-rose-400/40 bg-rose-400/10 text-rose-400'
                    : 'border-border/40 text-muted-foreground hover:text-foreground'
                }`}
              >
                {side}
              </button>
            ))}
          </div>

          <label className="text-[10px] uppercase font-mono text-muted-foreground block mb-1">Units</label>
          <input value={wiQty} onChange={e => setWiQty(e.target.value)}
            className="w-full bg-muted/20 border border-border/40 rounded-lg px-3 py-2 text-xs font-mono outline-none focus:border-primary/50 mb-4" />

          <div className="space-y-2.5">
            {[
              { l: `${wiSymbol} weight`, before: `${whatIf.oldWeight.toFixed(1)}%`, after: `${whatIf.newWeight.toFixed(1)}%`, ok: null as boolean | null },
              { l: 'Portfolio value', before: fmtK(stats.totalValue), after: fmtK(stats.totalValue + whatIf.cost), ok: whatIf.cost >= 0 },
              { l: 'Est. cash after', before: fmtUsd(AVAILABLE_CASH, 0), after: fmtUsd(whatIf.newCash, 0), ok: whatIf.newCash >= 0 },
            ].map(row => (
              <div key={row.l} className="flex items-baseline justify-between text-[11.5px] pb-2 border-b border-border/20">
                <span className="text-muted-foreground">{row.l}</span>
                <span className="flex items-baseline gap-2 font-mono">
                  <span className="text-muted-foreground/70">{row.before}</span>
                  <span className="text-muted-foreground/40">→</span>
                  <span className={`font-bold ${row.ok === null ? '' : row.ok ? 'text-emerald-400' : 'text-rose-400'}`}>{row.after}</span>
                </span>
              </div>
            ))}
          </div>

          <p className="mt-3 text-[11px] text-muted-foreground leading-relaxed">
            {whatIf.newCash < 0
              ? `Insufficient cash — needs ${fmtUsd(-whatIf.newCash, 0)} more than available.`
              : whatIf.newWeight > 40
                ? `${wiSymbol} would exceed 40% of the portfolio — concentration risk rises sharply.`
                : whatIf.delta === 0
                  ? 'No quantity held to sell at this size.'
                  : `Trade costs ${fmtUsd(Math.abs(whatIf.cost), 0)} and shifts ${wiSymbol} to ${whatIf.newWeight.toFixed(1)}% of NAV.`}
          </p>
        </div>

        {/* Position Sizing */}
        <div className={`${PANEL} p-5`}>
          <h3 className="text-md font-serif font-semibold mb-4">Position Sizing</h3>
          <div className="space-y-3 mb-4">
            {[
              { l: 'Entry', v: szEntry, set: setSzEntry },
              { l: 'Stop loss', v: szStop, set: setSzStop },
              { l: 'Target', v: szTarget, set: setSzTarget },
            ].map(f => (
              <div key={f.l} className="flex items-center gap-3">
                <span className="text-[11px] text-muted-foreground w-16 shrink-0">{f.l}</span>
                <input value={f.v} onChange={e => f.set(e.target.value)}
                  className="flex-1 bg-muted/20 border border-border/40 rounded-lg px-3 py-1.5 text-xs font-mono outline-none focus:border-primary/50" />
              </div>
            ))}
            <div className="flex items-center gap-3">
              <span className="text-[11px] text-muted-foreground w-16 shrink-0">Risk / trade</span>
              <input type="range" min="0.25" max="5" step="0.25" value={szRisk}
                onChange={e => setSzRisk(parseFloat(e.target.value))}
                className="flex-1 accent-[#7aff78]" />
              <span className="font-mono text-xs text-primary w-11 text-right">{szRisk.toFixed(2)}%</span>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2.5">
            {[
              { l: 'Units', v: sizing.units > 999 ? sizing.units.toFixed(0) : sizing.units.toFixed(4), c: 'text-emerald-400' },
              { l: 'Position size', v: fmtK(sizing.posValue), c: '' },
              { l: 'Risk amount', v: fmtUsd(sizing.riskDollar, 0), c: 'text-rose-400' },
              { l: 'Stop distance', v: sizing.entry > 0 ? `${(((sizing.entry - sizing.stop) / sizing.entry) * 100).toFixed(1)}%` : '—', c: '' },
              { l: 'Reward : Risk', v: `${sizing.rr.toFixed(2)} : 1`, c: sizing.rr >= 2 ? 'text-emerald-400' : sizing.rr >= 1 ? 'text-amber-400' : 'text-rose-400' },
              { l: '% of NAV', v: `${((sizing.posValue / (stats.totalValue || 1)) * 100).toFixed(1)}%`, c: sizing.posValue / (stats.totalValue || 1) > 0.25 ? 'text-rose-400' : '' },
            ].map(r => (
              <div key={r.l} className={`${TILE} p-2.5`}>
                <div className="text-[10px] text-muted-foreground mb-0.5">{r.l}</div>
                <div className={`font-mono text-sm font-bold ${r.c}`}>{r.v}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Alerts */}
        <div className={`${PANEL} p-5`}>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-md font-serif font-semibold flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-primary" /> Alerts
            </h3>
            <span className="text-[10px] font-mono text-muted-foreground">{alerts.length} active</span>
          </div>

          <select
            value={alertType}
            onChange={e => setAlertType(e.target.value as Alert['type'])}
            className="w-full bg-muted/20 border border-border/40 rounded-lg px-3 py-2 text-xs font-mono outline-none focus:border-primary/50 mb-2 cursor-pointer [&>option]:bg-[#111]"
          >
            {ALERT_TYPES.map(t => <option key={t.value} value={t.value}>{t.label} {t.value === 'DAILY_MOVE' ? '(%)' : '(USD)'}</option>)}
          </select>
          <div className="flex gap-2 mb-4">
            <input value={alertTarget} onChange={e => setAlertTarget(e.target.value)} placeholder={alertType === 'DAILY_MOVE' ? 'e.g. 5' : 'Trigger value'}
              className="flex-1 bg-muted/20 border border-border/40 rounded-lg px-3 py-1.5 text-xs font-mono outline-none focus:border-primary/50" />
            <Button size="sm" onClick={handleAddAlert}
              className="bg-primary/15 text-primary hover:bg-primary/25 border border-primary/30 text-xs font-bold cursor-pointer">
              <Plus className="w-3.5 h-3.5 mr-0.5" /> Add
            </Button>
          </div>

          <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
            {alerts.length === 0 && (
              <p className="text-xs text-muted-foreground font-mono text-center py-6">No alerts set. Define a threshold above.</p>
            )}
            {alerts.map(a => {
              const price = priceOf(a.symbol);
              const move = Math.abs(dayOf(a.symbol));
              let triggered = false;
              let status = '';
              if (a.type === 'PRICE_ABOVE') {
                triggered = price > 0 && price >= a.target;
                status = `Now $${price.toLocaleString(undefined, { maximumFractionDigits: 2 })} · ${triggered ? 'triggered' : price > 0 ? `${(((a.target / price) - 1) * 100).toFixed(1)}% away` : 'waiting'}`;
              } else if (a.type === 'PRICE_BELOW') {
                triggered = price > 0 && price <= a.target;
                status = `Now $${price.toLocaleString(undefined, { maximumFractionDigits: 2 })} · ${triggered ? 'triggered' : price > 0 ? `${(((1 - a.target / price)) * 100).toFixed(1)}% away` : 'waiting'}`;
              } else if (a.type === 'DAILY_MOVE') {
                triggered = move > a.target;
                status = `Today ${move.toFixed(2)}% · ${triggered ? 'triggered' : 'watching'}`;
              } else {
                status = 'Monitoring allocation';
              }
              return (
                <div key={a.id} className="flex items-center gap-2.5 bg-muted/10 border border-border/20 rounded-lg px-3 py-2">
                  <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${triggered ? 'bg-emerald-400 animate-pulse' : 'bg-muted-foreground/40'}`}></span>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs">
                      <span className="font-mono font-bold">{a.symbol}</span>{' '}
                      <span className="text-foreground/80">
                        {a.type === 'PRICE_ABOVE' ? `above $${a.target.toLocaleString()}`
                          : a.type === 'PRICE_BELOW' ? `below $${a.target.toLocaleString()}`
                          : `move > ${a.target}%`}
                      </span>
                    </div>
                    <div className="text-[10px] text-muted-foreground mt-0.5">{status}</div>
                  </div>
                  <button onClick={() => handleDeleteAlert(a.id)} className="text-muted-foreground hover:text-rose-400 cursor-pointer text-base leading-none">×</button>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* ─── MONTE CARLO + RETURN ATTRIBUTION ───────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
        <div className={`${PANEL} lg:col-span-3 p-5`}>
          <div className="flex items-baseline justify-between flex-wrap gap-3 mb-3">
            <h3 className="text-md font-serif font-semibold">Monte Carlo Projection</h3>
            <div className="flex items-center gap-4 flex-wrap">
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-muted-foreground">Horizon</span>
                <input type="range" min="1" max="20" step="1" value={mcYears}
                  onChange={e => setMcYears(parseInt(e.target.value, 10))}
                  className="w-20 accent-[#7aff78]" />
                <span className="font-mono text-[11px] text-primary w-7">{mcYears}y</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-muted-foreground">Monthly add</span>
                <input value={mcMonthly} onChange={e => setMcMonthly(e.target.value)}
                  className="w-20 bg-muted/20 border border-border/40 rounded-md px-2 py-1 font-mono text-[11px] outline-none focus:border-primary/50" />
              </div>
            </div>
          </div>
          <EChart option={mcOption} height={240} />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
            {[
              { l: 'Pessimistic (5%)', v: fmtK(monteCarlo.end.lo), c: 'text-rose-400', n: 'Worse than 95% of paths' },
              { l: 'Median (50%)', v: fmtK(monteCarlo.end.mid), c: 'text-emerald-400', n: `+${(((monteCarlo.end.mid / (stats.totalValue + monteCarlo.totalContrib)) - 1) * 100).toFixed(0)}% over contributions` },
              { l: 'Optimistic (95%)', v: fmtK(monteCarlo.end.hi), c: 'text-emerald-400', n: 'Top 5% of paths' },
              { l: 'Total invested', v: fmtK(stats.totalValue + monteCarlo.totalContrib), c: '', n: `${fmtUsd(monteCarlo.totalContrib, 0)} added` },
            ].map(o => (
              <div key={o.l} className={`${TILE} p-3`}>
                <div className="text-[10px] text-muted-foreground mb-0.5">{o.l}</div>
                <div className={`font-mono font-bold ${o.c}`}>{o.v}</div>
                <div className="text-[9.5px] text-muted-foreground/70 mt-0.5">{o.n}</div>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[11px] text-muted-foreground leading-relaxed">
            Lognormal GBM paths calibrated to your weighted portfolio volatility of {pVol.toFixed(1)}%, ~45% expected annual return, contributions reinvested monthly.
          </p>
        </div>

        <div className={`${PANEL} lg:col-span-2 p-5`}>
          <div className="flex items-baseline justify-between mb-3 flex-wrap gap-2">
            <h3 className="text-md font-serif font-semibold">Return Attribution</h3>
            <span className="text-[11px] text-muted-foreground">Contribution to total gain</span>
          </div>
          {attributionRows.length > 0 ? (
            <>
              <EChart option={attributionOption} height={Math.max(160, attributionRows.length * 36 + 16)} />
              <div className="mt-3 pt-3 border-t border-border/20 flex justify-between text-xs">
                <span className="text-muted-foreground">Total unrealized</span>
                <span className={`font-mono font-bold ${stats.unrealizedPnL >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {stats.unrealizedPnL >= 0 ? '+' : '-'}{fmtUsd(Math.abs(stats.unrealizedPnL))} ({fmtPct(stats.roiPercent)})
                </span>
              </div>
            </>
          ) : (
            <p className="text-xs text-muted-foreground font-mono text-center py-10">Attribution unlocks once you hold assets.</p>
          )}
        </div>
      </div>

      {/* ─── COST BASIS & DCA ───────────────────────────────────────────────── */}
      <div className={`${PANEL} p-5 mb-6`}>
        <div className="flex items-baseline justify-between mb-4 flex-wrap gap-2">
          <h3 className="text-md font-serif font-semibold">Cost Basis &amp; DCA</h3>
          <span className="text-[11px] text-muted-foreground">Average entry vs. live market — {taxMethod} accounting</span>
        </div>
        <EChart option={costBasisOption} height={260} />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3 mt-4">
          {stats.holdings.map(h => {
            const spread = ((h.currentPrice / h.avgCost) - 1) * 100;
            return (
              <div key={h.symbol} className={`${TILE} p-3`}>
                <div className="flex justify-between items-baseline mb-1.5">
                  <span className="font-mono font-bold text-xs">{h.symbol}</span>
                  <span className={`font-mono text-[11px] font-bold ${spread >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{fmtPct(spread)}</span>
                </div>
                <div className="text-[10px] text-muted-foreground space-y-0.5">
                  <div>Avg <span className="font-mono text-foreground/80">${h.avgCost.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span></div>
                  <div>Now <span className="font-mono text-foreground/80">${h.currentPrice.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span></div>
                  <div>Break-even <span className="font-mono text-foreground/80">${(h.avgCost * 1.002).toLocaleString(undefined, { maximumFractionDigits: 2 })}</span></div>
                </div>
              </div>
            );
          })}
          {stats.holdings.length === 0 && <p className="text-xs text-muted-foreground col-span-full text-center py-4">No cost basis to compare.</p>}
        </div>
      </div>

      {/* ─── ADD TRANSACTION MODAL ──────────────────────────────────────────── */}
      {isAddOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-md animate-in fade-in duration-300">
          <div className="bg-card border border-border/80 rounded-2xl shadow-2xl w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="p-5 border-b border-border/40 flex items-center justify-between bg-muted/10">
              <h2 className="text-md font-serif font-semibold flex items-center gap-2.5">
                <PlusCircle className="w-5 h-5 text-primary" />
                Record Transaction
              </h2>
              <button onClick={() => setIsAddOpen(false)} className="text-muted-foreground hover:text-foreground transition-colors cursor-pointer">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-5">
              <div className="grid grid-cols-2 gap-4">
                <Button variant="outline"
                  className={`border-border/40 font-mono transition-all rounded-xl cursor-pointer ${txType === 'BUY' ? 'bg-primary/10 text-primary border-primary/50 font-bold' : 'bg-transparent text-muted-foreground'}`}
                  onClick={() => setTxType('BUY')}>
                  Buy / Long
                </Button>
                <Button variant="outline"
                  className={`border-border/40 font-mono transition-all rounded-xl cursor-pointer ${txType === 'SELL' ? 'bg-rose-500/10 text-rose-400 border-rose-500/40 font-bold' : 'bg-transparent text-muted-foreground'}`}
                  onClick={() => setTxType('SELL')}>
                  Sell / Short
                </Button>
              </div>

              <div className="space-y-2 relative" ref={symbolDropdownRef}>
                <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">Asset Token Symbol</label>
                <div className="relative">
                  <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                    <Search className="h-4 w-4 text-muted-foreground/60" />
                  </span>
                  <input
                    type="text"
                    value={symbolSearchQuery}
                    onFocus={() => setShowSymbolDropdown(true)}
                    onChange={(e) => {
                      setSymbolSearchQuery(e.target.value);
                      setTxSymbol(e.target.value);
                      setShowSymbolDropdown(true);
                    }}
                    className="w-full bg-background border border-border/50 rounded-xl pl-10 pr-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary uppercase font-mono"
                    placeholder="Search e.g. BTC, ETH..."
                  />
                </div>

                {showSymbolDropdown && filteredSymbolOptions.length > 0 && (
                  <div className="absolute z-50 left-0 right-0 mt-1 max-h-56 overflow-y-auto bg-card border border-border/80 rounded-xl shadow-xl divide-y divide-border/20">
                    {filteredSymbolOptions.map(asset => (
                      <div
                        key={asset.symbol}
                        onClick={() => {
                          setTxSymbol(asset.symbol);
                          setSymbolSearchQuery(asset.symbol);
                          setTxPrice(String(asset.price));
                          if (txTotalSpent) setTxQty(String(parseFloat(txTotalSpent) / asset.price));
                          else if (txQty) setTxTotalSpent((parseFloat(txQty) * asset.price).toFixed(2));
                          setShowSymbolDropdown(false);
                        }}
                        className="flex items-center justify-between px-4 py-2.5 hover:bg-muted/30 cursor-pointer transition-colors text-xs font-mono"
                      >
                        <div className="flex flex-col">
                          <span className="font-bold text-foreground">{asset.symbol}</span>
                          <span className="text-[10px] text-muted-foreground">{asset.name}</span>
                        </div>
                        <span className="text-muted-foreground font-semibold">${asset.price.toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">Price per Token ($)</label>
                <input type="number" step="any" value={txPrice} onChange={e => handlePriceChange(e.target.value)}
                  className="w-full bg-background border border-border/50 rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary font-mono"
                  placeholder="0.00" />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">Quantity</label>
                  <input type="number" step="any" value={txQty} onChange={e => handleQtyChange(e.target.value)}
                    className="w-full bg-background border border-border/50 rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary font-mono"
                    placeholder="0.00" />
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-mono text-primary uppercase tracking-wider block">Total Spent ($)</label>
                  <input type="number" step="any" value={txTotalSpent} onChange={e => handleSpentChange(e.target.value)}
                    className="w-full bg-background border border-primary/40 rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary font-mono shadow-sm shadow-primary/5"
                    placeholder="e.g. 30.00" />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">Trading Fee ($)</label>
                  <input type="number" value={txFee} onChange={e => setTxFee(e.target.value)}
                    className="w-full bg-background border border-border/50 rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary font-mono"
                    placeholder="0.00" />
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">Trade Date</label>
                  <div className="relative">
                    <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                      <Calendar className="h-4 w-4 text-muted-foreground/60" />
                    </span>
                    <input type="date" value={txDate} onChange={e => setTxDate(e.target.value)}
                      className="w-full bg-background border border-border/50 rounded-xl pl-10 pr-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary font-mono cursor-pointer" />
                  </div>
                </div>
              </div>
            </div>

            <div className="p-5 border-t border-border/40 bg-muted/10 flex justify-end gap-3">
              <Button variant="ghost" onClick={() => setIsAddOpen(false)}
                className="text-muted-foreground hover:text-foreground cursor-pointer rounded-xl font-mono text-xs">
                Cancel
              </Button>
              <Button className="bg-primary hover:bg-primary/90 text-primary-foreground font-semibold rounded-xl px-4 font-mono text-xs shadow-md cursor-pointer"
                onClick={handleAddTransaction}
                disabled={isUpdating || !txSymbol || !txQty || !txPrice}>
                {isUpdating ? 'Saving...' : 'Save Transaction'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Ambient brand glow */}
      <div aria-hidden className="pointer-events-none absolute top-0 left-1/4 right-0 h-96 opacity-40"
        style={{ background: 'radial-gradient(ellipse at center, rgba(122,255,120,0.10) 0%, transparent 65%)', filter: 'blur(20px)' }} />
    </div>
  );
}
