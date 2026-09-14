'use client';

// ── Chart widgets — ECharts line charts for the Command Center ──────────────
// Asset price + EMA/RSI, economic data series, and portfolio fund performance.
// Each consumes DataHub topics and renders an ECharts line chart. Never fabricates.

import React, { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import { useTopic } from '@/lib/workspace/data-hub';
import { cn } from '@/lib/utils';
import { cssVarToHex } from '@/lib/chart-colors';
import { baseChartOption, useEChart } from '@/components/screens/portfolio/use-echart';
import { usePortfolioPerformance, useFundComparison } from './portfolio-store';
import { getTradingViewSymbol } from '@/lib/utils';
import { defaultChartState, type ChartState } from '@/lib/chart/types';
import type { WidgetPlacement } from '@/lib/workspace/types';
import { ChartWidget } from '@/components/chart/chart-widget';

interface Bar { date: string; open: number | null; high: number | null; low: number | null; close: number; volume: number | null; }
interface PriceHistory { symbol: string; currency: string; points: number[]; series: Bar[]; perf?: { week?: number; month?: number; quarter?: number }; }
interface EconPoint { date: string; value: number; }
interface EconSeries { source: string; seriesKey: string; rows: EconPoint[]; }
interface SnapshotMetric { id: string; label: string; value: number | null; unit: string; country: string; }

function WidgetHeader({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-border/10 pb-2.5 mb-3">
      <h3 className="font-serif text-sm font-semibold text-foreground truncate">{title}</h3>
      {hint && <span className="font-mono text-[9px] text-muted-foreground/70 shrink-0">{hint}</span>}
    </div>
  );
}

function EmptyNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-1 items-center justify-center py-8 text-center">
      <p className="text-xs text-muted-foreground/70 italic">{children}</p>
    </div>
  );
}

// ── Technical indicators (deterministic) ───────────────────────────────────

function ema(values: number[], period: number): (number | null)[] {
  const k = 2 / (period + 1);
  const out: (number | null)[] = [];
  let prev: number | null = null;
  for (let i = 0; i < values.length; i++) {
    if (i < period - 1) { out.push(null); continue; }
    if (prev === null) {
      const sum = values.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0);
      prev = sum / period;
    } else {
      prev = values[i] * k + prev * (1 - k);
    }
    out.push(prev);
  }
  return out;
}

function rsi(values: number[], period = 14): (number | null)[] {
  const out: (number | null)[] = [];
  let avgGain = 0, avgLoss = 0;
  for (let i = 0; i < values.length; i++) {
    if (i === 0) { out.push(null); continue; }
    const change = values[i] - values[i - 1];
    const gain = Math.max(0, change);
    const loss = Math.max(0, -change);
    if (i <= period) {
      avgGain += gain; avgLoss += loss;
      if (i === period) { avgGain /= period; avgLoss /= period; }
      out.push(null);
      continue;
    }
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    if (avgLoss === 0) { out.push(100); continue; }
    const rs = avgGain / avgLoss;
    out.push(100 - 100 / (1 + rs));
  }
  return out;
}

// ── Asset line chart with EMA + RSI ─────────────────────────────────────────

export function AssetChartWidget() {
  const t = useTopic<PriceHistory>('chart:asset:AAPL');
  const data = t.data;
  const primary = useMemo(() => cssVarToHex('--primary', '#34d399'), []);
  const ema20 = useMemo(() => (data?.points ? ema(data.points, 20) : []), [data?.points]);
  const ema50 = useMemo(() => (data?.points ? ema(data.points, 50) : []), [data?.points]);
  const rsi14 = useMemo(() => (data?.points ? rsi(data.points, 14) : []), [data?.points]);
  const dates = useMemo(() => data?.series?.map(b => b.date) ?? [], [data?.series]);

  const ref = useEChart(() => {
    if (!data?.points || data.points.length < 2) return null;
    return {
      ...baseChartOption(),
      grid: { left: 8, right: 8, top: 10, bottom: 0, containLabel: true },
      xAxis: { type: 'category', data: dates, axisLabel: { color: '#94a3b8', fontSize: 9 }, axisLine: { lineStyle: { color: 'rgba(148,163,184,0.04)' } } },
      yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: 'rgba(148,163,184,0.03)' } }, axisLabel: { color: '#94a3b8', fontSize: 9 } },
      series: [
        { name: 'Close', type: 'line', data: data.points, showSymbol: false, lineStyle: { width: 2, color: primary }, areaStyle: { color: primary, opacity: 0.08 } },
        { name: 'EMA 20', type: 'line', data: ema20, showSymbol: false, lineStyle: { width: 1, color: '#fbbf24' } },
        { name: 'EMA 50', type: 'line', data: ema50, showSymbol: false, lineStyle: { width: 1, color: '#60a5fa' } },
      ],
      legend: { bottom: 0, textStyle: { color: '#94a3b8', fontSize: 9 }, itemWidth: 12 },
    } as EChartsOption;
  }, [data, dates, ema20, ema50, primary]);

  const rsiRef = useEChart(() => {
    if (!data?.points || data.points.length < 2) return null;
    return {
      ...baseChartOption(),
      grid: { left: 8, right: 8, top: 4, bottom: 0, containLabel: true },
      xAxis: { type: 'category', data: dates, axisLabel: { show: false }, axisLine: { lineStyle: { color: 'rgba(148,163,184,0.04)' } } },
      yAxis: { type: 'value', min: 0, max: 100, splitLine: { lineStyle: { color: 'rgba(148,163,184,0.03)' } }, axisLabel: { color: '#94a3b8', fontSize: 8 } },
      series: [{ name: 'RSI 14', type: 'line', data: rsi14, showSymbol: false, lineStyle: { width: 1, color: '#a78bfa' } }],
    } as EChartsOption;
  }, [data, dates, rsi14]);

  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title={`${data?.symbol ?? 'AAPL'} Chart`} hint="EMA · RSI" />
      {!data || data.points.length < 2 ? <EmptyNote>Loading price history…</EmptyNote> : (
        <div className="flex flex-1 flex-col gap-2">
          <div ref={ref} className="min-h-[120px] flex-1" />
          <div ref={rsiRef} className="h-16 shrink-0" />
        </div>
      )}
    </div>
  );
}

// ── Economic data chart ──────────────────────────────────────────────────────

export function EconomicDataChartWidget() {
  const t = useTopic<EconSeries>('econ:series:us-cpi');
  const data = t.data;
  const primary = useMemo(() => cssVarToHex('--primary', '#34d399'), []);
  const dates = useMemo(() => data?.rows?.map(r => r.date) ?? [], [data?.rows]);
  const values = useMemo(() => data?.rows?.map(r => r.value) ?? [], [data?.rows]);

  const ref = useEChart(() => {
    if (!data?.rows || data.rows.length < 2) return null;
    return {
      ...baseChartOption(),
      grid: { left: 8, right: 8, top: 10, bottom: 0, containLabel: true },
      xAxis: { type: 'category', data: dates, axisLabel: { color: '#94a3b8', fontSize: 9 }, axisLine: { lineStyle: { color: 'rgba(148,163,184,0.04)' } } },
      yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: 'rgba(148,163,184,0.03)' } }, axisLabel: { color: '#94a3b8', fontSize: 9 } },
      series: [{ name: data.seriesKey, type: 'line', data: values, showSymbol: false, lineStyle: { width: 2, color: primary }, areaStyle: { color: primary, opacity: 0.08 } }],
    } as EChartsOption;
  }, [data, dates, values, primary]);

  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Economic Data" hint={data?.seriesKey ?? 'US CPI'} />
      {!data || data.rows.length < 2 ? <EmptyNote>Loading economic series…</EmptyNote> : (
        <div ref={ref} className="min-h-[160px] flex-1" />
      )}
    </div>
  );
}

// ── Portfolio performance (ALL funds) ────────────────────────────────────────
// Aggregates every fund's ledger with real price histories into one indexed
// performance curve (100 = first holding) and overlays user-chosen benchmarks.

const COMPARE_COLORS = ['#94a3b8', '#fbbf24', '#60a5fa', '#f472b6', '#a78bfa', '#2dd4bf'];

function readCompare(config: unknown): string[] {
  if (Array.isArray(config)) return config.map(s => String(s).toUpperCase().trim()).filter(Boolean).slice(0, 6);
  if (typeof config === 'string') return config.split(',').map(s => s.toUpperCase().trim()).filter(Boolean).slice(0, 6);
  return ['SPY'];
}

export function FundPerformanceChartWidget({ placement }: { placement?: WidgetPlacement }) {
  const compare = useMemo(() => readCompare(placement?.config?.compare), [placement?.config?.compare]);
  const perf = usePortfolioPerformance(compare);
  const primary = useMemo(() => cssVarToHex('--primary', '#34d399'), []);

  const ref = useEChart(() => {
    if (!perf?.portfolio || perf.portfolio.length < 2) return null;
    return {
      ...baseChartOption(),
      grid: { left: 8, right: 8, top: 26, bottom: 0, containLabel: true },
      xAxis: { type: 'category', data: perf.dates, axisLabel: { color: '#94a3b8', fontSize: 9 }, axisLine: { lineStyle: { color: 'rgba(148,163,184,0.04)' } } },
      yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: 'rgba(148,163,184,0.03)' } }, axisLabel: { color: '#94a3b8', fontSize: 9 } },
      series: [
        { name: 'Portfolio', type: 'line', data: perf.portfolio, showSymbol: false, smooth: true, lineStyle: { width: 2, color: primary }, areaStyle: { color: primary, opacity: 0.14 } },
        ...perf.benchmarks.map((b, i) => ({
          name: b.symbol,
          type: 'line' as const,
          data: b.data,
          showSymbol: false,
          smooth: true,
          lineStyle: { width: 1, color: COMPARE_COLORS[i % COMPARE_COLORS.length], type: 'dashed' as const },
        })),
      ],
      legend: { top: 0, right: 4, textStyle: { color: '#94a3b8', fontSize: 9 }, itemWidth: 12 },
    } as EChartsOption;
  }, [perf, primary]);

  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Portfolio Performance" hint={compare.length ? `ALL FUNDS · ${compare.join(' · ')}` : 'ALL FUNDS'} />
      {!perf || perf.portfolio.length < 2 ? (
        <EmptyNote>Add transactions in the Portfolio page — the curve indexes to 100 at your first holding.</EmptyNote>
      ) : (
        <div ref={ref} className="min-h-[160px] flex-1" />
      )}
    </div>
  );
}

// ── Overall performance (each fund vs the benchmarks) ────────────────────────
// Mirrors the Portfolio page's "Overall Performance" chart: one indexed line per
// fund plus the standard benchmarks (SPY/QQQ/BTC-USD) as dashed references.

export function FundsComparisonChartWidget() {
  const { lines, ready } = useFundComparison();

  const ref = useEChart(() => {
    if (lines.length === 0) return null;
    const len = Math.min(...lines.map(l => l.nav.length));
    const navs = lines.map(l => l.nav.slice(-len));
    return {
      ...baseChartOption(),
      grid: { left: 8, right: 8, top: 8, bottom: 0, containLabel: true },
      xAxis: {
        type: 'category',
        data: lines[0].dates.length >= len ? lines[0].dates.slice(-len) : Array.from({ length: len }, (_, i) => i),
        axisLine: { lineStyle: { color: 'rgba(148,163,184,0.04)' } },
        axisLabel: { color: '#94a3b8', fontSize: 9 },
      },
      yAxis: {
        type: 'value',
        scale: true,
        splitLine: { lineStyle: { color: 'rgba(148,163,184,0.03)' } },
        axisLabel: { color: '#94a3b8', fontSize: 9, formatter: (v: number) => v.toFixed(2) },
      },
      series: navs.map((nav, i) => ({
        name: lines[i].name,
        type: 'line' as const,
        data: nav.map(v => Number(v.toFixed(4))),
        showSymbol: false,
        lineStyle: { width: lines[i].dashed ? 1.2 : 2, color: lines[i].color, type: lines[i].dashed ? ('dashed' as const) : ('solid' as const) },
        emphasis: { focus: 'series' as const },
      })),
      legend: { show: false },
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(18,18,20,0.5)', appendTo: 'body',
        borderColor: 'rgba(255,255,255,0.12)',
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: '#e5e7eb', fontSize: 11 },
        extraCssText:
          'backdrop-filter: blur(18px) saturate(1.35); border-radius: 14px; box-shadow: 0 8px 30px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.06);',
        valueFormatter: (v: unknown) => (typeof v === 'number' ? `${((v - 1) * 100).toFixed(2)}%` : String(v)),
      },
    } as EChartsOption;
  }, [lines]);

  const header = (
    <div className="mb-1 flex flex-wrap items-center gap-x-3 gap-y-1">
      {lines.map(l => {
        const ret = l.nav.length >= 2 ? ((l.nav[l.nav.length - 1] / l.nav[0]) - 1) * 100 : 0;
        return (
          <span key={l.name} className="flex items-center gap-1.5 font-mono text-[10px]">
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: l.color }} />
            <span className="text-muted-foreground">{l.name}</span>
            <span className={cn('font-bold', ret >= 0 ? 'text-emerald-400' : 'text-rose-400')}>{ret >= 0 ? '+' : ''}{ret.toFixed(2)}%</span>
          </span>
        );
      })}
    </div>
  );

  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Overall Performance" hint="FUNDS vs BENCHMARKS · 3MO · INDEXED" />
      {lines.length === 0 ? (
        <EmptyNote>{ready ? 'Add holdings across your funds to compare performance.' : 'Loading price history…'}</EmptyNote>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col">
          {header}
          <div ref={ref} className="min-h-[180px] flex-1" />
        </div>
      )}
    </div>
  );
}

// ── Macro snapshot (rates + prints) ─────────────────────────────────────────

export function MacroSnapshotWidget() {
  const t = useTopic<{ metrics: SnapshotMetric[] }>('econ:snapshot');
  const metrics = t.data?.metrics ?? [];
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Macro Snapshot" hint="RATES · CPI" />
      {metrics.length === 0 ? <EmptyNote>Loading macro data…</EmptyNote> : (
        <div className="flex flex-1 flex-col gap-1 overflow-y-auto scrollbar-hide">
          {metrics.slice(0, 12).map(m => (
            <div key={m.id} className="flex items-center justify-between text-[10px] py-0.5">
              <span className="text-muted-foreground truncate">{m.label}</span>
              <span className="font-mono text-foreground">{m.value != null ? `${m.value}${m.unit}` : '—'}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── TradingView chart ─────────────────────────────────────────────────────────

export function TradingViewChartWidget({ placement }: { placement?: WidgetPlacement }) {
  const storageKey = `be_tv_symbol:${placement?.id ?? 'default'}`;
  const [symbol, setSymbol] = React.useState((placement?.config?.symbol as string) || 'AAPL');
  const containerRef = React.useRef<HTMLDivElement>(null);

  // Restore the last-viewed symbol for this widget instance on mount.
  React.useEffect(() => {
    try {
      const saved = window.localStorage.getItem(storageKey);
      if (saved) setSymbol(saved);
    } catch { /* ignore */ }
  }, [storageKey]);

  const chooseSymbol = (value: string) => {
    const next = value.toUpperCase();
    setSymbol(next);
    try { window.localStorage.setItem(storageKey, next); } catch { /* ignore */ }
  };

  React.useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const tvSymbol = getTradingViewSymbol(symbol);
    container.innerHTML = '';
    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: tvSymbol,
      interval: 'D',
      timezone: 'Etc/UTC',
      theme: 'dark',
      style: '1',
      locale: 'en',
      allow_symbol_change: true,
      hide_side_toolbar: false,
      hide_legend: false,
      studies: ['STD;RSI'],
    });
    container.appendChild(script);
    return () => { container.innerHTML = ''; };
  }, [symbol]);

  return (
    <div className="flex h-full flex-col p-4">
      <div className="flex items-center justify-between gap-2 border-b border-border/10 pb-2.5 mb-3">
        <h3 className="font-serif text-sm font-semibold text-foreground truncate">{symbol} — TradingView</h3>
        <div className="flex items-center gap-1.5 shrink-0">
          <input
            value={symbol}
            onChange={e => chooseSymbol(e.target.value)}
            placeholder="Symbol"
            className="w-24 rounded-lg border border-white/10 dark:border-white/10 bg-background/60 px-2 py-1 text-[10px] font-mono text-foreground focus:ring-1 focus:ring-primary outline-none"
          />
          <span className="font-mono text-[9px] text-muted-foreground/70">{getTradingViewSymbol(symbol)}</span>
        </div>
      </div>
      <div ref={containerRef} className="min-h-0 flex-1 overflow-hidden rounded-xl border border-border/10" />
    </div>
  );
}

// ── Eclipse Chart widget — the native provider-switchable chart ───────────────
// Wraps the full ChartWidget (Eclipse + TradingView providers, indicators,
// timeframes) so it can live inside the Command Center dashboard. Symbol is
// configurable per-instance via the widget config panel.

export function EclipseChartWidget({ placement }: { placement?: WidgetPlacement }) {
  // Fully controlled chart state, persisted per widget instance so symbol,
  // market, timeframe, provider, indicators and drawings all survive a reload.
  const storageKey = `be_chart_state:${placement?.id ?? 'default'}`;
  const [chartState, setChartState] = React.useState<ChartState>(() => {
    const base = defaultChartState({
      symbol: (placement?.config?.symbol as string) || 'AAPL',
      market: (placement?.config?.market as string) || 'US',
    });
    if (typeof window !== 'undefined') {
      try {
        const raw = window.localStorage.getItem(storageKey);
        if (raw) return { ...base, ...(JSON.parse(raw) as Partial<ChartState>) };
      } catch { /* ignore corrupt storage */ }
    }
    return base;
  });

  const handleStateChange = (next: ChartState) => {
    setChartState(next);
    try { window.localStorage.setItem(storageKey, JSON.stringify(next)); } catch { /* ignore */ }
  };

  return (
    <div className="flex h-full w-full flex-col p-2" style={{ minHeight: 620 }}>
      <ChartWidget
        symbol={chartState.symbol}
        market={chartState.market}
        state={chartState}
        onStateChange={handleStateChange}
        className="h-full"
      />
    </div>
  );
}
