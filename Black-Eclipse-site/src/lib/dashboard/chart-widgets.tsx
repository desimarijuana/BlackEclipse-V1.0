'use client';

// ── Chart widgets — ECharts line charts for the Command Center ──────────────
// Asset price + EMA/RSI, economic data series, and portfolio fund performance.
// Each consumes DataHub topics and renders an ECharts line chart. Never fabricates.

import React, { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import { useTopic } from '@/lib/workspace/data-hub';
import { cssVarToHex } from '@/lib/chart-colors';
import { baseChartOption, useEChart } from '@/components/screens/portfolio/use-echart';
import { getTradingViewSymbol } from '@/lib/utils';
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

// ── Portfolio fund performance ───────────────────────────────────────────────

export function FundPerformanceChartWidget() {
  const t = useTopic<{ nav: number[]; navDates: string[]; benchmarkNav: number[] }>('portfolio:fund:nav');
  const data = t.data;
  const primary = useMemo(() => cssVarToHex('--primary', '#34d399'), []);

  const ref = useEChart(() => {
    if (!data?.nav || data.nav.length < 2) return null;
    const dates = data.navDates?.length ? data.navDates : data.nav.map((_, i) => String(i));
    return {
      ...baseChartOption(),
      grid: { left: 8, right: 8, top: 10, bottom: 0, containLabel: true },
      xAxis: { type: 'category', data: dates, axisLabel: { color: '#94a3b8', fontSize: 9 }, axisLine: { lineStyle: { color: 'rgba(148,163,184,0.04)' } } },
      yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: 'rgba(148,163,184,0.03)' } }, axisLabel: { color: '#94a3b8', fontSize: 9 } },
      series: [
        { name: 'Fund NAV', type: 'line', data: data.nav, showSymbol: false, lineStyle: { width: 2, color: primary }, areaStyle: { color: primary, opacity: 0.08 } },
        ...(data.benchmarkNav?.length === data.nav.length
          ? [{ name: 'Benchmark', type: 'line' as const, data: data.benchmarkNav, showSymbol: false, lineStyle: { width: 1, color: '#94a3b8', type: 'dashed' as const } }]
          : []),
      ],
      legend: data.benchmarkNav?.length ? { bottom: 0, textStyle: { color: '#94a3b8', fontSize: 9 }, itemWidth: 12 } : undefined,
    } as EChartsOption;
  }, [data, primary]);

  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Fund Performance" hint="NAV" />
      {!data || data.nav.length < 2 ? <EmptyNote>Loading fund performance…</EmptyNote> : (
        <div ref={ref} className="min-h-[160px] flex-1" />
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
  const [symbol, setSymbol] = React.useState((placement?.config?.symbol as string) || 'AAPL');
  const containerRef = React.useRef<HTMLDivElement>(null);

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
            onChange={e => setSymbol(e.target.value.toUpperCase())}
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
  const symbol = (placement?.config?.symbol as string) || 'AAPL';
  const market = (placement?.config?.market as string) || 'US';
  return (
    <div className="flex h-full w-full flex-col p-2" style={{ minHeight: 420 }}>
      <ChartWidget symbol={symbol} market={market} className="h-full" />
    </div>
  );
}
