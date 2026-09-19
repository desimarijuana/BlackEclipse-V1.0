'use client';

// ── EarningsCalendar — shared month-grid earnings calendar ───────────────────
// Rendered in two places from one implementation:
//   • the Command Center `earnings-calendar` widget (dense), and
//   • the full-page Earnings screen (roomy).
// Data comes from the `earnings:calendar` DataHub topic (Alpha Vantage via the
// server; the key never reaches the browser), with an explicit UNAVAILABLE
// state — rows are never fabricated. Clicking a row opens that symbol's chart.

import React, { useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTopic } from '@/lib/workspace/data-hub';
import { useCommandStore } from '@/lib/search/store';

export interface EarningsRow {
  symbol: string;
  name: string;
  date: string;
  time: 'BMO' | 'AMC' | null;
  epsEstimate: number | null;
  epsActual: number | null;
  currency: string | null;
}
export interface EarningsPayload {
  rows?: EarningsRow[];
  source?: 'alphavantage' | 'nasdaq' | 'unavailable';
  fetchedAt?: string;
  reason?: string;
}

const WEEKDAYS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

/** Local calendar day (YYYY-MM-DD) for a Date, in the viewer's timezone. */
function localDay(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function useEarningsCalendar() {
  const t = useTopic<EarningsPayload>('earnings:calendar');
  const rows = useMemo(() => t.data?.rows ?? [], [t.data]);
  const byDay = useMemo(() => {
    const m = new Map<string, EarningsRow[]>();
    for (const r of rows) {
      if (!r.date) continue;
      const list = m.get(r.date) ?? [];
      list.push(r);
      m.set(r.date, list);
    }
    for (const list of m.values()) list.sort((a, b) => a.symbol.localeCompare(b.symbol));
    return m;
  }, [rows]);
  const loading = t.updatedAt === null;
  const unavailable = !loading && (t.source === 'UNAVAILABLE' || t.data?.source === 'unavailable');
  return { t, rows, byDay, loading, unavailable };
}

function openSymbol(symbol: string) {
  useCommandStore.getState().dispatch({ tab: 'chart', params: { symbol } });
}

/**
 * The month grid + selected-day detail. `dense` is the compact widget layout;
 * the default is the roomy full-page layout.
 */
export function EarningsCalendar({
  dense = false,
  title,
}: {
  dense?: boolean;
  /** Optional heading shown above the month navigation (full-page embed). */
  title?: string;
}) {
  const { t, rows, byDay, loading, unavailable } = useEarningsCalendar();
  const [monthCursor, setMonthCursor] = useState(() => {
    const n = new Date();
    return new Date(n.getFullYear(), n.getMonth(), 1);
  });
  const today = localDay(new Date());
  const [selectedDay, setSelectedDay] = useState<string>(today);

  const weeks = useMemo(() => {
    const first = new Date(monthCursor.getFullYear(), monthCursor.getMonth(), 1);
    const start = new Date(first);
    start.setDate(first.getDate() - first.getDay());
    const cells: { date: string; day: number; inMonth: boolean }[] = [];
    for (let i = 0; i < 42; i++) {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      cells.push({ date: localDay(d), day: d.getDate(), inMonth: d.getMonth() === first.getMonth() });
    }
    const out: typeof cells[] = [];
    for (let i = 0; i < 42; i += 7) out.push(cells.slice(i, i + 7));
    return out;
  }, [monthCursor]);

  const monthLabel = monthCursor.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
  const monthCount = useMemo(
    () => rows.filter(r => r.date.startsWith(`${monthCursor.getFullYear()}-${String(monthCursor.getMonth() + 1).padStart(2, '0')}`)).length,
    [rows, monthCursor],
  );
  const shiftMonth = (delta: number) =>
    setMonthCursor(c => new Date(c.getFullYear(), c.getMonth() + delta, 1));
  const selectedRows = byDay.get(selectedDay) ?? [];

  // Cell sizing differs between the compact widget and the full page.
  const minCell = dense ? 'min-h-[38px]' : 'min-h-[64px]';
  const chipText = dense ? 'text-[6.5px]' : 'text-[9px]';

  return (
    <div className={cn('flex flex-col', dense ? 'h-full p-4' : 'w-full')}>
      {dense ? (
        <div className="flex items-center justify-between gap-2 border-b border-border/10 pb-2.5 mb-3">
          <h3 className="font-serif text-sm font-semibold text-foreground truncate">Earnings Calendar</h3>
          <span className="flex items-center gap-2 shrink-0">
            <span className="font-mono text-[9px] text-muted-foreground/70">
              {loading ? '…' : `${monthCount} in ${monthCursor.toLocaleDateString(undefined, { month: 'short' })}`}
            </span>
          </span>
        </div>
      ) : title ? (
        <h2 className="mb-3 font-serif text-lg font-semibold text-foreground">{title}</h2>
      ) : null}

      {/* Month navigation */}
      <div className="mb-2 flex shrink-0 items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => shiftMonth(-1)}
          className="rounded-lg p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground cursor-pointer"
          title="Previous month"
          aria-label="Previous month"
        ><ChevronLeft size={dense ? 14 : 16} /></button>
        <span className={cn('font-mono font-bold text-foreground', dense ? 'text-[11px]' : 'text-sm')}>{monthLabel}</span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => { const n = new Date(); setMonthCursor(new Date(n.getFullYear(), n.getMonth(), 1)); setSelectedDay(today); }}
            className="rounded-lg px-2 py-1 text-[9px] font-bold uppercase tracking-wide text-muted-foreground transition-colors hover:bg-accent hover:text-primary cursor-pointer"
            title="Jump to today"
          >Today</button>
          <button
            type="button"
            onClick={() => shiftMonth(1)}
            className="rounded-lg p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground cursor-pointer"
            title="Next month"
            aria-label="Next month"
          ><ChevronRight size={dense ? 14 : 16} /></button>
        </div>
      </div>

      {loading ? (
        <div className="flex flex-1 items-center justify-center py-8 text-center">
          <p className="text-xs text-muted-foreground/70 italic">Loading earnings…</p>
        </div>
      ) : unavailable ? (
        <div className="flex flex-1 items-center justify-center py-8 text-center">
          <p className="text-xs text-amber-400/80 italic max-w-[32ch]">
            UNAVAILABLE — {t.data?.reason ?? 'earnings source not reachable.'}
          </p>
        </div>
      ) : (
        <div className={cn(dense ? 'flex min-h-0 flex-1 flex-col' : 'flex flex-col gap-4')}>
          {/* Month grid */}
          <div className={cn('shrink-0 rounded-xl glass-card-subtle', dense ? 'p-1.5' : 'p-3')}>
            <div className="grid grid-cols-7 gap-px">
              {WEEKDAYS.map((w, i) => (
                <span key={i} className={cn('py-0.5 text-center font-bold uppercase tracking-widest text-muted-foreground/60', dense ? 'text-[8px]' : 'text-[10px]')}>{w}</span>
              ))}
            </div>
            <div className="grid grid-cols-7 gap-px">
              {weeks.flat().map(cell => {
                const list = byDay.get(cell.date) ?? [];
                const count = list.length;
                const isToday = cell.date === today;
                const isSelected = cell.date === selectedDay;
                return (
                  <button
                    key={cell.date}
                    type="button"
                    onClick={() => setSelectedDay(cell.date)}
                    className={cn(
                      'flex flex-col items-center rounded-md px-0.5 pt-0.5 transition-colors cursor-pointer',
                      minCell,
                      isSelected ? 'bg-primary/20 ring-1 ring-primary/50' : count > 0 ? 'bg-accent/30 hover:bg-accent/60' : 'hover:bg-accent/30',
                      !cell.inMonth && 'opacity-40',
                    )}
                    aria-label={`${cell.date}${count ? `, ${count} earnings` : ''}`}
                    aria-pressed={isSelected}
                  >
                    <span className={cn(
                      'flex items-center justify-center rounded-full font-mono leading-none',
                      dense ? 'h-4 w-4 text-[9px]' : 'h-5 w-5 text-[10px]',
                      isToday ? 'bg-primary text-primary-foreground font-bold' : 'text-muted-foreground',
                    )}>{cell.day}</span>
                    {count > 0 && (
                      <span className="mt-0.5 flex flex-wrap items-center justify-center gap-px">
                        {list.slice(0, dense ? 2 : 3).map(r => (
                          <span key={r.symbol} className={cn('rounded-[3px] bg-primary/15 px-0.5 font-mono font-bold text-primary', chipText)}>
                            {r.symbol.slice(0, dense ? 4 : 6)}
                          </span>
                        ))}
                        {count > (dense ? 2 : 3) && (
                          <span className={cn('font-mono text-muted-foreground', chipText)}>+{count - (dense ? 2 : 3)}</span>
                        )}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Selected day detail */}
          <div className={cn('flex min-h-0 flex-col', dense ? 'mt-2 flex-1' : '')}>
            <p className={cn('mb-1 shrink-0 font-bold uppercase tracking-widest text-muted-foreground/70', dense ? 'text-[9px]' : 'text-[10px]')}>
              {selectedDay === today ? 'Today' : selectedDay} · {selectedRows.length} report{selectedRows.length === 1 ? '' : 's'}
            </p>
            {selectedRows.length === 0 ? (
              <p className="text-[10px] italic text-muted-foreground/60">No earnings scheduled.</p>
            ) : (
              <div className={cn('flex flex-col gap-1', dense ? 'min-h-0 flex-1 overflow-y-auto scrollbar-hide' : '')}>
                {selectedRows.map(r => (
                  <button
                    key={`${r.symbol}-${r.date}`}
                    type="button"
                    onClick={() => openSymbol(r.symbol)}
                    className="flex items-center gap-2 rounded-lg border border-border/10 glass-card-subtle px-2 py-1.5 text-left transition-colors hover:border-primary/30 hover:bg-accent/40 cursor-pointer"
                    title={`Open ${r.symbol} on the chart`}
                  >
                    <span className={cn('font-mono font-bold text-foreground shrink-0', dense ? 'text-[10px]' : 'text-xs')}>{r.symbol}</span>
                    <span className="min-w-0 flex-1 truncate text-[10px] text-muted-foreground">{r.name}</span>
                    {r.time && (
                      <span className={cn('shrink-0 rounded px-1 py-0.5 text-[8px] font-bold',
                        r.time === 'BMO' ? 'bg-sky-500/10 text-sky-400' : 'bg-violet-500/10 text-violet-400')}>{r.time}</span>
                    )}
                    <span className={cn('shrink-0 font-mono tabular-nums text-foreground', dense ? 'text-[10px]' : 'text-xs')}>
                      {r.epsEstimate != null ? r.epsEstimate.toFixed(2) : '—'}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Provenance — source + last updated, never fabricated. */}
      <p className={cn('shrink-0 font-mono text-muted-foreground/60', dense ? 'mt-1.5 text-[9px]' : 'mt-3 text-[10px]')}>
        {unavailable
          ? `UNAVAILABLE · ${t.data?.reason ?? 'source not reachable'}`
          : `${t.data?.source === 'nasdaq' ? 'Nasdaq' : 'Alpha Vantage'} · ${t.data?.fetchedAt ? `updated ${new Date(t.data.fetchedAt).toLocaleTimeString()}` : '—'}`}
      </p>
    </div>
  );
}
