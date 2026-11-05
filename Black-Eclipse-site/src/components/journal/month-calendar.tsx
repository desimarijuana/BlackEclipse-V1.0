'use client';

// ── Month Calendar — a month grid of daily trading results ──────────────────
// Traditional month view: weekday header, day cells with the date number, the
// day's net R, and the trades taken that day (symbol · R) as plain rows with no
// chip background. A weekly-total column on the right shows which weeks carried
// the trader and which bled. Clicking a day opens its journal.
//
// Cells are tinted by the day's result — a soft brand wash for a green day,
// bearish for a red one, neutral when there were no trades — sitting on a
// slightly darker shell. Styling uses the shared `.cal-cell` recipe (no
// per-cell blur) so it themes with the app.

import React, { useMemo } from 'react';
import { cn } from '@/lib/utils';
import type { TradeRecord } from '@/lib/journal/types';
import { hasRBasis, isRMeasurable } from '@/lib/journal/trade-math';
import { fmtMoney } from '@/lib/journal/format';
import { fmtR } from './charts/echarts-container';

interface MonthCalendarProps {
  trades: TradeRecord[];
  year: number;
  month: number; // 0-indexed
  onSelectDay: (date: string) => void;
}

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const MAX_TRADES = 3;
const WEEK_COL = 'w-[64px]';

// One rule everywhere in the grid: show R only when every trade in the group
// carries a stop-derived R basis; otherwise show the realized P&L, which is
// always truthful. This keeps broker imports (no SL in MT5 deal history) from
// rendering a meaningless "+0.00R".
function groupShowsR(group: TradeRecord[]): boolean {
  return group.length > 0 && group.every(isRMeasurable);
}
function groupValue(group: TradeRecord[]): number {
  return groupShowsR(group)
    ? group.reduce((s, t) => s + t.rMultiple, 0)
    : group.reduce((s, t) => s + t.pnl, 0);
}
function groupLabel(group: TradeRecord[]): string {
  return groupShowsR(group)
    ? fmtR(group.reduce((s, t) => s + t.rMultiple, 0))
    : fmtMoney(group.reduce((s, t) => s + t.pnl, 0));
}
function tradeLabel(t: TradeRecord): string {
  if (t.status === 'open') return 'open';
  return isRMeasurable(t) ? fmtR(t.rMultiple) : fmtMoney(t.pnl);
}

// The day's fill reads profit/loss: a soft brand wash for a green day, bearish
// for a red one, neutral for empty days.
function cellClass(value: number | null): string {
  if (value === null) return 'cal-cell';
  return value >= 0 ? 'cal-cell cal-cell--pos' : 'cal-cell cal-cell--neg';
}

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

  // Build the grid as 7-day rows, padding leading/trailing blanks so each row
  // is a complete Mon–Sun week. Keeping full weeks lets us compute a weekly
  // total per row (the column on the right).
  const weeks = useMemo(() => {
    const first = new Date(Date.UTC(year, month, 1));
    const daysInMonth = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
    const leading = (first.getUTCDay() + 6) % 7; // Mon=0
    const cells: (number | null)[] = [];
    for (let i = 0; i < leading; i++) cells.push(null);
    for (let d = 1; d <= daysInMonth; d++) cells.push(d);
    while (cells.length % 7 !== 0) cells.push(null);

    const rows: (number | null)[][] = [];
    for (let i = 0; i < cells.length; i += 7) rows.push(cells.slice(i, i + 7));
    return rows;
  }, [year, month]);

  const iso = (day: number) => `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
  const isoOf = (day: number | null) => (day === null ? null : iso(day));
  const todayKey = new Date().toISOString().slice(0, 10);

  const monthTrades = useMemo(
    () => trades.filter((t) => t.exitTime.startsWith(`${year}-${String(month + 1).padStart(2, '0')}`)),
    [trades, year, month],
  );

  return (
    <div className="cal-shell rounded-2xl p-2.5 sm:p-3">
      {/* Horizontal scroll on narrow screens keeps the 7 day columns legible. */}
      <div className="overflow-x-auto scrollbar-hide">
      <div className="min-w-[560px] sm:min-w-0">
      {/* Weekday header */}
      <div className="mb-2 grid grid-cols-[repeat(7,minmax(0,1fr))_auto] gap-1.5">
        {WEEKDAYS.map((d) => (
          <div key={d} className="text-center font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground/45">
            {d}
          </div>
        ))}
        <div className={cn('text-center font-mono text-[9px] font-semibold uppercase tracking-[0.16em] text-muted-foreground/35', WEEK_COL)}>
          Wk
        </div>
      </div>

      {/* Week rows */}
      <div className="flex flex-col gap-1.5">
        {weeks.map((week, wi) => {
          const weekDays = week.filter((d): d is number => d !== null).map(isoOf);
          const weekTrades = weekDays.flatMap((k) => (k ? byDay.get(k) ?? [] : []));
          const weekValue = weekTrades.length > 0 ? groupValue(weekTrades) : null;
          const weekHasTrades = weekTrades.length > 0;

          return (
            <div key={wi} className="grid grid-cols-[repeat(7,minmax(0,1fr))_auto] gap-1.5">
              {week.map((day, di) => {
                if (day === null) {
                  return <div key={`blank-${wi}-${di}`} className="min-h-[96px] rounded-xl opacity-0" aria-hidden />;
                }
                const dateKey = iso(day);
                const dayTrades = byDay.get(dateKey) ?? [];
                const hasTrades = dayTrades.length > 0;
                const dayValue = hasTrades ? groupValue(dayTrades) : null;
                const isToday = dateKey === todayKey;
                const dow = new Date(Date.UTC(year, month, day)).getUTCDay();
                const isWeekend = dow === 0 || dow === 6;

                return (
                  <button
                    key={dateKey}
                    type="button"
                    onClick={() => onSelectDay(dateKey)}
                    title={hasTrades
                      ? `${dateKey} · ${dayTrades.length} trade${dayTrades.length > 1 ? 's' : ''} · ${groupLabel(dayTrades)}`
                      : dateKey}
                    className={cn(
                      'group relative flex min-h-[96px] flex-col rounded-xl p-2 text-left',
                      cellClass(dayValue),
                      isWeekend && !hasTrades && 'cal-cell--muted',
                      isToday && 'ring-1 ring-primary/60',
                    )}
                  >
                    {/* Date number + day result */}
                    <div className="flex items-center justify-between">
                      <span
                        className={cn(
                          'flex h-[18px] w-[18px] items-center justify-center rounded-md font-mono text-[10px] font-semibold tabular-nums',
                          isToday
                            ? 'bg-primary text-primary-foreground'
                            : hasTrades ? 'text-foreground/75' : 'text-muted-foreground/40',
                        )}
                      >
                        {day}
                      </span>
                      {hasTrades && dayValue !== null && (
                        <span className={cn('font-mono text-[10px] font-semibold tabular-nums', dayValue >= 0 ? 'text-emerald-400' : 'text-rose-400')}>
                          {groupLabel(dayTrades)}
                        </span>
                      )}
                    </div>

                    {/* Trades taken that day — plain symbol · result rows, no chip bg */}
                    {hasTrades && (
                      <div className="mt-1.5 flex flex-col gap-[2px] overflow-hidden">
                        {dayTrades.slice(0, MAX_TRADES).map((t) => (
                          <div key={t.id} className="flex items-center justify-between gap-1 leading-tight">
                            <span className="truncate font-mono text-[9px] text-foreground/65">{t.symbol}</span>
                            <span className={cn('shrink-0 font-mono text-[9px] font-semibold tabular-nums', (hasRBasis(t) ? t.rMultiple : t.pnl) >= 0 ? 'text-emerald-400/90' : 'text-rose-400/90')}>
                              {tradeLabel(t)}
                            </span>
                          </div>
                        ))}
                        {dayTrades.length > MAX_TRADES && (
                          <span className="font-mono text-[8px] text-muted-foreground/50">
                            +{dayTrades.length - MAX_TRADES} more
                          </span>
                        )}
                      </div>
                    )}
                  </button>
                );
              })}

              {/* Weekly total column */}
              <div
                className={cn(
                  'flex flex-col items-center justify-center rounded-xl px-1 text-center',
                  WEEK_COL,
                  weekValue !== null
                    ? weekValue >= 0
                      ? 'cal-cell cal-cell--pos'
                      : 'cal-cell cal-cell--neg'
                    : 'cal-cell cal-cell--muted',
                )}
                title={weekHasTrades ? `${weekTrades.length} trades this week · ${groupLabel(weekTrades)}` : 'No trades this week'}
              >
                <span className="font-mono text-[8px] uppercase tracking-[0.16em] text-muted-foreground/45">W{wi + 1}</span>
                <span className={cn('font-mono text-[11px] font-semibold tabular-nums', weekHasTrades && weekValue !== null ? (weekValue >= 0 ? 'text-emerald-400' : 'text-rose-400') : 'text-muted-foreground/35')}>
                  {weekHasTrades ? groupLabel(weekTrades) : '—'}
                </span>
                {weekHasTrades && (
                  <span className="font-mono text-[8px] text-muted-foreground/45">{weekTrades.length}t</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
      </div>
      </div>

      {/* Legend + month total */}
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 font-mono text-[9px] text-muted-foreground/60">
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-emerald-500/60" /> Profit</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-rose-500/60" /> Loss</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full border border-white/10 bg-white/[0.03]" /> No trades</span>
        <span className="ml-auto text-muted-foreground/45">
          Click a day to open its journal
        </span>
        <span className={cn('font-semibold tabular-nums', groupValue(monthTrades) >= 0 ? 'text-emerald-400' : 'text-rose-400')}>
          Month {monthTrades.length > 0 ? groupLabel(monthTrades) : '—'}
        </span>
      </div>
    </div>
  );
}
