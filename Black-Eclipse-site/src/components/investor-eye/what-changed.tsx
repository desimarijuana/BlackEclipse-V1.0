'use client';

// ── Investor Eye — What Changed ──────────────────────────────────────────────
// A compact summary of the selected window: new events, severity breakdown,
// activity by channel, and observed market moves. These are OBSERVATIONS, not
// predictions (spec §23).

import { useMemo } from 'react';
import { ArrowUpRight, Minus } from 'lucide-react';
import type { MarketObservation, NormalizedEvent } from '@/lib/investor-eye/types';
import { formatPct } from '@/lib/investor-eye/format';
import { cn } from '@/lib/utils';

interface WhatChangedProps {
  events: NormalizedEvent[];
  markets: MarketObservation[];
  windowHours: number;
}

export function WhatChanged({ events, markets, windowHours }: WhatChangedProps) {
  const summary = useMemo(() => {
    const major = events.filter((e) => e.severity === 'critical' || e.severity === 'high').length;
    const channels = new Map<string, number>();
    const types = new Map<string, number>();
    for (const e of events) {
      for (const c of e.channels) channels.set(c, (channels.get(c) ?? 0) + 1);
      types.set(e.eventType, (types.get(e.eventType) ?? 0) + 1);
    }
    const topChannels = [...channels.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4);
    const topTypes = [...types.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3);
    const movers = [...markets]
      .filter((m) => Number.isFinite(m.changePct))
      .sort((a, b) => Math.abs(b.changePct) - Math.abs(a.changePct))
      .slice(0, 5);
    return { major, topChannels, topTypes, movers };
  }, [events, markets]);

  return (
    <div className="glass-card rounded-xl border border-white/10 dark:border-white/5 px-3 py-2.5">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">What Changed</span>
        <span className="text-[9px] font-mono text-muted-foreground/70">{windowHours}h window</span>
      </div>

      <div className="space-y-1.5">
        <Line label={`${events.length} geopolitical events`} positive={events.length > 0} />
        <Line label={`${summary.major} major (high/critical)`} positive={summary.major > 0} />
        {summary.topChannels.map(([channel, count]) => (
          <div key={channel} className="flex items-center justify-between gap-2 text-[10px]">
            <span className="truncate text-muted-foreground">{channel}</span>
            <span className="shrink-0 font-mono text-foreground">{count}</span>
          </div>
        ))}
        {summary.topTypes.map(([type, count]) => (
          <div key={type} className="flex items-center justify-between gap-2 text-[10px]">
            <span className="truncate text-muted-foreground/80">{type.replace(/_/g, ' ')}</span>
            <span className="shrink-0 font-mono text-muted-foreground">{count}</span>
          </div>
        ))}
      </div>

      {summary.movers.length > 0 && (
        <div className="mt-3 border-t border-border/10 pt-2">
          <div className="mb-1 text-[9px] font-bold uppercase tracking-widest text-muted-foreground">Markets</div>
          <div className="space-y-1">
            {summary.movers.map((m) => (
              <div key={m.marketId} className="flex items-center justify-between gap-2 text-[10px]">
                <span className="truncate text-muted-foreground">{m.symbol}</span>
                <span
                  className={cn(
                    'shrink-0 font-mono font-semibold',
                    m.changePct > 0 ? 'text-emerald-400' : m.changePct < 0 ? 'text-red-400' : 'text-muted-foreground',
                  )}
                >
                  {formatPct(m.changePct)}
                </span>
              </div>
            ))}
          </div>
          <div className="mt-1.5 text-[9px] italic text-muted-foreground/60">
            Observations only — not predictions.
          </div>
        </div>
      )}
    </div>
  );
}

function Line({ label, positive }: { label: string; positive: boolean }) {
  return (
    <div className="flex items-center gap-1.5 text-[10px]">
      {positive ? (
        <ArrowUpRight size={11} className="shrink-0 text-primary" />
      ) : (
        <Minus size={11} className="shrink-0 text-muted-foreground/60" />
      )}
      <span className={positive ? 'text-foreground' : 'text-muted-foreground'}>{label}</span>
    </div>
  );
}
