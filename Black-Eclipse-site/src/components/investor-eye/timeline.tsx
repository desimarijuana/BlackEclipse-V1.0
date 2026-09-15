'use client';

// ── Investor Eye — Timeline ──────────────────────────────────────────────────
// The bottom time-range scrubber. It controls the window the whole surface
// reads, so switching a range triggers one cached fetch per window rather than
// a per-frame playback (spec §22: do not make timeline playback expensive).

import { TIME_RANGES, type TimeRangeId } from '@/lib/investor-eye/store';
import type { NormalizedEvent } from '@/lib/investor-eye/types';
import { cn } from '@/lib/utils';

interface TimelineProps {
  value: TimeRangeId;
  onChange: (id: TimeRangeId) => void;
  /** Events in the current window, drawn as ticks on the rail. */
  events: NormalizedEvent[];
  windowHours: number;
}

function severityTick(severity: string): string {
  switch (severity) {
    case 'critical': return 'bg-red-500';
    case 'high': return 'bg-orange-500';
    case 'medium': return 'bg-yellow-500';
    default: return 'bg-sky-400/70';
  }
}

export function Timeline({ value, onChange, events, windowHours }: TimelineProps) {
  const now = Date.now();
  const start = now - windowHours * 36e5;
  const span = Math.max(1, now - start);
  // Bucket ticks so a dense window does not paint hundreds of DOM nodes.
  const ticks: Array<{ pct: number; severity: string }> = [];
  for (const e of events) {
    const t = Date.parse(e.publishedAt);
    if (Number.isNaN(t)) continue;
    const pct = ((t - start) / span) * 100;
    if (pct < 0 || pct > 100) continue;
    ticks.push({ pct, severity: e.severity });
  }
  ticks.sort((a, b) => a.pct - b.pct);
  const spaced = ticks.filter((t, i, arr) => i === 0 || t.pct - arr[i - 1].pct > 0.4).slice(0, 160);

  return (
    <div className="glass-card rounded-xl border border-white/10 dark:border-white/5 px-3 py-2">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1">
          {TIME_RANGES.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => onChange(r.id)}
              className={cn(
                'rounded-md px-2 py-1 text-[10px] font-mono font-bold transition-colors cursor-pointer border',
                value === r.id
                  ? 'border-primary/30 bg-primary/15 text-foreground'
                  : 'border-transparent text-muted-foreground hover:bg-accent/40 hover:text-foreground',
              )}
            >
              {r.label}
            </button>
          ))}
        </div>

        <div className="relative h-6 flex-1 min-w-0">
          <div className="absolute left-0 right-0 top-1/2 h-px -translate-y-1/2 bg-border/40" />
          {spaced.map((t, i) => (
            <span
              key={i}
              className={cn('absolute top-1/2 h-3 w-[3px] -translate-y-1/2 rounded-sm', severityTick(t.severity))}
              style={{ left: `${t.pct}%`, opacity: 0.85 }}
              title={`${t.pct.toFixed(0)}% through window`}
            />
          ))}
          <span className="absolute right-0 top-1/2 h-2 w-2 -translate-y-1/2 translate-x-1/2 rounded-full bg-primary" />
        </div>

        <div className="shrink-0 text-[10px] font-mono text-muted-foreground">
          {events.length} events · {windowHours}h
        </div>
      </div>
    </div>
  );
}
