'use client';

// ── Investor Eye — Timeline ──────────────────────────────────────────────────
// The bottom time-range scrubber. It controls the window the whole surface
// reads, so switching a range triggers one cached fetch per window rather than
// a per-frame playback (spec §22: do not make timeline playback expensive).
//
// Colour-coded: each window has its own hue (short = cool, long = warm) and the
// severity rail repeats the severity palette, so the ticks and the legend agree.

import { TIME_RANGES, type TimeRangeId } from '@/lib/investor-eye/store';
import type { NormalizedEvent } from '@/lib/investor-eye/types';
import { SEVERITY_COLORS, SEVERITY_ORDER } from '@/lib/investor-eye/layers';
import { cn } from '@/lib/utils';

interface TimelineProps {
  value: TimeRangeId;
  onChange: (id: TimeRangeId) => void;
  /** Events in the current window, drawn as ticks on the rail. */
  events: NormalizedEvent[];
  windowHours: number;
}

/** Window length → hue. Short windows read cool, long windows read warm. */
const RANGE_COLOR: Record<TimeRangeId, string> = {
  '1h': '#22d3ee',
  '6h': '#38bdf8',
  '24h': '#a78bfa',
  '7d': '#fb923c',
  '30d': '#f472b6',
};

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

  const activeColor = RANGE_COLOR[value] ?? '#38bdf8';

  return (
    <div className="glass-card rounded-xl border border-white/10 dark:border-white/5 px-3 py-2">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1">
          {TIME_RANGES.map((r) => {
            const color = RANGE_COLOR[r.id as TimeRangeId];
            const on = value === r.id;
            return (
              <button
                key={r.id}
                type="button"
                onClick={() => onChange(r.id)}
                aria-pressed={on}
                title={`Show the last ${r.label}`}
                className={cn(
                  'rounded-md px-2 py-1 text-[10px] font-mono font-bold transition-colors cursor-pointer border',
                  on ? 'text-foreground' : 'border-transparent text-muted-foreground hover:bg-accent/40 hover:text-foreground',
                )}
                style={on ? { borderColor: `${color}66`, backgroundColor: `${color}2e`, color } : undefined}
              >
                {r.label}
              </button>
            );
          })}
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
          <span
            className="absolute right-0 top-1/2 h-2 w-2 -translate-y-1/2 translate-x-1/2 rounded-full"
            style={{ backgroundColor: activeColor }}
            title="Now"
          />
        </div>

        <div className="shrink-0 text-[10px] font-mono text-muted-foreground">
          {events.length} events · {windowHours}h
        </div>
      </div>

      {/* Severity rail legend — the tick colours, named (spec §34). */}
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border/10 pt-1.5">
        <span className="text-[8px] font-bold uppercase tracking-widest text-muted-foreground/70">Severity</span>
        {SEVERITY_ORDER.map((sev) => (
          <span key={sev} className="inline-flex items-center gap-1 text-[9px] capitalize text-muted-foreground">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: SEVERITY_COLORS[sev] }} />
            {sev}
          </span>
        ))}
      </div>
    </div>
  );
}
