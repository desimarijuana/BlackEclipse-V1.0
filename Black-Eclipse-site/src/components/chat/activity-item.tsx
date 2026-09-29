'use client';

// ── ActivityItemRow — one tool/retrieval operation the agent performed ──────
// Compact by default: an icon, a human label, a status, an optional duration,
// and an optional result summary. Expandable only when there is something safe
// and useful to show (a failure code, a source name, the raw operation).
//
// It never shows raw JSON, credentials, or chain-of-thought. The "technical"
// details it can reveal are the operation name and a failure code — the things
// a developer-facing view is allowed to show.

import { useState } from 'react';
import { AlertCircle, Check, ChevronRight, Globe, Loader2, Scissors, Search, Sigma, Wrench } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ActivityItem } from '@/lib/agent/response-model';

export interface ActivityItemRowProps {
  item: ActivityItem;
  /** Tighter type/spacing for the floating dock. */
  compact?: boolean;
}

/** A conservative duration format — only shown when the runtime reported one. */
function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`;
}

/** Pick a category icon from the operation kind/name (display only). */
function CategoryIcon({ item, className }: { item: ActivityItem; className?: string }) {
  if (item.kind === 'bounded') return <Scissors size={12} className={className} />;
  if (item.kind === 'retrieval') return <Globe size={12} className={className} />;
  if (/search|research/.test(item.name)) return <Search size={12} className={className} />;
  if (/calc|rsi|sma|indicator|technical/.test(item.name)) return <Sigma size={12} className={className} />;
  return <Wrench size={12} className={className} />;
}

export function ActivityItemRow({ item, compact = false }: ActivityItemRowProps) {
  const [open, setOpen] = useState(false);
  const failed = item.status === 'failed';
  const running = item.status === 'running';

  // Reveal the operation name + failure code only when they exist. A plain
  // successful tool with no extras stays a single line.
  const hasDetails = Boolean(item.code) || item.kind === 'retrieval' || Boolean(item.name);

  return (
    <div className={cn('group/act rounded-lg', compact ? 'text-[11px]' : 'text-[12px]')}>
      <button
        type="button"
        onClick={() => hasDetails && setOpen((v) => !v)}
        aria-expanded={hasDetails ? open : undefined}
        disabled={!hasDetails}
        className={cn(
          'flex w-full items-center gap-2 rounded-lg px-1.5 py-1 text-left transition-colors',
          hasDetails && 'cursor-pointer hover:bg-accent/50',
        )}
      >
        <span className={cn('shrink-0', failed ? 'text-rose-400' : running ? 'text-primary' : 'text-muted-foreground/70')}>
          {running ? <Loader2 size={12} className="animate-spin" />
            : failed ? <AlertCircle size={12} />
            : <CategoryIcon item={item} />}
        </span>
        <span className={cn('min-w-0 flex-1 truncate', failed ? 'text-rose-300' : 'text-muted-foreground')}>
          {item.label}
        </span>
        {item.summary && !running && !failed && (
          <span className="shrink-0 text-muted-foreground/60">{item.summary}</span>
        )}
        {item.durationMs != null && !running && (
          <span className="shrink-0 font-mono text-[10px] text-muted-foreground/50 tabular-nums">
            {formatDuration(item.durationMs)}
          </span>
        )}
        {!running && !failed && <Check size={11} className="shrink-0 text-primary/60" />}
        {hasDetails && (
          <ChevronRight
            size={11}
            className={cn(
              'shrink-0 text-muted-foreground/40 transition-transform',
              open && 'rotate-90',
            )}
          />
        )}
      </button>

      {open && (
        <dl className="ml-6 mt-0.5 space-y-0.5 border-l border-border/30 pl-3 pb-1 font-mono text-[10.5px] text-muted-foreground/70">
          <div className="flex gap-2">
            <dt className="text-muted-foreground/50">operation</dt>
            <dd className="break-all">{item.name}</dd>
          </div>
          {item.kind === 'retrieval' && item.source && (
            <div className="flex gap-2">
              <dt className="text-muted-foreground/50">source</dt>
              <dd>{item.source}</dd>
            </div>
          )}
          {item.code && (
            <div className="flex gap-2">
              <dt className="text-muted-foreground/50">error</dt>
              <dd className="text-rose-300/90">{item.code}</dd>
            </div>
          )}
        </dl>
      )}
    </div>
  );
}
