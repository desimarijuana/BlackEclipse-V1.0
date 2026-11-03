'use client';

// ── Journal Calendar — proper month-grid calendar showing trades per day ─────

import React, { useMemo, useState, useRef } from 'react';
import { usePageShortcuts } from '@/hooks/use-page-shortcuts';
import { ChevronLeft, ChevronRight, Plus, CalendarRange, Trophy, Percent } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { MonthCalendar } from './month-calendar';
import { QuickAddTrade } from './quick-add-trade';
import { CsvImport } from './csv-import';
import type { TradeRecord } from '@/lib/journal/types';
import { classifyTradeOutcome, hasRBasis } from '@/lib/journal/trade-math';
import { formatMonthLabel } from '@/lib/journal/dates';
import { fmtR, fmtMoney } from './charts/echarts-container';

interface CalendarProps {
  trades: TradeRecord[];
  onSelectDay: (date: string) => void;
  onChanged: () => void;
}

export function JournalCalendar({ trades, onSelectDay, onChanged }: CalendarProps) {
  const now = new Date();
  const [year, setYear] = useState(now.getUTCFullYear());
  const [month, setMonth] = useState(now.getUTCMonth());
  const [adding, setAdding] = useState(false);

  const monthLabel = useMemo(() => formatMonthLabel(year, month), [year, month]);

  // Month summary stats.
  const monthStats = useMemo(() => {
    const prefix = `${year}-${String(month + 1).padStart(2, '0')}`;
    const monthTrades = trades.filter((t) => t.exitTime.startsWith(prefix));
    const netR = monthTrades.reduce((s, t) => s + t.rMultiple, 0);
    const netPnl = monthTrades.reduce((s, t) => s + t.pnl, 0);
    const wins = monthTrades.filter((t) => classifyTradeOutcome(t) === "win").length;
    const winRate = monthTrades.length > 0 ? (wins / monthTrades.length) * 100 : 0;
    const rAvailable = monthTrades.length > 0 && monthTrades.every(hasRBasis);
    const bestR = monthTrades.reduce((m, t) => (hasRBasis(t) ? Math.max(m, t.rMultiple) : m), -Infinity);
    const bestPnl = monthTrades.reduce((m, t) => Math.max(m, t.pnl), -Infinity);
    const tradingDays = new Set(monthTrades.map((t) => t.exitTime.slice(0, 10))).size;
    return {
      count: monthTrades.length, netR, netPnl, winRate, tradingDays, rAvailable,
      bestR: Number.isFinite(bestR) ? bestR : 0,
      bestPnl: Number.isFinite(bestPnl) ? bestPnl : 0,
    };
  }, [trades, year, month]);

  // Daily result series for the sparkline: R when the month has an R basis,
  // otherwise realized P&L — never a flat zero line.
  const dailySpark = useMemo(() => {
    const prefix = `${year}-${String(month + 1).padStart(2, '0')}`;
    const byDay = new Map<string, number>();
    for (const t of trades) {
      if (!t.exitTime.startsWith(prefix)) continue;
      const d = t.exitTime.slice(0, 10);
      byDay.set(d, (byDay.get(d) ?? 0) + (monthStats.rAvailable ? t.rMultiple : t.pnl));
    }
    const daysInMonth = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
    const series: number[] = [];
    for (let d = 1; d <= daysInMonth; d++) {
      const key = `${prefix}-${String(d).padStart(2, '0')}`;
      series.push(byDay.get(key) ?? 0);
    }
    return series;
  }, [trades, year, month, monthStats.rAvailable]);

  const goPrev = () => {
    if (month === 0) { setMonth(11); setYear((y) => y - 1); }
    else setMonth((m) => m - 1);
  };
  const goNext = () => {
    if (month === 11) { setMonth(0); setYear((y) => y + 1); }
    else setMonth((m) => m + 1);
  };
  const goToday = () => {
    const t = new Date();
    setYear(t.getUTCFullYear());
    setMonth(t.getUTCMonth());
  };

  const isCurrentMonth = year === now.getUTCFullYear() && month === now.getUTCMonth();

  const rootRef = useRef<HTMLDivElement>(null);
  const startAdding = () => setAdding(true);
  usePageShortcuts(rootRef, [
    { id: 'calendar.new', label: 'Add trade', keys: 'Shift+N', run: startAdding, enabled: !adding },
  ]);

  return (
    <div ref={rootRef} data-keyboard-scope="Trading calendar" className="flex flex-col gap-5">
      {/* Header + navigation */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/15 shadow-lg shadow-primary/10">
            <CalendarRange className="text-primary" size={22} />
          </span>
          <div className="min-w-0">
            <h2 className="font-serif text-lg font-semibold tracking-tight text-foreground">Trading Calendar</h2>
            <p className="text-xs text-muted-foreground mt-0.5">Click any day to open its journal and review the trades taken.</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1 rounded-xl glass-card-subtle p-1">
            <button onClick={goPrev} aria-label="Previous month" className="rounded-lg p-1.5 text-muted-foreground hover:text-primary hover:bg-accent/40 transition-all cursor-pointer">
              <ChevronLeft size={15} />
            </button>
            <span className="min-w-[140px] text-center font-serif text-sm font-semibold text-foreground">{monthLabel}</span>
            <button onClick={goNext} aria-label="Next month" className="rounded-lg p-1.5 text-muted-foreground hover:text-primary hover:bg-accent/40 transition-all cursor-pointer">
              <ChevronRight size={15} />
            </button>
            {!isCurrentMonth && (
              <button onClick={goToday} className="ml-1 rounded-lg bg-accent/30 px-2.5 py-1 text-[10px] font-semibold text-muted-foreground hover:text-primary transition-all cursor-pointer">
                Today
              </button>
            )}
          </div>
          <CsvImport onImported={onChanged} />
          <button
            onClick={startAdding}
            className="inline-flex items-center gap-1.5 rounded-xl border border-primary/40 bg-primary/15 text-primary px-3 py-1.5 text-xs font-bold hover:bg-primary/25 transition-all cursor-pointer"
          >
            <Plus size={13} /> Add Trade
          </button>
          <QuickAddTrade onAdded={onChanged} open={adding} onOpenChange={setAdding} trigger={false} />
        </div>
      </div>

      {/* Month summary strip */}
      <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
        <MonthStat
          icon={<CalendarRange size={13} />}
          label="Trades"
          value={String(monthStats.count)}
          sub={`${monthStats.tradingDays} trading day${monthStats.tradingDays === 1 ? '' : 's'}`}
        />
        <MonthStat
          icon={<Percent size={13} />}
          label="Win Rate"
          value={monthStats.count > 0 ? `${monthStats.winRate.toFixed(0)}%` : '—'}
          sub={monthStats.count > 0 ? `${Math.round((monthStats.winRate / 100) * monthStats.count)} winners` : 'no trades'}
          accent={
            monthStats.count > 0
              ? monthStats.winRate >= 50 ? 'text-emerald-400' : 'text-rose-400'
              : undefined
          }
          progress={monthStats.count > 0 ? monthStats.winRate / 100 : undefined}
        />
        <MonthStat
          icon={<Trophy size={13} />}
          label={monthStats.rAvailable ? "Net R" : "Net P&L"}
          value={monthStats.rAvailable ? fmtR(monthStats.netR) : fmtMoney(monthStats.netPnl)}
          accent={(monthStats.rAvailable ? monthStats.netR : monthStats.netPnl) >= 0 ? 'text-emerald-400' : 'text-rose-400'}
          sub={
            monthStats.count > 0
              ? monthStats.rAvailable
                ? `best ${fmtR(monthStats.bestR)}`
                : `best ${fmtMoney(monthStats.bestPnl)}`
              : undefined
          }
          spark={dailySpark}
        />
        <MonthStat
          icon={<Trophy size={13} />}
          label="Net P&L"
          value={fmtMoney(monthStats.netPnl)}
          accent={monthStats.netPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}
          sub={monthStats.count > 0 ? `avg ${fmtMoney(monthStats.count ? monthStats.netPnl / monthStats.count : 0)} / trade` : undefined}
        />
      </div>

      {/* Calendar */}
      <div className="rounded-2xl glass-card p-4">
        <MonthCalendar trades={trades} year={year} month={month} onSelectDay={onSelectDay} />
      </div>
    </div>
  );
}

function MonthStat({
  icon, label, value, accent, sub, progress, spark,
}: {
  icon?: React.ReactNode; label: string; value: string; accent?: string;
  sub?: string; progress?: number; spark?: number[];
}) {
  return (
    <div className="relative overflow-hidden rounded-2xl glass-card p-3.5">
      <div className="flex items-center gap-2">
        {icon && <span className="text-muted-foreground/60">{icon}</span>}
        <p className="text-[9px] uppercase tracking-[0.18em] font-bold text-muted-foreground">{label}</p>
      </div>
      <p className={cn('mt-1.5 font-mono text-lg font-bold leading-none tabular-nums', accent ?? 'text-foreground')}>{value}</p>
      {sub && <p className="mt-1 font-mono text-[9px] text-muted-foreground/70 truncate">{sub}</p>}

      {progress != null && (
        <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-border/40">
          <div
            className={cn('h-full rounded-full transition-all', progress >= 0.5 ? 'bg-primary' : 'bg-destructive')}
            style={{ width: `${Math.min(100, Math.max(0, progress * 100))}%` }}
          />
        </div>
      )}

      {spark && spark.some((v) => v !== 0) && (
        <div className="mt-2 flex h-4 items-end gap-[2px]" aria-hidden>
          {spark.map((v, i) => {
            const mag = Math.min(1, Math.abs(v) / 3);
            return (
              <span
                key={i}
                className={cn('min-w-0 flex-1 rounded-sm', v === 0 ? 'bg-border/50' : v > 0 ? 'bg-emerald-500/70' : 'bg-rose-500/70')}
                style={{ height: v === 0 ? '2px' : `${Math.max(3, mag * 16)}px` }}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
