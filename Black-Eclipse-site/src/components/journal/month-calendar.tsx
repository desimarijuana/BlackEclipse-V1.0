'use client';

// ── Month Calendar — a proper date grid showing the trades taken each day ────
// Traditional month view: weekday header, day cells with the date number and
// the trades taken that day (symbol + R). Clicking a day opens its journal.

import React, { useMemo } from 'react';
import { cn } from '@/lib/utils';
import type { TradeRecord } from '@/lib/journal/types';
import { fmtR } from './charts/echarts-container';

interface MonthCalendarProps {
  trades: TradeRecord[];
  year: number;
  month: number; // 0-indexed
  onSelectDay: (date: string) => void;
}

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export function MonthCalendar({ trades, year, month, onSelectDay }: MonthCalendarProps) {
  // Group trades by day (YYYY-MM-DD).
  const byDay = useMemo(() => {
    const map = new Map<string, TradeRecord[]>();
    for (const t of trades) {
      const day = t.exitTime.slice(0, 10);
      const arr = map.get(day) ?? [];
      arr.push(t);
      map.set(day, arr);
    }
    return map;
  }, [trades]);

  // Build the grid: leading blanks for the first weekday, then days 1..N.
  const cells = useMemo(() => {
    const first = new Date(Date.UTC(year, month, 1));
    const daysInMonth = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
    const leading = (first.getUTCDay() + 6) % 7; // Mon=0
    const out: (number | null)[] = [];
    for (let i = 0; i < leading; i++) out.push(null);
    for (let d = 1; d <= daysInMonth; d++) out.push(d);
    return out;
  }, [year, month]);

  const iso = (day: number) => `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
  const todayKey = new Date().toISOString().slice(0, 10);

  return (
    <div>
      {/* Weekday header */}
      <div className="grid grid-cols-7 gap-1.5 mb-2">
        {WEEKDAYS.map((d) => (
          <div key={d} className="text-center font-mono text-[10px] font-bold uppercase tracking-widest text-muted-foreground/60">
            {d}
          </div>
        ))}
      </div>

      {/* Day grid */}
      <div className="grid grid-cols-7 gap-1.5">
        {cells.map((day, i) => {
          if (day === null) return <div key={`blank-${i}`} className="min-h-[96px] rounded-xl border border-transparent" />;
          const dateKey = iso(day);
          const dayTrades = byDay.get(dateKey) ?? [];
          const netR = dayTrades.reduce((s, t) => s + t.rMultiple, 0);
          const hasTrades = dayTrades.length > 0;
          const isToday = dateKey === todayKey;
          const isWeekend = (new Date(Date.UTC(year, month, day)).getUTCDay() === 0 || new Date(Date.UTC(year, month, day)).getUTCDay() === 6);

          return (
            <button
              key={dateKey}
              type="button"
              onClick={() => onSelectDay(dateKey)}
              className={cn(
                'group relative flex min-h-[96px] flex-col rounded-xl border p-1.5 text-left transition-all cursor-pointer',
                hasTrades
                  ? netR >= 0
                    ? 'border-emerald-500/20 bg-emerald-500/[0.06] hover:border-emerald-500/50 hover:bg-emerald-500/[0.12]'
                    : 'border-rose-500/20 bg-rose-500/[0.06] hover:border-rose-500/50 hover:bg-rose-500/[0.12]'
                  : 'border-white/5 bg-white/[0.02] hover:border-white/15 hover:bg-white/[0.05]',
                isToday && 'ring-1 ring-primary/60',
              )}
            >
              {/* Date number */}
              <div className="flex items-center justify-between">
                <span
                  className={cn(
                    'flex h-5 w-5 items-center justify-center rounded-md font-mono text-[11px] font-bold',
                    isToday ? 'bg-primary text-primary-foreground' : hasTrades ? 'text-foreground' : 'text-muted-foreground/50',
                  )}
                >
                  {day}
                </span>
                {hasTrades && (
                  <span className={cn('font-mono text-[9px] font-bold', netR >= 0 ? 'text-emerald-400' : 'text-rose-400')}>
                    {fmtR(netR)}
                  </span>
                )}
              </div>

              {/* Trades taken that day */}
              <div className="mt-1 flex flex-col gap-0.5 overflow-hidden">
                {dayTrades.slice(0, 3).map((t) => (
                  <div
                    key={t.id}
                    className={cn(
                      'flex items-center justify-between gap-1 rounded-md px-1 py-0.5',
                      t.rMultiple >= 0 ? 'bg-emerald-500/10' : 'bg-rose-500/10',
                    )}
                  >
                    <span className="truncate font-mono text-[9px] font-semibold text-foreground">{t.symbol}</span>
                    <span className={cn('shrink-0 font-mono text-[9px] font-bold', t.rMultiple >= 0 ? 'text-emerald-400' : 'text-rose-400')}>
                      {fmtR(t.rMultiple)}
                    </span>
                  </div>
                ))}
                {dayTrades.length > 3 && (
                  <span className="px-1 font-mono text-[8px] text-muted-foreground/60">+{dayTrades.length - 3} more</span>
                )}
              </div>

              {/* Weekend dimming */}
              {isWeekend && !hasTrades && <div className="pointer-events-none absolute inset-0 rounded-xl bg-black/20" />}
            </button>
          );
        })}
      </div>

      {/* Legend */}
      <div className="mt-3 flex items-center gap-4 text-[9px] font-mono text-muted-foreground/70">
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded bg-emerald-500/40" /> Profitable day</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded bg-rose-500/40" /> Losing day</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded border border-white/10 bg-white/[0.02]" /> No trades</span>
        <span className="ml-auto text-muted-foreground/50">Click a day to open its journal</span>
      </div>
    </div>
  );
}
