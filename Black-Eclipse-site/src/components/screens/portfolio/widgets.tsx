'use client';

// ── Fund widgets (pure) ──────────────────────────────────────────────────────
// Every widget consumes the engines' computed outputs via props and reports
// null/empty where data is missing — never fabricates. All edit chrome lives
// in the kernel shells; these components render content only.

import React, { useMemo, useState } from 'react';
import {
  Activity, Brain, ChartLine, Gauge, HeartPulse, Layers, PieChart,
  Table2, Wallet,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { fmtK, fmtPct, fmtUsd } from '@/lib/portfolio-analysis';
import { computeMonteCarlo } from '@/lib/portfolio-analysis';
import { cssVarToHex } from '@/lib/chart-colors';
import { normalizeLayout } from '@/lib/workspace/ops';
import type { WorkspaceLayout } from '@/lib/workspace/types';
import type { WorkspaceWidgetMeta } from '@/lib/workspace/workspace-drawer';
import { baseChartOption, useEChart } from './use-echart';
import type { FundData } from './use-fund-data';
import type { Fund } from '@/lib/portfolio/types';

export interface WidgetProps {
  fund: Fund;
  data: FundData;
}

const UP = 'text-emerald-400';
const DOWN = 'text-rose-400';
const toneClass = (n: number) => (n > 0 ? UP : n < 0 ? DOWN : 'text-muted-foreground');

function WidgetHeader({ icon: Icon, title, hint }: { icon: React.ComponentType<{ size?: number; className?: string }>; title: string; hint?: string }) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-border/10 pb-2.5 mb-3">
      <div className="flex items-center gap-2 min-w-0">
        <Icon size={14} className="text-primary shrink-0" />
        <h3 className="font-serif text-sm font-semibold text-foreground truncate">{title}</h3>
      </div>
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

const Tile = React.forwardRef<HTMLDivElement, {
  label: string; value: string; tone?: string; sub?: string; loading?: boolean;
}>(function Tile({ label, value, tone, sub, loading }, ref) {
  return (
    <div ref={ref} className="flex min-w-0 flex-col justify-center rounded-xl bg-white/[0.04] dark:bg-white/[0.04] border border-white/15 dark:border-white/10 backdrop-blur-md p-3">
      <p className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground truncate">{label}</p>
      {loading ? (
        <span className="mt-1.5 block h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground/70" aria-hidden />
      ) : (
        <>
          <p className={cn('mt-1 font-mono text-sm font-bold truncate', tone ?? 'text-foreground')}>{value}</p>
          {sub && <p className={cn('font-mono text-[10px] truncate', tone ?? 'text-muted-foreground')}>{sub}</p>}
        </>
      )}
    </div>
  );
});

// ── KPI board ────────────────────────────────────────────────────────────────

export function KpiBoardWidget({ data }: WidgetProps) {
  const s = data.stats;
  const holdingsCount = s.holdings.length;
  const ld = data.loading && !data.ready;
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader icon={Wallet} title="Key Metrics" hint={s.base} />
      <div className="grid flex-1 auto-rows-fr grid-cols-2 gap-2.5 lg:grid-cols-4">
        <Tile label="Total Value" value={fmtUsd(s.totalValue)} sub={`Cash ${fmtUsd(data.cash)}`} loading={ld} />
        <Tile label="Unrealized P/L" value={fmtUsd(s.unrealizedPnL)} tone={toneClass(s.unrealizedPnL)} sub={fmtPct(s.roiPercent)} loading={ld} />
        <Tile label="Day Change" value={fmtUsd(s.dailyChangeValue)} tone={toneClass(s.dailyChangeValue)} sub={fmtPct(s.dailyChangePercent)} loading={ld} />
        <Tile label="Holdings" value={String(holdingsCount)} sub={`Realized ${fmtUsd(s.realizedPnL)}`} />
      </div>
      {holdingsCount === 0 && <EmptyNote>No open positions — add transactions in the ledger.</EmptyNote>}
    </div>
  );
}

// ── Performance (NAV vs benchmark) ───────────────────────────────────────────

export function PerformanceWidget({ data }: WidgetProps) {
  const primary = useMemo(() => cssVarToHex('--primary', '#34d399'), []);
  const benchColor = '#94a3b8';
  const hasNav = data.risk.nav.length >= 2;
  const ref = useEChart(() => {
    if (!hasNav) return null;
    const grid = { left: 8, right: 8, top: 10, bottom: 0, containLabel: true };
    return {
      ...baseChartOption(),
      grid,
      xAxis: { type: 'category', data: data.risk.navDates.length ? data.risk.navDates : data.risk.nav.map((_, i) => i), axisLine: { lineStyle: { color: '#334155' } }, axisLabel: { color: '#94a3b8', fontSize: 9 } },
      yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: 'rgba(148,163,184,0.12)' } }, axisLabel: { color: '#94a3b8', fontSize: 9, formatter: (v: number) => v.toFixed(2) } },
      series: [
        { name: 'Fund NAV', type: 'line', data: data.risk.nav, showSymbol: false, lineStyle: { width: 2, color: primary }, areaStyle: { color: primary, opacity: 0.08 } },
        ...(data.risk.benchmarkNav.length === data.risk.nav.length
          ? [{ name: 'SPY', type: 'line' as const, data: data.risk.benchmarkNav, showSymbol: false, lineStyle: { width: 1, color: benchColor, type: 'dashed' as const } }]
          : []),
      ],
      legend: data.risk.benchmarkNav.length ? { bottom: 0, textStyle: { color: '#94a3b8', fontSize: 9 }, itemWidth: 12 } : undefined,
    };
  }, [hasNav, data.risk.nav, data.risk.benchmarkNav, data.risk.navDates, primary]);

  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader icon={ChartLine} title="Performance" hint="NAV · 3MO" />
      {hasNav ? <div ref={ref} className="min-h-[160px] flex-1" />
        : <EmptyNote>Price history unavailable for current holdings yet.</EmptyNote>}
    </div>
  );
}

// ── Allocation ───────────────────────────────────────────────────────────────

const DONUT_COLORS = ['#34d399', '#60a5fa', '#fbbf24', '#f472b6', '#a78bfa', '#2dd4bf', '#fb7185', '#f97316', '#94a3b8'];

export function AllocationWidget({ data }: WidgetProps) {
  const holdings = data.stats.holdings;
  const ref = useEChart(() => {
    if (!holdings.length) return null;
    return {
      ...baseChartOption(),
      tooltip: { trigger: 'item', backgroundColor: 'rgba(15,15,15,0.92)', borderWidth: 0, textStyle: { color: '#e5e7eb', fontSize: 11 } },
      series: [{
        type: 'pie', radius: ['58%', '82%'], center: ['50%', '50%'],
        label: { show: false }, silent: false,
        data: holdings.slice(0, 9).map((h, i) => ({ name: h.symbol, value: Number(h.valueUsd.toFixed(2)), itemStyle: { color: DONUT_COLORS[i % DONUT_COLORS.length] } })),
      }],
    };
  }, [holdings]);

  if (!holdings.length) {
    return (
      <div className="flex h-full flex-col p-4">
        <WidgetHeader icon={PieChart} title="Allocation" />
        <EmptyNote>No holdings to allocate yet.</EmptyNote>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader icon={PieChart} title="Allocation" hint={`${holdings.length} POS`} />
      <div ref={ref} className="min-h-[120px] flex-1" />
      <div className="mt-2 flex min-h-0 shrink-0 flex-col gap-1">
        {holdings.map((h, i) => (
          <div key={h.symbol} className="flex items-center gap-2 text-xs">
            <span className="w-2 h-2 rounded-full shrink-0" style={{ background: DONUT_COLORS[i % DONUT_COLORS.length] }} />
            <span className="font-mono font-bold text-foreground w-16 truncate">{h.symbol}</span>
            <div className="flex-1 h-1 rounded-full bg-border/40 overflow-hidden">
              <div className="h-full rounded-full" style={{ width: `${Math.min(100, h.allocation)}%`, background: DONUT_COLORS[i % DONUT_COLORS.length] }} />
            </div>
            <span className="font-mono text-[10px] text-muted-foreground w-10 text-right">{h.allocation.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Holdings table ───────────────────────────────────────────────────────────

export function HoldingsWidget({ fund, data }: WidgetProps) {
  const holdings = data.stats.holdings;
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader icon={Table2} title="Holdings" hint={`${holdings.length}`} />
      {holdings.length === 0 ? <EmptyNote>No open positions.</EmptyNote> : (
        <div className="flex-1 overflow-auto custom-scrollbar rounded-xl border border-white/15 dark:border-white/10 bg-white/[0.04] dark:bg-white/[0.04] backdrop-blur-md shadow-inner shadow-black/20">
          <table className="w-full text-left border-separate border-spacing-0 text-xs">
            <thead className="sticky top-0 z-10">
              <tr className="bg-[#111310]/90 dark:bg-[#111310]/90 bg-white/60 backdrop-blur-md">
                {['Symbol', 'Qty', 'Avg', 'Price', 'Value', 'P/L'].map((h, i) => (
                  <th key={h} className={cn(
                    'border-b border-white/10 py-2.5 px-3 text-[9px] uppercase tracking-widest text-muted-foreground/80 font-mono font-semibold whitespace-nowrap',
                    i === 0 ? 'text-left' : 'text-right',
                  )}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="font-mono">
              {holdings.map(h => (
                <tr key={h.symbol} className="group transition-colors hover:bg-white/[0.05]">
                  <td className="border-b border-white/5 py-2.5 px-3 font-bold text-foreground whitespace-nowrap">
                    <span className="flex items-center gap-1.5">
                      <span className="h-1.5 w-1.5 rounded-full shrink-0" style={{ background: fund?.accent ?? '#34d399' }} />
                      {h.symbol}
                      <span className="rounded border border-border/30 bg-accent/30 px-1 text-[8px] font-semibold text-muted-foreground">{h.currency}</span>
                    </span>
                  </td>
                  <td className="border-b border-white/5 py-2.5 px-3 text-right text-muted-foreground tabular-nums whitespace-nowrap">{h.quantity.toLocaleString()}</td>
                  <td className="border-b border-white/5 py-2.5 px-3 text-right text-muted-foreground tabular-nums whitespace-nowrap">{h.avgCost.toFixed(2)}</td>
                  <td className="border-b border-white/5 py-2.5 px-3 text-right text-foreground tabular-nums whitespace-nowrap">{h.currentPrice ? h.currentPrice.toFixed(2) : '—'}</td>
                  <td className="border-b border-white/5 py-2.5 px-3 text-right text-foreground font-bold tabular-nums whitespace-nowrap">{fmtK(h.valueUsd)}</td>
                  <td className={cn('border-b border-white/5 py-2.5 px-3 text-right font-bold tabular-nums whitespace-nowrap',
                    toneClass(h.unrealizedPnLUsd))}>
                    {h.unrealizedPnLUsd !== 0 ? fmtPct(h.avgCost > 0 ? (h.unrealizedPnLUsd / (h.avgCost * h.quantity)) * 100 : 0) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Transactions ledger ──────────────────────────────────────────────────────

export function LedgerWidget({ fund, data }: WidgetProps) {
  const txs = useMemo(
    () => [...fund.transactions].sort((a, b) => b.date.localeCompare(a.date)).slice(0, 40),
    [fund.transactions],
  );

  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader icon={Layers} title="Transaction Ledger" hint={`${fund.transactions.length} TX`} />
      {txs.length === 0 ? <EmptyNote>No transactions recorded yet.</EmptyNote> : (
        <div className="flex-1 overflow-auto custom-scrollbar rounded-xl border border-white/15 dark:border-white/10 bg-white/[0.04] dark:bg-white/[0.04] backdrop-blur-md shadow-inner shadow-black/20">
          <table className="w-full text-left border-separate border-spacing-0 text-xs">
            <thead className="sticky top-0 z-10">
              <tr className="bg-[#111310]/90 dark:bg-[#111310]/90 bg-white/60 backdrop-blur-md">
                {['Date', 'Type', 'Symbol', 'Qty', 'Price', 'Fee'].map((h, i) => (
                  <th key={h} className={cn(
                    'border-b border-white/10 py-2.5 px-3 text-[9px] uppercase tracking-widest text-muted-foreground/80 font-mono font-semibold whitespace-nowrap',
                    i < 3 ? 'text-left' : 'text-right',
                  )}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="font-mono">
              {txs.map(t => (
                <tr key={t.id} className="transition-colors hover:bg-white/[0.05]">
                  <td className="border-b border-white/5 py-2.5 px-3 text-muted-foreground tabular-nums whitespace-nowrap">{t.date}</td>
                  <td className="border-b border-white/5 py-2.5 px-3 whitespace-nowrap">
                    <span className={cn('rounded-md border px-1.5 py-0.5 text-[9px] font-bold tracking-wide',
                      t.type === 'BUY' ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-400'
                        : t.type === 'SELL' ? 'border-rose-500/25 bg-rose-500/10 text-rose-400'
                          : t.type === 'DIVIDEND' ? 'border-amber-500/25 bg-amber-500/10 text-amber-400'
                            : 'border-sky-500/25 bg-sky-500/10 text-sky-400')}>
                      {t.type}
                    </span>
                  </td>
                  <td className="border-b border-white/5 py-2.5 px-3 font-bold text-foreground whitespace-nowrap">{t.symbol}</td>
                  <td className="border-b border-white/5 py-2.5 px-3 text-right text-muted-foreground tabular-nums whitespace-nowrap">{t.quantity.toLocaleString()}</td>
                  <td className="border-b border-white/5 py-2.5 px-3 text-right text-foreground tabular-nums whitespace-nowrap">{t.price.toLocaleString()}</td>
                  <td className="border-b border-white/5 py-2.5 px-3 text-right text-muted-foreground tabular-nums whitespace-nowrap">{t.fee ? t.fee.toFixed(2) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-2 font-mono text-[9px] text-muted-foreground/60">Cash position: {fmtUsd(data.cash)}</p>
    </div>
  );
}

// ── Risk metrics ─────────────────────────────────────────────────────────────

export function RiskWidget({ data }: WidgetProps) {
  const r = data.risk;
  const ld = data.loading && !data.ready;
  const metrics: Array<{ label: string; value: string; tone?: string }> = [
    { label: 'Beta vs SPY', value: r.beta != null ? r.beta.toFixed(2) : '—' },
    { label: 'Ann. Volatility', value: r.vol != null ? `${r.vol.toFixed(1)}%` : '—' },
    { label: 'Sharpe', value: r.sharpe != null ? r.sharpe.toFixed(2) : '—' },
    { label: 'Max Drawdown', value: r.mdd != null ? `${r.mdd.toFixed(1)}%` : '—', tone: r.mdd != null ? DOWN : undefined },
  ];
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader icon={Activity} title="Risk Metrics" hint="3MO DAILY" />
      <div className="grid flex-1 auto-rows-fr grid-cols-2 gap-2.5 lg:grid-cols-4">
        {metrics.map(m => <Tile key={m.label} label={m.label} value={m.value} tone={m.tone} loading={ld} />)}
      </div>
      {r.vol == null && <EmptyNote>Not enough price history to compute risk yet.</EmptyNote>}
    </div>
  );
}

// ── Portfolio health ─────────────────────────────────────────────────────────

export function HealthWidget({ data }: WidgetProps) {
  const health = data.health;
  const primary = useMemo(() => cssVarToHex('--primary', '#34d399'), []);
  const ref = useEChart(() => {
    if (!health) return null;
    const value = Math.round(health.total);
    return {
      ...baseChartOption(),
      series: [{
        type: 'gauge', startAngle: 210, endAngle: -30, min: 0, max: 100,
        progress: { show: true, width: 10, itemStyle: { color: primary } },
        axisLine: { lineStyle: { width: 10, color: [[1, 'rgba(148,163,184,0.15)']] } },
        axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false },
        pointer: { show: false }, anchor: { show: false },
        detail: { valueAnimation: false, offsetCenter: [0, '5%'], formatter: '{value}', color: '#e5e7eb', fontSize: 22, fontFamily: 'monospace' },
        data: [{ value }],
      }],
    };
  }, [health, primary]);

  if (!health) {
    return (
      <div className="flex h-full flex-col p-4">
        <WidgetHeader icon={HeartPulse} title="Portfolio Health" />
        <EmptyNote>Add holdings to score portfolio health.</EmptyNote>
      </div>
    );
  }

  const rows: Array<[string, number | null]> = [
    ['Diversification', health.breakdown.diversification],
    ['Risk', health.breakdown.risk],
    ['Momentum', health.breakdown.momentum],
    ['Concentration', health.breakdown.concentration],
    ['Valuation', health.breakdown.valuation],
    ['Quality', health.breakdown.quality],
  ];

  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader icon={HeartPulse} title="Portfolio Health" />
      <div ref={ref} className="min-h-[120px] flex-1" />
      <div className="grid shrink-0 grid-cols-2 content-start gap-x-4 gap-y-1.5 mt-1">
        {rows.map(([label, v]) => (
          <div key={label} className="flex items-center gap-2 text-[10px]">
            <span className="w-20 shrink-0 text-muted-foreground font-semibold">{label}</span>
            {v == null
              ? <span className="font-mono text-muted-foreground/50">n/a</span>
              : <>
                  <div className="flex-1 h-1 rounded-full bg-border/40 overflow-hidden">
                    <div className={cn('h-full rounded-full', v >= 60 ? 'bg-emerald-400' : v >= 35 ? 'bg-amber-400' : 'bg-rose-400')} style={{ width: `${v}%` }} />
                  </div>
                  <span className="font-mono w-6 text-right text-foreground">{Math.round(v)}</span>
                </>}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Monte Carlo projection ───────────────────────────────────────────────────

export function MonteCarloWidget({ data }: WidgetProps) {
  const [years, setYears] = useState(5);
  const [monthly, setMonthly] = useState(250);
  const vol = data.risk.vol ?? 40;
  const result = useMemo(
    () => data.stats.totalValue > 0
      ? computeMonteCarlo({ totalValue: data.stats.totalValue, vol, years, monthly })
      : null,
    [data.stats.totalValue, vol, years, monthly],
  );
  const colors = useMemo(() => ({
    primary: cssVarToHex('--primary', '#34d399'),
    amber: '#fbbf24', rose: '#fb7185',
  }), []);

  const ref = useEChart(() => {
    if (!result) return null;
    return {
      ...baseChartOption(),
      grid: { left: 8, right: 8, top: 10, bottom: 0, containLabel: true },
      xAxis: { type: 'category', data: result.months.map(m => `${m}m`), axisLabel: { color: '#94a3b8', fontSize: 9, interval: Math.floor(result.months.length / 6) } },
      yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: 'rgba(148,163,184,0.12)' } }, axisLabel: { color: '#94a3b8', fontSize: 9, formatter: (v: number) => fmtK(v) } },
      series: [
        { name: 'P95', type: 'line', data: result.p95, showSymbol: false, lineStyle: { width: 1, color: colors.primary }, areaStyle: { color: colors.primary, opacity: 0.12 }, stack: 'band' },
        { name: 'P50', type: 'line', data: result.p50, showSymbol: false, lineStyle: { width: 2, color: colors.primary } },
        { name: 'P05', type: 'line', data: result.p05, showSymbol: false, lineStyle: { width: 1, color: colors.rose } },
      ],
      legend: { bottom: 0, textStyle: { color: '#94a3b8', fontSize: 9 }, itemWidth: 12 },
    };
  }, [result, colors]);

  const inputCls = 'w-full bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl px-2.5 py-1.5 text-xs font-mono focus:ring-1 focus:ring-primary outline-none';

  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader icon={Gauge} title="Monte Carlo Projection" hint="GBM P05/P50/P95" />
      {result ? <>
        <div className="grid grid-cols-3 gap-2 mb-2">
          <label className="flex flex-col gap-1 text-[9px] uppercase tracking-widest font-bold text-muted-foreground">
            Years
            <input type="number" min={1} max={30} value={years} onChange={e => setYears(Math.max(1, Math.min(30, Number(e.target.value) || 1)))} className={inputCls} />
          </label>
          <label className="flex flex-col gap-1 text-[9px] uppercase tracking-widest font-bold text-muted-foreground">
            Monthly $
            <input type="number" min={0} step={50} value={monthly} onChange={e => setMonthly(Math.max(0, Number(e.target.value) || 0))} className={inputCls} />
          </label>
          <label className="flex flex-col gap-1 text-[9px] uppercase tracking-widest font-bold text-muted-foreground">
            Vol (from risk)
            <div className={cn(inputCls, 'opacity-60')}>{vol.toFixed(0)}%</div>
          </label>
        </div>
        <div ref={ref} className="min-h-[140px] flex-1" />
        <p className="mt-2 shrink-0 font-mono text-[10px] text-muted-foreground">
          {years}y range: <span className={DOWN}>{fmtK(result.end.lo)}</span> → <span className="text-foreground">{fmtK(result.end.mid)}</span> → <span className={UP}>{fmtK(result.end.hi)}</span>
        </p>
      </> : <EmptyNote>Add holdings to project outcomes.</EmptyNote>}
    </div>
  );
}

// ── AI insights (brief + change feed from the analysis engine) ───────────────

export function InsightsWidget({ data }: WidgetProps) {
  const hasContent = data.brief.length > 0 || data.changes.length > 0;
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader icon={Brain} title="AI Insights" hint="ENGINE BRIEF" />
      {!hasContent ? <EmptyNote>Insights appear once the fund holds positions.</EmptyNote> : (
        <div className="flex-1 overflow-y-auto scrollbar-hide flex flex-col gap-2">
          {data.brief.map((line, i) => (
            <p key={`b${i}`} className="text-xs text-muted-foreground leading-relaxed border-l-2 border-primary/30 pl-2.5">{line}</p>
          ))}
          {data.changes.map(c => (
            <p key={c.id} className={cn(
              'text-xs leading-relaxed rounded-xl border px-2.5 py-2',
              c.severity === 'positive' ? 'border-emerald-500/10 bg-emerald-500/5 text-emerald-400'
                : c.severity === 'negative' ? 'border-rose-500/10 bg-rose-500/5 text-rose-400'
                  : 'border-border/20 bg-accent/20 text-muted-foreground',
            )}>{c.text}</p>
          ))}
          {data.attribution.length > 0 && (
            <div className="mt-1">
              <p className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground mb-1.5">Top P/L contributors</p>
              {data.attribution.slice(0, 3).map(a => (
                <div key={a.symbol} className="flex items-center justify-between font-mono text-[11px] py-0.5">
                  <span className="font-bold text-foreground">{a.symbol}</span>
                  <span className={toneClass(a.dollar)}>{fmtUsd(a.dollar)} · {a.pts.toFixed(1)} pts</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Rebalancing suggestions (drift vs equal-weight target) ───────────────────

export function RebalanceWidget({ data }: WidgetProps) {
  const holdings = data.stats.holdings;
  if (holdings.length === 0) {
    return (
      <div className="flex h-full flex-col p-4">
        <WidgetHeader icon={Layers} title="Rebalancing Suggestions" />
        <EmptyNote>Add holdings to compute allocation drift.</EmptyNote>
      </div>
    );
  }
  const target = 100 / holdings.length;
  const rows = holdings
    .map(h => ({ symbol: h.symbol, cur: h.allocation, drift: h.allocation - target, value: h.valueUsd }))
    .sort((a, b) => Math.abs(b.drift) - Math.abs(a.drift));

  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader icon={Layers} title="Rebalancing Suggestions" hint="DRIFT vs EQUAL WEIGHT" />
      <div className="grid flex-1 auto-rows-fr grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
        {rows.map(r => {
          const dollar = (Math.abs(r.drift) / 100) * data.stats.totalValue;
          const quiet = Math.abs(r.drift) < 1.5;
          return (
            <div key={r.symbol} className="flex min-h-0 flex-col justify-center rounded-xl border border-border/20 bg-accent/20 px-3 py-2.5 min-w-0">
              <div className="flex items-baseline justify-between gap-2 mb-1.5">
                <span className="font-mono text-xs font-bold text-foreground">{r.symbol}</span>
                <span className={cn('text-[10px] font-bold', quiet ? 'text-muted-foreground' : r.drift > 0 ? 'text-rose-400' : 'text-emerald-400')}>
                  {quiet ? 'Hold' : r.drift > 0 ? `Trim ${fmtK(dollar)}` : `Add ${fmtK(dollar)}`}
                </span>
              </div>
              <div className="flex gap-3 flex-wrap font-mono text-[10px] text-muted-foreground">
                <span>Now {r.cur.toFixed(1)}%</span>
                <span>Target {target.toFixed(1)}%</span>
                <span className={cn('font-bold', quiet ? 'text-muted-foreground' : r.drift > 0 ? 'text-rose-400' : 'text-emerald-400')}>
                  {r.drift >= 0 ? '+' : ''}{r.drift.toFixed(1)} pts
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Registry ─────────────────────────────────────────────────────────────────

export const FUND_WIDGETS: WorkspaceWidgetMeta[] = [
  { widgetId: 'kpi-board', label: 'Key Metrics', desc: 'Value, unrealized P/L, cash, holdings count.' },
  { widgetId: 'performance', label: 'Performance', desc: 'Fund NAV vs SPY benchmark (indexed).' },
  { widgetId: 'allocation', label: 'Allocation', desc: 'Donut + per-symbol weights.' },
  { widgetId: 'holdings', label: 'Holdings', desc: 'Open positions with cost basis and P/L.' },
  { widgetId: 'rebalance', label: 'Rebalancing', desc: 'Drift vs target weights with trim/add actions.' },
  { widgetId: 'ledger', label: 'Transactions', desc: 'Full transaction ledger + cash.' },
  { widgetId: 'risk-metrics', label: 'Risk Metrics', desc: 'Beta, volatility, Sharpe, drawdown.' },
  { widgetId: 'health', label: 'Portfolio Health', desc: 'Gauge + transparent sub-scores.' },
  { widgetId: 'monte-carlo', label: 'Monte Carlo', desc: 'Projected outcome bands with contributions.' },
  { widgetId: 'ai-insights', label: 'AI Insights', desc: 'Engine brief, change feed, attribution.' },
];

export const FUND_WIDGET_IDS = FUND_WIDGETS.map(w => w.widgetId);

export function renderFundWidget(widgetId: string, props: WidgetProps): React.ReactNode {
  switch (widgetId) {
    case 'kpi-board': return <KpiBoardWidget {...props} />;
    case 'performance': return <PerformanceWidget {...props} />;
    case 'allocation': return <AllocationWidget {...props} />;
    case 'holdings': return <HoldingsWidget {...props} />;
    case 'rebalance': return <RebalanceWidget {...props} />;
    case 'ledger': return <LedgerWidget {...props} />;
    case 'risk-metrics': return <RiskWidget {...props} />;
    case 'health': return <HealthWidget {...props} />;
    case 'monte-carlo': return <MonteCarloWidget {...props} />;
    case 'ai-insights': return <InsightsWidget {...props} />;
    default: return <div className="p-4 text-xs text-muted-foreground">Unknown widget: {widgetId}</div>;
  }
}

/**
 * Clean default arrangement — mirrors the classic analytics-hub layout:
 * tight rows, no dead space. KPI strip → Performance (wide) + Allocation →
 * Holdings (wide) + AI Insights → Risk + Ledger → Monte Carlo + Health.
 */
export function defaultFundLayout(): WorkspaceLayout {
  const id = (widgetId: string) => FUND_WIDGET_IDS.includes(widgetId) ? widgetId : null;
  const col = (ids: string[], weight: number) => ({
    id: `col-${ids.join('-')}-${Math.random().toString(36).slice(2, 6)}`,
    weight,
    widgets: ids.map(widgetId => ({ id: `wid-${widgetId}-${Math.random().toString(36).slice(2, 6)}`, widgetId, height: null as number | null })),
  });
  const sec = (cols: { id: string; weight: number; widgets: { id: string; widgetId: string; height: number | null }[] }[]) =>
    ({ id: `sec-${Math.random().toString(36).slice(2, 6)}`, columns: cols });

  const layout: WorkspaceLayout = {
    version: 1,
    sections: [
      sec([col([id('kpi-board')].filter(Boolean) as string[], 3)]),
      sec([col([id('performance')].filter(Boolean) as string[], 2), col([id('allocation')].filter(Boolean) as string[], 1)]),
      sec([col([id('holdings')].filter(Boolean) as string[], 2), col([id('ai-insights')].filter(Boolean) as string[], 1)]),
      sec([col([id('rebalance')].filter(Boolean) as string[], 3)]),
      sec([col([id('risk-metrics')].filter(Boolean) as string[], 1), col([id('ledger')].filter(Boolean) as string[], 2)]),
      sec([col([id('monte-carlo')].filter(Boolean) as string[], 1), col([id('health')].filter(Boolean) as string[], 2)]),
    ],
  };
  const normalized = normalizeLayout(layout, new Set(FUND_WIDGET_IDS));
  return normalized ?? layout;
}

