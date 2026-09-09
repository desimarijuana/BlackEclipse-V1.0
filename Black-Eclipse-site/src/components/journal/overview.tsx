'use client';

// ── Journal Overview — "How am I trading?" ───────────────────────────────────
// KPI strip + equity curve + best/worst dimensions + recent trades + insights.

import React, { useMemo } from 'react';
import { ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { JournalAnalytics, TradeRecord } from '@/lib/journal/types';
import { EquityCurveChart, DimensionBarChart, WinLossChart, fmtR, fmtMoney } from './charts';

interface OverviewProps {
  analytics: JournalAnalytics | null;
  trades: TradeRecord[];
  onOpenTrades: () => void;
}

export function JournalOverview({ analytics, trades, onOpenTrades }: OverviewProps) {
  const p = analytics?.performance;
  const recent = useMemo(() => [...trades].sort((a, b) => Date.parse(b.exitTime) - Date.parse(a.exitTime)).slice(0, 8), [trades]);

  if (!analytics || !p) {
    return (
      <div className="rounded-3xl bg-[#0f0f0f]/60 p-12 text-center">
        <p className="text-sm text-muted-foreground">No trades yet. Add your first trade to start building your journal.</p>
        <button onClick={onOpenTrades} className="mt-4 rounded-xl border border-primary/40 bg-primary/15 text-primary px-4 py-2 text-xs font-bold hover:bg-primary/25 transition-all cursor-pointer">
          + Add Trade
        </button>
      </div>
    );
  }

  const kpis: { label: string; value: string; tone?: string; sub?: string }[] = [
    { label: 'Total Trades', value: String(p.totalTrades) },
    { label: 'Win Rate', value: `${(p.winRate * 100).toFixed(1)}%`, sub: `${p.wins}W / ${p.losses}L / ${p.breakevens}B` },
    { label: 'Net P&L', value: fmtMoney(p.netPnl), tone: p.netPnl >= 0 ? 'text-emerald-400' : 'text-rose-400' },
    { label: 'Net R', value: fmtR(p.netR), tone: p.netR >= 0 ? 'text-emerald-400' : 'text-rose-400' },
    { label: 'Expectancy', value: fmtR(p.expectancy), tone: p.expectancy >= 0 ? 'text-emerald-400' : 'text-rose-400' },
    { label: 'Profit Factor', value: p.profitFactor === Infinity ? '∞' : p.profitFactor.toFixed(2) },
    { label: 'Max Drawdown', value: fmtR(-p.maxDrawdown), tone: 'text-rose-400' },
    { label: 'Avg Win / Loss', value: `${fmtMoney(p.averageWin)} / ${fmtMoney(p.averageLoss)}` },
    { label: 'Streak', value: p.currentStreak > 0 ? `${p.currentStreak}W` : p.currentStreak < 0 ? `${-p.currentStreak}L` : '—', tone: p.currentStreak > 0 ? 'text-emerald-400' : p.currentStreak < 0 ? 'text-rose-400' : undefined },
    { label: 'Discipline', value: `${analytics.discipline.total}/100`, sub: `v${analytics.discipline.total >= 80 ? 'strong' : analytics.discipline.total >= 50 ? 'ok' : 'needs work'}` },
  ];

  return (
    <div className="flex flex-col gap-5">
      {/* KPI strip */}
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-5">
        {kpis.map((k) => (
          <div key={k.label} className="rounded-2xl bg-[#0f0f0f]/60 p-3">
            <p className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">{k.label}</p>
            <p className={cn('mt-1 font-mono text-sm font-bold truncate', k.tone ?? 'text-foreground')}>{k.value}</p>
            {k.sub && <p className="font-mono text-[9px] text-muted-foreground/70 truncate">{k.sub}</p>}
          </div>
        ))}
      </div>

      {/* Equity curve + win/loss */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="rounded-2xl bg-[#0f0f0f]/60 p-4 lg:col-span-2">
          <EquityCurveChart equity={analytics.equity} height={260} />
        </div>
        <div className="rounded-2xl bg-[#0f0f0f]/60 p-4">
          <WinLossChart wins={p.wins} losses={p.losses} breakevens={p.breakevens} height={200} />
          <div className="mt-2 grid grid-cols-3 gap-2 text-center">
            <MiniStat label="Wins" value={String(p.wins)} tone="text-emerald-400" />
            <MiniStat label="Losses" value={String(p.losses)} tone="text-rose-400" />
            <MiniStat label="Breakeven" value={String(p.breakevens)} />
          </div>
        </div>
      </div>

      {/* Best / worst dimensions */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="rounded-2xl bg-[#0f0f0f]/60 p-4">
          <DimensionBarChart rows={analytics.bySymbol.slice(0, 6)} title="Best / Worst Symbols" hint="NET R" height={200} />
        </div>
        <div className="rounded-2xl bg-[#0f0f0f]/60 p-4">
          <DimensionBarChart rows={analytics.bySetup.slice(0, 6)} title="Best / Worst Setups" hint="NET R" height={200} />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="rounded-2xl bg-[#0f0f0f]/60 p-4">
          <DimensionBarChart rows={analytics.bySession.slice(0, 6)} title="Best / Worst Sessions" hint="NET R" height={200} />
        </div>
        <div className="rounded-2xl bg-[#0f0f0f]/60 p-4">
          <DisciplinePanel analytics={analytics} />
        </div>
      </div>

      {/* Recent trades */}
      <div className="rounded-2xl bg-[#0f0f0f]/60 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
          <h3 className="font-serif text-sm font-semibold text-foreground">Recent Trades</h3>
          <button onClick={onOpenTrades} className="text-[11px] font-semibold text-primary hover:text-primary/80 cursor-pointer">View all →</button>
        </div>
        {recent.length === 0 ? (
          <p className="p-6 text-center text-xs text-muted-foreground italic">No trades yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="sticky top-0 bg-[#0f0f0f]/95 border-b border-white/10">
                <tr>
                  {['Date', 'Symbol', 'Dir', 'Entry', 'Exit', 'R', 'P&L'].map((h) => (
                    <th key={h} className="px-3 py-2 text-[9px] uppercase tracking-widest text-muted-foreground font-bold">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {recent.map((t) => (
                  <tr key={t.id} className="border-b border-white/5 last:border-0 hover:bg-white/[0.03]">
                    <td className="px-3 py-2 text-muted-foreground">{t.exitTime.slice(0, 10)}</td>
                    <td className="px-3 py-2 font-bold text-foreground">{t.symbol}</td>
                    <td className="px-3 py-2">{t.direction === 'LONG' ? <span className="text-emerald-400">LONG</span> : <span className="text-rose-400">SHORT</span>}</td>
                    <td className="px-3 py-2 text-muted-foreground">{t.entry}</td>
                    <td className="px-3 py-2 text-muted-foreground">{t.exit}</td>
                    <td className={cn('px-3 py-2 font-bold', t.rMultiple >= 0 ? 'text-emerald-400' : 'text-rose-400')}>{fmtR(t.rMultiple)}</td>
                    <td className={cn('px-3 py-2 font-bold', t.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400')}>{fmtMoney(t.pnl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function MiniStat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-xl bg-white/[0.03] border border-white/5 p-2">
      <p className="text-[8px] uppercase tracking-widest text-muted-foreground">{label}</p>
      <p className={cn('font-mono text-sm font-bold', tone ?? 'text-foreground')}>{value}</p>
    </div>
  );
}

function DisciplinePanel({ analytics }: { analytics: JournalAnalytics }) {
  const d = analytics.discipline;
  const rows: { label: string; value: number; max: number }[] = [
    { label: 'Risk', value: d.risk, max: 25 },
    { label: 'Strategy', value: d.strategy, max: 25 },
    { label: 'Stop', value: d.stop, max: 20 },
    { label: 'Overtrading', value: d.overtrading, max: 15 },
    { label: 'Execution', value: d.execution, max: 15 },
  ];
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-serif text-sm font-semibold text-foreground flex items-center gap-2"><ShieldCheck size={14} className="text-primary" /> Discipline Score</h3>
        <span className="font-mono text-2xl font-bold text-primary">{d.total}<span className="text-xs text-muted-foreground">/100</span></span>
      </div>
      <div className="flex flex-col gap-2">
        {rows.map((r) => (
          <div key={r.label} className="flex items-center gap-2 text-[10px]">
            <span className="w-20 shrink-0 text-muted-foreground font-semibold">{r.label}</span>
            <div className="flex-1 h-1.5 rounded-full bg-border/40 overflow-hidden">
              <div className="h-full rounded-full bg-primary" style={{ width: `${(r.value / r.max) * 100}%` }} />
            </div>
            <span className="font-mono w-8 text-right text-foreground">{r.value}/{r.max}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
