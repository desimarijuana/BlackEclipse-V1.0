'use client';

// ── Trading Calendar — GitHub-style contribution heatmap, native to BlackEclipse ──
// Each cell is a trading day. Color intensity reflects the day's net R-multiple
// (positive = green, negative = red, breakeven = neutral, no trades = empty).
// Hovering shows a detailed tooltip; clicking opens the Daily Journal.

import React, { useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import type { DayAggregate } from '@/lib/journal/types';
import { fmtR, fmtMoney } from './charts/echarts-container';

interface CalendarHeatmapProps {
  days: DayAggregate[];
  year?: number;
  onSelectDay?: (date: string) => void;
}

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

/** Map a day's net R to a 0-4 intensity bucket (signed). */
function intensityFor(netR: number): { level: number; sign: 'pos' | 'neg' | 'zero' } {
  if (netR === 0) return { level: 0, sign: 'zero' };
  const sign = netR > 0 ? 'pos' : 'neg';
  const abs = Math.abs(netR);
  let level = 1;
  if (abs >= 3) level = 4;
  else if (abs >= 2) level = 3;
  else if (abs >= 1) level = 2;
  return { level, sign };
}

const CELL_CLASS = {
  empty: 'bg-white/[0.03] border border-white/5',
  zero: 'bg-white/[0.08] border border-white/10',
  pos: {
    1: 'bg-emerald-500/25 border border-emerald-500/30',
    2: 'bg-emerald-500/45 border border-emerald-500/40',
    3: 'bg-emerald-500/70 border border-emerald-500/60',
    4: 'bg-emerald-400 border border-emerald-300/70',
  },
  neg: {
    1: 'bg-rose-500/25 border border-rose-500/30',
    2: 'bg-rose-500/45 border border-rose-500/40',
    3: 'bg-rose-500/70 border border-rose-500/60',
    4: 'bg-rose-500 border border-rose-400/70',
  },
} as const;

export function CalendarHeatmap({ days, year, onSelectDay }: CalendarHeatmapProps) {
  const [hovered, setHovered] = useState<DayAggregate | null>(null);
  const [hoverPos, setHoverPos] = useState<{ x: number; y: number } | null>(null);

  const targetYear = year ?? new Date().getUTCFullYear();
  const dayMap = useMemo(() => {
    const m = new Map<string, DayAggregate>();
    for (const d of days) if (d.date.startsWith(String(targetYear))) m.set(d.date, d);
    return m;
  }, [days, targetYear]);

  // Build weeks (columns) of 7 days (rows Mon..Sun). Start from the first
  // Monday on/before Jan 1, end on the last Sunday on/after Dec 31.
  const weeks = useMemo(() => {
    const start = new Date(Date.UTC(targetYear, 0, 1));
    const dayOfWeek = start.getUTCDay(); // 0=Sun
    const offsetToMonday = (dayOfWeek + 6) % 7;
    start.setUTCDate(start.getUTCDate() - offsetToMonday);

    const end = new Date(Date.UTC(targetYear, 11, 31));
    const endDow = end.getUTCDay();
    const offsetToSunday = (7 - endDow) % 7;
    end.setUTCDate(end.getUTCDate() + offsetToSunday);

    const cols: { date: string; inYear: boolean }[][] = [];
    const cursor = new Date(start);
    while (cursor <= end) {
      const col: { date: string; inYear: boolean }[] = [];
      for (let i = 0; i < 7; i++) {
        const iso = cursor.toISOString().slice(0, 10);
        col.push({ date: iso, inYear: iso.startsWith(String(targetYear)) });
        cursor.setUTCDate(cursor.getUTCDate() + 1);
      }
      cols.push(col);
    }
    return cols;
  }, [targetYear]);

  const monthLabels = useMemo(() => {
    const labels: { label: string; col: number }[] = [];
    let lastMonth = -1;
    weeks.forEach((col, ci) => {
      const firstInYear = col.find((c) => c.inYear);
      if (!firstInYear) return;
      const month = Number(firstInYear.date.slice(5, 7));
      if (month !== lastMonth) {
        labels.push({ label: new Date(Date.UTC(targetYear, month - 1, 1)).toLocaleString('en', { month: 'short' }), col: ci });
        lastMonth = month;
      }
    });
    return labels;
  }, [weeks, targetYear]);

  const handleHover = (e: React.MouseEvent, day: DayAggregate | null) => {
    setHovered(day);
    setHoverPos(day ? { x: e.clientX, y: e.clientY } : null);
  };

  return (
    <div className="relative">
      {/* Month labels */}
      <div className="mb-1 flex gap-1.5 pl-8">
        {weeks.map((_, ci) => {
          const label = monthLabels.find((m) => m.col === ci);
          return (
            <span key={ci} className="w-3.5 shrink-0 font-mono text-[9px] text-muted-foreground/70">
              {label ? label.label : ''}
            </span>
          );
        })}
      </div>

      <div className="flex gap-1.5">
        {/* Weekday labels */}
        <div className="flex flex-col gap-1.5 pr-1.5">
          {WEEKDAYS.map((d) => (
            <span key={d} className="flex h-3.5 items-center font-mono text-[9px] text-muted-foreground/60">{d}</span>
          ))}
        </div>

        {/* Grid */}
        <div className="flex gap-1.5">
          {weeks.map((col, ci) => (
            <div key={ci} className="flex flex-col gap-1.5">
              {col.map((cell) => {
                const day = dayMap.get(cell.date);
                const hasTrades = day && day.trades > 0;
                const inten = hasTrades ? intensityFor(day!.netR) : null;
                const cls = !hasTrades
                  ? CELL_CLASS.empty
                  : inten!.sign === 'zero'
                    ? CELL_CLASS.zero
                    : CELL_CLASS[inten!.sign][inten!.level as 1 | 2 | 3 | 4];
                return (
                  <button
                    key={cell.date}
                    type="button"
                    disabled={!hasTrades}
                    onMouseEnter={(e) => handleHover(e, hasTrades ? day! : null)}
                    onMouseLeave={() => handleHover(null as unknown as React.MouseEvent, null)}
                    onClick={() => hasTrades && onSelectDay?.(cell.date)}
                    className={cn(
                      'h-3.5 w-3.5 rounded-[3px] transition-transform',
                      cls,
                      hasTrades && 'cursor-pointer hover:scale-125 hover:ring-1 hover:ring-primary/50',
                      !cell.inYear && 'opacity-20',
                    )}
                    title={hasTrades ? `${cell.date} · ${fmtR(day!.netR)}` : cell.date}
                  />
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="mt-3 flex items-center gap-1.5 text-[9px] font-mono text-muted-foreground/70">
        <span>Less</span>
        {[0, 1, 2, 3, 4].map((l) => (
          <span key={l} className={cn('h-3 w-3 rounded-[3px]', l === 0 ? CELL_CLASS.empty : CELL_CLASS.pos[l as 1 | 2 | 3 | 4])} />
        ))}
        <span className="ml-2">More</span>
        <span className="ml-4 text-muted-foreground/50">green = profit · red = loss</span>
      </div>

      {/* Hover tooltip */}
      {hovered && hoverPos && (
        <div
          className="pointer-events-none fixed z-50 w-56 rounded-xl border border-white/10 bg-[#0f0f0f]/95 p-3 shadow-2xl shadow-black/50 backdrop-blur-xl"
          style={{ left: Math.min(hoverPos.x + 12, window.innerWidth - 240), top: Math.min(hoverPos.y + 12, window.innerHeight - 200) }}
        >
          <p className="font-mono text-[11px] font-bold text-foreground">{formatDate(hovered.date)}</p>
          <div className="mt-2 space-y-1 font-mono text-[10px] text-muted-foreground">
            <Row label="Trades" value={String(hovered.trades)} />
            <Row label="Win Rate" value={hovered.trades > 0 ? `${Math.round((hovered.wins / hovered.trades) * 100)}%` : '—'} />
            <Row label="Net P&L" value={fmtMoney(hovered.netPnl)} tone={hovered.netPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'} />
            <Row label="Net R" value={fmtR(hovered.netR)} tone={hovered.netR >= 0 ? 'text-emerald-400' : 'text-rose-400'} />
            <Row label="Best Trade" value={fmtR(hovered.bestR)} tone="text-emerald-400" />
            <Row label="Worst Trade" value={fmtR(hovered.worstR)} tone="text-rose-400" />
            {hovered.discipline != null && <Row label="Discipline" value={String(hovered.discipline)} />}
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground/70">{label}</span>
      <span className={cn('font-bold text-foreground', tone)}>{value}</span>
    </div>
  );
}

function formatDate(iso: string): string {
  const d = new Date(iso + 'T00:00:00Z');
  return d.toLocaleDateString('en', { year: 'numeric', month: 'long', day: 'numeric' });
}
