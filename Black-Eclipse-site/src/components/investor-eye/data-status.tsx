'use client';

// ── Investor Eye — Data Status ───────────────────────────────────────────────
// Freshness indicator. It never claims LIVE for cached/unavailable data, and it
// renders "DATA UNAVAILABLE · LAST KNOWN HH:MM UTC" instead of a fake zero.

import type { DataStatus } from '@/lib/investor-eye/types';
import { cn } from '@/lib/utils';

function dot(provenance: string): string {
  switch (provenance) {
    case 'LIVE': return 'bg-emerald-400';
    case 'DELAYED': return 'bg-amber-400';
    case 'CACHED': return 'bg-sky-400';
    case 'HISTORICAL': return 'bg-violet-400';
    case 'ESTIMATED': return 'bg-fuchsia-400';
    case 'DEMO': return 'bg-pink-400';
    default: return 'bg-red-500';
  }
}

/** Human label for a source's honest state. */
function sourceState(s: DataStatus['sources'][number]): string {
  switch (s.state) {
    case 'rate_limited':
      return `rate limited${s.retryAfterSec ? ` — retry in ${Math.ceil(s.retryAfterSec / 60)}m` : ''}`;
    case 'error': return `error — ${s.lastError ?? 'unknown'}`;
    case 'optional': return 'not configured (optional)';
    case 'available': return s.lastSuccess ? 'ok' : 'idle';
    default: return 'idle';
  }
}

export function DataStatusChip({ status, className }: { status: DataStatus; className?: string }) {
  const live = status.provenance === 'LIVE';
  const throttled = status.sources.filter((s) => s.state === 'rate_limited');
  return (
    <div
      className={cn(
        'inline-flex items-center gap-2 rounded-full border px-2.5 py-1',
        className,
        live ? 'border-emerald-500/20' : throttled.length > 0 ? 'border-amber-500/25' : 'border-border/40',
      )}
      title={status.sources.map((s) => `${s.name}: ${sourceState(s)}`).join('\n')}
    >
      <span className={cn('h-1.5 w-1.5 rounded-full', dot(status.provenance), live && 'animate-pulse')} />
      <span className="text-[10px] font-mono font-bold tracking-wide text-foreground">{status.provenance}</span>
      <span className="text-[10px] font-mono text-muted-foreground">{status.label}</span>
      {throttled.length > 0 && (
        <span className="text-[10px] font-mono text-amber-400" title="Some sources are throttled — the feed may be thinner than usual">
          {throttled.length} throttled
        </span>
      )}
    </div>
  );
}
