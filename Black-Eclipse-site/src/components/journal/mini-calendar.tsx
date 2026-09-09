'use client';

// ── Mini Calendar — compact last-30-days performance strip for the Overview ──

import React, { useMemo } from 'react';
import { cn } from '@/lib/utils';
import type { DayAggregate } from '@/lib/journal/types';
import { fmtR } from './charts/echarts-container';

interface MiniCalendarProps {
  days: DayAggregate[];
  onSelectDay?: (date: string) => void;
}

export function MiniCalendar({ days, onSelectDay }: MiniCalendarProps) {
  const last30 = useMemo(() => {
    const map = new Map(days.map((d) => [d.date, d]));
    const out: { date: string; day: DayAggregate | null }[] = [];
    const today = new Date();
    for (let i = 29; i >= 0; i--) {
      const d = new Date(today);
      d.setUTCDate(d.getUTCDate() - i);
      const key = d.toISOString().slice(0, 10);
      out.push({ date: key, day: map.get(key) ?? null });
    }
    return out;
  }, [days]);

  return (
    <div className="flex flex-col">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-serif text-sm font-semibold text-foreground">Last 30 Days</h3>
        <span className="font-mono text-[9px] text-muted-foreground/70">NET R PER DAY</span>
      </div>
      <div className="grid grid-cols-10 gap-1">
        {last30.map(({ date, day }) => {
          const has = day && day.trades > 0;
          const netR = day?.netR ?? 0;
          const cls = !has
            ? 'bg-white/[0.03]'
            : netR > 0
              ? 'bg-emerald-500/50'
              : netR < 0
                ? 'bg-rose-500/50'
                : 'bg-white/[0.08]';
          return (
            <button
              key={date}
              type="button"
              disabled={!has}
              onClick={() => has && onSelectDay?.(date)}
              title={has ? `${date} · ${fmtR(netR)}` : date}
              className={cn('h-6 rounded-[4px] transition-transform', cls, has && 'cursor-pointer hover:scale-110 hover:ring-1 hover:ring-primary/50')}
            />
          );
        })}
      </div>
      <div className="mt-2 flex items-center gap-3 text-[9px] font-mono text-muted-foreground/60">
        <span className="flex items-center gap-1"><span className="h-2 w-2 rounded bg-emerald-500/50" /> Profit</span>
        <span className="flex items-center gap-1"><span className="h-2 w-2 rounded bg-rose-500/50" /> Loss</span>
        <span className="flex items-center gap-1"><span className="h-2 w-2 rounded bg-white/[0.08]" /> Flat</span>
        <span className="flex items-center gap-1"><span className="h-2 w-2 rounded bg-white/[0.03]" /> No trade</span>
      </div>
    </div>
  );
}
