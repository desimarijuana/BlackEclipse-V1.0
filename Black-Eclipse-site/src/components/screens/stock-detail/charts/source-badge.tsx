'use client';

import { cn } from '@/lib/utils';
import type { StockFactState, StockSourceRef } from '@/lib/stock-intelligence/types';

const LABEL: Record<StockFactState, string> = {
  LIVE: 'Live',
  CACHED: 'Cached',
  HISTORICAL: 'Historical',
  FILING: 'Filing',
  WEB: 'Web',
  AI_EXTRACTED: 'AI extracted',
  DERIVED: 'Derived',
  UNAVAILABLE: 'Unavailable',
};

const TONE: Record<StockFactState, string> = {
  LIVE: 'border-emerald-400/30 text-emerald-300',
  CACHED: 'border-sky-400/30 text-sky-300',
  HISTORICAL: 'border-slate-400/30 text-slate-300',
  FILING: 'border-indigo-400/30 text-indigo-300',
  WEB: 'border-cyan-400/30 text-cyan-300',
  AI_EXTRACTED: 'border-violet-400/30 text-violet-300',
  DERIVED: 'border-amber-400/30 text-amber-300',
  UNAVAILABLE: 'border-border/40 text-muted-foreground',
};

export function SourceBadge({
  state,
  sources = [],
  className,
}: {
  state: StockFactState;
  sources?: StockSourceRef[];
  className?: string;
}) {
  const detail = sources.map((source) => source.label).join(' · ');
  return (
    <span
      title={detail || LABEL[state]}
      className={cn(
        'shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-mono uppercase tracking-wide',
        TONE[state],
        className,
      )}
    >
      {LABEL[state]}
    </span>
  );
}
