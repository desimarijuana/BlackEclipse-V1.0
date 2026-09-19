'use client';

// ── Journal Calendar — proper month-grid calendar showing trades per day ─────

import React, { useMemo, useState, useRef } from 'react';
import { usePageShortcuts } from '@/hooks/use-page-shortcuts';
import { ChevronLeft, ChevronRight, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { MonthCalendar } from './month-calendar';
import { QuickAddTrade } from './quick-add-trade';
import { CsvImport } from './csv-import';
import type { TradeRecord } from '@/lib/journal/types';
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
    const wins = monthTrades.filter((t) => t.rMultiple > 0).length;
    const winRate = monthTrades.length > 0 ? (wins / monthTrades.length) * 100 : 0;
    const tradingDays = new Set(monthTrades.map((t) => t.exitTime.slice(0, 10))).size;
    return { count: monthTrades.length, netR, netPnl, winRate, tradingDays };
  }, [trades, year, month]);

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
        <div>
          <h2 className="font-serif text-lg font-semibold text-foreground">Trading Calendar</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Click a day to open its journal and see the trades taken.</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 rounded-xl glass-card p-1">
            <button onClick={goPrev} className="rounded-lg p-1.5 text-muted-foreground hover:text-primary hover:bg-accent/40 transition-all cursor-pointer" title="Previous month">
              <ChevronLeft size={15} />
            </button>
            <span className="min-w-[150px] text-center font-serif text-sm font-semibold text-foreground">{monthLabel}</span>
            <button onClick={goNext} className="rounded-lg p-1.5 text-muted-foreground hover:text-primary hover:bg-accent/40 transition-all cursor-pointer" title="Next month">
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
          <QuickAddTrade
            onAdded={onChanged}
            open={adding}
            onOpenChange={setAdding}
            trigger={false}
          />
        </div>
      </div>

      {/* Month summary strip */}
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <MonthStat label="Trades" value={String(monthStats.count)} />
        <MonthStat label="Net R" value={fmtR(monthStats.netR)} tone={monthStats.netR >= 0 ? 'text-emerald-400' : 'text-rose-400'} />
        <MonthStat label="Net P&L" value={fmtMoney(monthStats.netPnl)} tone={monthStats.netPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'} />
        <MonthStat label="Win Rate" value={monthStats.count > 0 ? `${monthStats.winRate.toFixed(0)}%` : '—'} sub={`${monthStats.tradingDays} trading days`} />
      </div>

      {/* Calendar */}
      <div className="rounded-2xl glass-card p-4">
        <MonthCalendar trades={trades} year={year} month={month} onSelectDay={onSelectDay} />
      </div>
    </div>
  );
}

function MonthStat({ label, value, tone, sub }: { label: string; value: string; tone?: string; sub?: string }) {
  return (
    <div className="rounded-2xl glass-card p-3">
      <p className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">{label}</p>
      <p className={cn('mt-1 font-mono text-sm font-bold', tone ?? 'text-foreground')}>{value}</p>
      {sub && <p className="font-mono text-[9px] text-muted-foreground/70">{sub}</p>}
    </div>
  );
}
