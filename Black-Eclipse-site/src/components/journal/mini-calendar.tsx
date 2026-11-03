'use client';

// ── Mini Calendar — compact GitHub-style last-N-weeks performance strip ──────
// A week-column grid (7 rows Mon→Sun × N week columns) of small fixed-size
// cells, matching the contribution-graph idiom. Cell colour encodes the day's
// net R with SIGNED INTENSITY (darker = bigger move), so a +5R day reads
// stronger than a +0.3R day instead of both being one flat green.
//
// Cells are a fixed 11px box (not stretched grid tracks) — the previous version
// had no width class, so each cell stretched to fill its column and the
// "squares" became large rectangles.

import React, { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '@/lib/utils';
import type { DayAggregate } from '@/lib/journal/types';
import { intensityFor } from '@/lib/journal/intensity';
import { fmtR, fmtMoney } from './charts/echarts-container';

interface MiniCalendarProps {
  days: DayAggregate[];
  onSelectDay?: (date: string) => void;
  /** Number of week columns to show. Default 39 (nine months). */
  weeks?: number;
  /**
   * Fill the container width (default) — cells stay square via `aspect-ratio`,
   * so the strip scales with its card instead of leaving dead space. Set false
   * to use a fixed `cellSize` instead.
   */
  fill?: boolean;
  /**
   * Upper bound on cell size in `fill` mode. Without this a very wide card
   * stretches the cells to ~50px and the strip dominates the page; capping keeps
   * them big-but-proportional and centres the grid in the leftover space.
   */
  maxCell?: number;
  /** Fixed cell edge length in px when `fill` is false. */
  cellSize?: number;
}

export const MINI_CELL_PX = 22;
/** Largest cell produced by `fill` mode before the grid stops growing. */
export const MINI_CELL_MAX = 30;

/** Fixed-size metrics used when `fill` is false. */
function metrics(cellSize: number) {
  return {
    cell: cellSize,
    gap: Math.max(2, Math.round(cellSize * 0.15)),
    radius: Math.max(3, Math.round(cellSize * 0.2)),
    labelFont: Math.max(8, Math.round(cellSize * 0.4)),
  };
}

const CELL_CLASS = {
  empty: 'bg-white/[0.04]',
  zero: 'bg-white/[0.10]',
  pos: {
    1: 'bg-emerald-500/25',
    2: 'bg-emerald-500/45',
    3: 'bg-emerald-500/70',
    4: 'bg-emerald-400',
  },
  neg: {
    1: 'bg-rose-500/25',
    2: 'bg-rose-500/45',
    3: 'bg-rose-500/70',
    4: 'bg-rose-500',
  },
} as const;

/** Monday-first weekday index (0=Mon … 6=Sun) for a UTC date. */
function mondayIndex(d: Date): number {
  return (d.getUTCDay() + 6) % 7;
}

const MONTH_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function MiniCalendar({
  days, onSelectDay, weeks = 39, fill = true, maxCell = MINI_CELL_MAX, cellSize = MINI_CELL_PX,
}: MiniCalendarProps) {
  const [hovered, setHovered] = useState<{ day: DayAggregate | null; date: string } | null>(null);
  const [hoverPos, setHoverPos] = useState<{ x: number; y: number } | null>(null);
  // A 39-week strip squeezes each day to a few pixels on phones; show ~a
  // quarter instead and let the parent keep its full-range data.
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 640px)');
    const update = () => setNarrow(mq.matches);
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, []);
  const effWeeks = narrow ? Math.min(weeks, 13) : weeks;
  const m = metrics(cellSize);
  // In fill mode the columns share the width, but each cell is capped so a wide
  // card doesn't produce enormous squares. The grid is then centred.
  const gridStyle = fill
    ? { gap: 4, width: '100%', maxWidth: `${effWeeks * (maxCell + 4)}px` }
    : { gap: m.gap };

  const dayMap = useMemo(() => new Map(days.map((d) => [d.date, d])), [days]);

  // Build `weeks` columns of 7 days ending on the current week's Sunday.
  const columns = useMemo(() => {
    const today = new Date();
    const todayUtc = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate()));
    // End on the Sunday of the current week so the last column is complete.
    const end = new Date(todayUtc);
    end.setUTCDate(end.getUTCDate() + (6 - mondayIndex(todayUtc)));

    const cols: { date: string; inFuture: boolean; day: DayAggregate | null }[][] = [];
    const cursor = new Date(end);
    cursor.setUTCDate(cursor.getUTCDate() - (effWeeks * 7 - 1));
    for (let w = 0; w < effWeeks; w++) {
      const col: { date: string; inFuture: boolean; day: DayAggregate | null }[] = [];
      for (let d = 0; d < 7; d++) {
        const iso = cursor.toISOString().slice(0, 10);
        col.push({ date: iso, inFuture: cursor > todayUtc, day: dayMap.get(iso) ?? null });
        cursor.setUTCDate(cursor.getUTCDate() + 1);
      }
      cols.push(col);
    }
    return cols;
  }, [dayMap, effWeeks]);

  // Month labels sit above the first column whose week contains that month's 1st.
  const monthLabels = useMemo(() => {
    const labels: { label: string; col: number }[] = [];
    let last = -1;
    columns.forEach((col, ci) => {
      const month = Number(col[0].date.slice(5, 7));
      if (month !== last) {
        labels.push({ label: MONTH_SHORT[month - 1], col: ci });
        last = month;
      }
    });
    return labels;
  }, [columns]);

  const traded = useMemo(() => columns.flat().filter((c) => c.day && c.day.trades > 0), [columns]);
  // Cell shading follows the same basis rule as the rest of the journal: R when
  // a day has a stop-derived basis, otherwise realized P&L. The P&L thresholds
  // come from the data's own magnitude quartiles so the gradient stays readable.
  const pnlThresholds = useMemo<[number, number, number]>(() => {
    const mags = traded
      .filter((c) => c.day && !c.day.rAvailable)
      .map((c) => Math.abs(c.day!.netPnl))
      .filter((v) => v > 0)
      .sort((a, b) => a - b);
    if (mags.length === 0) return [10, 50, 150];
    const at = (q: number) => mags[Math.min(mags.length - 1, Math.floor(q * mags.length))];
    return [at(0.25), at(0.5), at(0.75)];
  }, [traded]);
  const valueOfDay = (day: DayAggregate) => (day.rAvailable ? day.netR : day.netPnl);
  const allDaysUseR = useMemo(
    () => traded.length > 0 && traded.every((c) => c.day!.rAvailable),
    [traded],
  );
  const total = useMemo(
    () => traded.reduce((a, c) => a + (c.day ? (allDaysUseR ? c.day.netR : c.day.netPnl) : 0), 0),
    [traded, allDaysUseR],
  );

  const handleEnter = (e: React.MouseEvent, date: string, day: DayAggregate | null) => {
    if (!day || day.trades === 0) { setHovered(null); setHoverPos(null); return; }
    setHovered({ day, date });
    setHoverPos({ x: e.clientX, y: e.clientY });
  };
  const clearHover = () => { setHovered(null); setHoverPos(null); };

  return (
    <div className="flex flex-col">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="font-serif text-sm font-semibold text-foreground">
          Last {effWeeks} Weeks
        </h3>
        <span className={cn('font-mono text-[10px] font-bold', total > 0 ? 'text-emerald-400' : total < 0 ? 'text-rose-400' : 'text-muted-foreground/70')}>
          {allDaysUseR ? fmtR(total) : fmtMoney(total)}
        </span>
      </div>

      {/*
        In `fill` mode the grid spans the card: the 7 weekday rows and N week
        columns share the width via flex, and each cell keeps a square aspect
        ratio so the cells grow with the container instead of leaving dead space.
      */}
      <div className={cn('flex', fill ? 'w-full justify-center gap-1.5' : 'gap-1.5')}>
        {/* Weekday gutter */}
        <div className={cn('flex flex-col', fill ? 'shrink-0' : 'pr-1')} style={{ gap: fill ? undefined : m.gap }} aria-hidden>
          {['Mon', '', 'Wed', '', 'Fri', '', 'Sun'].map((d, i) => (
            <span
              key={i}
              className={cn('flex items-center font-mono text-muted-foreground/50', fill && 'flex-1')}
              style={fill ? { fontSize: m.labelFont } : { height: m.cell, fontSize: m.labelFont }}
            >
              {d}
            </span>
          ))}
        </div>

        <div className="flex min-w-0 flex-col" style={gridStyle}>
          {/* Month labels */}
          <div className={cn('mb-1 flex', fill ? 'w-full gap-1' : 'gap-1.5')} aria-hidden>
            {columns.map((_, ci) => {
              const label = monthLabels.find((ml) => ml.col === ci);
              return (
                <span
                  key={ci}
                  className={cn(
                    'overflow-visible whitespace-nowrap font-mono text-muted-foreground/60',
                    fill && 'flex-1',
                  )}
                  style={fill ? { fontSize: m.labelFont } : { width: m.cell, fontSize: m.labelFont }}
                >
                  {label ? label.label : ''}
                </span>
              );
            })}
          </div>

          {/* Grid */}
          <div className={cn('flex', fill ? 'w-full gap-1' : 'gap-1.5')}>
            {columns.map((col, ci) => (
              <div
                key={ci}
                className={cn('flex flex-col', fill && 'min-w-0 flex-1')}
                style={{ gap: fill ? 4 : m.gap }}
              >
                {col.map((cell) => {
                  const has = cell.day && cell.day.trades > 0;
                  const value = cell.day ? valueOfDay(cell.day) : 0;
                  const inten = has
                    ? intensityFor(value, cell.day!.rAvailable ? [1, 2, 3] : pnlThresholds)
                    : null;
                  const cls = !has
                    ? CELL_CLASS.empty
                    : inten!.sign === 'zero'
                      ? CELL_CLASS.zero
                      : CELL_CLASS[inten!.sign][inten!.level as 1 | 2 | 3 | 4];
                  return (
                    <button
                      key={cell.date}
                      type="button"
                      disabled={!has}
                      onMouseEnter={(e) => handleEnter(e, cell.date, cell.day)}
                      onMouseLeave={clearHover}
                      onClick={() => has && onSelectDay?.(cell.date)}
                      aria-label={has ? `${cell.date}: ${cell.day!.rAvailable ? fmtR(value) : fmtMoney(value)}` : `${cell.date}: no trade`}
                      className={cn(
                        'transition-transform',
                        // Square via aspect-ratio so cells scale with `fill`.
                        fill ? 'w-full aspect-square' : '',
                        cls,
                        cell.inFuture && 'opacity-25',
                        has && 'cursor-pointer hover:scale-110 hover:ring-1 hover:ring-primary/60',
                      )}
                      style={fill
                        ? { borderRadius: 4 }
                        : { width: m.cell, height: m.cell, borderRadius: m.radius }}
                    />
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-muted-foreground/60" style={{ fontSize: m.labelFont }}>
        {([
          ['bg-emerald-500/70', 'Profit'],
          ['bg-rose-500/70', 'Loss'],
          ['bg-white/[0.10]', 'Flat'],
          ['bg-white/[0.04]', 'No trade'],
        ] as const).map(([cls, label]) => (
          <span key={label} className="flex items-center gap-1">
            <span
              className={cn('inline-block', cls)}
              style={{ width: m.cell * 0.5, height: m.cell * 0.5, borderRadius: Math.max(2, m.radius - 1) }}
            />
            {label}
          </span>
        ))}
        <span className="ml-auto text-muted-foreground/50">darker = bigger move</span>
      </div>

      {/* Hover tooltip.
          Rendered through a portal to <body>: `position: fixed` is relative to
          the nearest ancestor with a transform/filter/backdrop-filter, and the
          frosted-glass card around this chart sets one — so without the portal
          the tooltip anchored to the card and drifted down instead of following
          the cursor. The portal restores true viewport positioning. */}
      {hovered?.day && hoverPos && typeof document !== 'undefined' &&
        createPortal(
          <div
            className="pointer-events-none fixed z-[100] w-48 rounded-xl border border-white/10 glass-card-strong p-3 shadow-2xl shadow-black/50"
            style={{
              left: Math.max(8, Math.min(hoverPos.x + 12, window.innerWidth - 210)),
              top: Math.max(8, Math.min(hoverPos.y + 12, window.innerHeight - 190)),
            }}
          >
            <p className="font-mono text-[10px] font-bold text-foreground">{hovered.date}</p>
            <div className="mt-2 space-y-1 font-mono text-[10px]">
              {hovered.day.rAvailable ? (
                <Row label="Net R" value={fmtR(hovered.day.netR)} tone={hovered.day.netR >= 0 ? 'text-emerald-400' : 'text-rose-400'} />
              ) : (
                <Row label="Net R" value="UNAVAILABLE" />
              )}
              <Row label="Net P&L" value={fmtMoney(hovered.day.netPnl)} tone={hovered.day.netPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'} />
              <Row label="Trades" value={String(hovered.day.trades)} />
              <Row
                label="Win rate"
                value={hovered.day.trades > 0 ? `${Math.round((hovered.day.wins / hovered.day.trades) * 100)}%` : '—'}
              />
              {hovered.day.rAvailable && (
                <Row label="Best / Worst" value={`${fmtR(hovered.day.bestR)} / ${fmtR(hovered.day.worstR)}`} />
              )}
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}

function Row({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-muted-foreground/70">{label}</span>
      <span className={cn('font-bold text-foreground', tone)}>{value}</span>
    </div>
  );
}
