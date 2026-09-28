'use client';

// ── Month calendar card — month grid with its own month navigation ───────────
// A compact, read-only month view for embedding outside the Calendar tab (the
// Overview uses it). The Calendar tab keeps its own richer header with
// Add-trade / CSV import; this is just the grid plus prev/next.

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { MonthCalendar } from './month-calendar';
import { formatMonthLabel } from '@/lib/journal/dates';
import type { TradeRecord } from '@/lib/journal/types';
import { fmtR, fmtMoney } from './charts/echarts-container';

interface MonthCalendarCardProps {
  trades: TradeRecord[];
  onSelectDay: (date: string) => void;
}

export function MonthCalendarCard({ trades, onSelectDay }: MonthCalendarCardProps) {
  // Open on the month of the MOST RECENT trade (its UTC `exitTime`), not the
  // browser's local clock: dates are stored and sliced as UTC throughout the
  // engine, and a local clock can be a month off — which opened on an empty
  // month. Falling back to today keeps this sane on an empty journal.
  const initialMonth = useMemo(() => {
    const latest = trades.reduce<string | null>(
      (best, t) => (best === null || t.exitTime > best ? t.exitTime : best),
      null,
    );
    const key = latest?.slice(0, 7) ?? null;
    const now = new Date();
    if (!key) return { year: now.getUTCFullYear(), month: now.getUTCMonth() };
    return { year: Number(key.slice(0, 4)), month: Number(key.slice(5, 7)) - 1 };
  }, [trades]);

  const [year, setYear] = useState(initialMonth.year);
  const [month, setMonth] = useState(initialMonth.month);
  // The card mounts before the trades arrive (the shell fetches them), so the
  // `useState` initialiser above runs on an empty list. Jump to the latest trade
  // month the first time data lands — but only if the user hasn't navigated yet,
  // so we never yank them out of a month they chose.
  const [navigated, setNavigated] = useState(false);
  const firstDataMonth = useRef<string | null>(null);
  useEffect(() => {
    if (navigated || trades.length === 0) return;
    const key = `${initialMonth.year}-${initialMonth.month}`;
    if (firstDataMonth.current === key) return;
    firstDataMonth.current = key;
    setYear(initialMonth.year);
    setMonth(initialMonth.month);
  }, [trades.length, initialMonth, navigated]);

  const monthLabel = useMemo(() => formatMonthLabel(year, month), [year, month]);

  const stats = useMemo(() => {
    const prefix = `${year}-${String(month + 1).padStart(2, '0')}`;
    const monthTrades = trades.filter((t) => t.exitTime.startsWith(prefix));
    return {
      count: monthTrades.length,
      netR: monthTrades.reduce((s, t) => s + t.rMultiple, 0),
      netPnl: monthTrades.reduce((s, t) => s + t.pnl, 0),
      days: new Set(monthTrades.map((t) => t.exitTime.slice(0, 10))).size,
    };
  }, [trades, year, month]);

  const goPrev = () => {
    setNavigated(true);
    if (month === 0) { setMonth(11); setYear((y) => y - 1); } else setMonth((m) => m - 1);
  };
  const goNext = () => {
    setNavigated(true);
    if (month === 11) { setMonth(0); setYear((y) => y + 1); } else setMonth((m) => m + 1);
  };

  return (
    <div className="flex flex-col p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-border/10 pb-2.5">
        <div className="flex items-center gap-2 min-w-0">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/10">
            <CalendarDays size={13} className="text-primary" />
          </span>
          <h3 className="font-serif text-sm font-semibold text-foreground truncate">Monthly Calendar</h3>
        </div>
        <div className="flex items-center gap-2">
          <div className="hidden items-center gap-2 sm:flex">
            <span className="rounded-lg border border-white/5 bg-white/[0.03] px-2 py-1 font-mono text-[10px] text-muted-foreground/80">
              {stats.count} trades · {stats.days}d
            </span>
            <span className={cn(
              'rounded-lg px-2 py-1 font-mono text-[10px] font-bold tabular-nums',
              stats.netR >= 0 ? 'cal-cell--pos' : 'cal-cell--neg',
            )}>
              {fmtR(stats.netR)}
            </span>
            <span className={cn(
              'rounded-lg px-2 py-1 font-mono text-[10px] font-bold tabular-nums',
              stats.netPnl >= 0 ? 'cal-cell--pos' : 'cal-cell--neg',
            )}>
              {fmtMoney(stats.netPnl)}
            </span>
          </div>
          <div className="flex items-center gap-0.5 rounded-xl glass-card-subtle p-0.5">
            <button
              onClick={goPrev}
              aria-label="Previous month"
              className="rounded-lg p-1 text-muted-foreground transition-all hover:bg-accent/40 hover:text-primary cursor-pointer"
            >
              <ChevronLeft size={13} />
            </button>
            <span className="min-w-[104px] text-center font-mono text-[10px] font-bold text-foreground">{monthLabel}</span>
            <button
              onClick={goNext}
              aria-label="Next month"
              className="rounded-lg p-1 text-muted-foreground transition-all hover:bg-accent/40 hover:text-primary cursor-pointer"
            >
              <ChevronRight size={13} />
            </button>
          </div>
        </div>
      </div>
      <MonthCalendar trades={trades} year={year} month={month} onSelectDay={onSelectDay} />
    </div>
  );
}
