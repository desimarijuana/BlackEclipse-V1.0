'use client';

// ── SymbolSelector — reusable JDdS-backed instrument picker ──────────────────
// Autocompletes against the full JDDS universe (/api/quote?q=) and lets the user
// choose a symbol + market. Shared by the workspace toolbar, chart panels, the
// watchlist panel and the AI panel so symbol picking behaves identically
// everywhere. Also the drag SOURCE for dragging a symbol onto a chart panel.

import React, { useEffect, useRef, useState } from 'react';
import { Search } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface SymbolSuggestion {
  symbol: string;
  name: string;
  marketId: string;
  currency?: string;
  price?: number;
}

export interface SymbolSelectorProps {
  /** Compact trigger style (icon + input) for dense toolbars. */
  compact?: boolean;
  placeholder?: string;
  /** Initial query text. */
  value?: string;
  autoFocus?: boolean;
  /** Show the market chip on each suggestion. */
  showMarket?: boolean;
  onPick: (symbol: string, market: string) => void;
  /** Fired on Enter with no highlighted suggestion. */
  onSubmit?: (symbol: string) => void;
  className?: string;
  /** Render the results inline (no portal) — useful inside drawers. */
  inline?: boolean;
}

/**
 * Search JDDS for instruments. Debounced + abortable; returns [] on failure so
 * the caller can keep its previous list.
 */
export function useSymbolSearch(query: string): { suggestions: SymbolSuggestion[]; loading: boolean } {
  const [suggestions, setSuggestions] = useState<SymbolSuggestion[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 1) { setSuggestions([]); return; }
    const controller = new AbortController();
    setLoading(true);
    const t = setTimeout(() => {
      fetch(`/api/quote?q=${encodeURIComponent(q)}`, { signal: controller.signal })
        .then((r) => (r.ok ? r.json() : { suggestions: [] }))
        .then((j: { suggestions?: SymbolSuggestion[] }) => {
          if (!controller.signal.aborted) setSuggestions(j.suggestions ?? []);
        })
        .catch(() => { /* keep previous */ })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 160);
    return () => { controller.abort(); clearTimeout(t); };
  }, [query]);

  return { suggestions, loading };
}

export function SymbolSelector({
  compact = false, placeholder = 'Symbol', value = '', autoFocus, showMarket = true,
  onPick, onSubmit, className, inline = false,
}: SymbolSelectorProps) {
  const [query, setQuery] = useState(value);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);
  const { suggestions, loading } = useSymbolSearch(query);

  useEffect(() => { setQuery(value); }, [value]);

  useEffect(() => {
    if (suggestions.length > 0) { setOpen(true); setHighlight(0); }
  }, [suggestions]);

  useEffect(() => {
    if (inline) return;
    const onDoc = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [inline]);

  const choose = (s: SymbolSuggestion) => {
    onPick(s.symbol, s.marketId);
    setQuery(s.symbol);
    setOpen(false);
  };

  const results = open && suggestions.length > 0 && (
    <div className={cn(
      'z-50 max-h-72 overflow-y-auto p-1 shadow-2xl',
      inline ? 'rounded-xl border border-border/40 glass-card-subtle' : 'absolute left-0 top-full mt-1.5 w-72 rounded-xl border border-border/40 glass-card-strong',
    )}>
      {suggestions.map((s, i) => (
        <div
          key={`${s.symbol}-${s.marketId}`}
          onMouseEnter={() => setHighlight(i)}
          onMouseDown={(e) => { e.preventDefault(); choose(s); }}
          className={cn(
            'flex cursor-pointer items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 transition-colors',
            i === highlight ? 'bg-primary/15' : 'hover:bg-accent/50',
          )}
        >
          <span className="flex min-w-0 flex-col">
            <span className="font-mono text-[11px] font-bold text-foreground">{s.symbol}</span>
            <span className="truncate text-[9px] text-muted-foreground">{s.name}</span>
          </span>
          <span className="ml-2 flex shrink-0 items-center gap-1.5">
            {s.price != null && s.price > 0 && (
              <span className="font-mono text-[10px] text-muted-foreground">{s.price.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
            )}
            {showMarket && <span className="rounded bg-accent/40 px-1.5 py-0.5 text-[8px] font-bold uppercase text-muted-foreground">{s.marketId}</span>}
          </span>
        </div>
      ))}
    </div>
  );

  return (
    <div ref={boxRef} className={cn('relative', className)}>
      <div className={cn('flex items-center gap-1 rounded-lg bg-accent/40', compact ? 'px-1.5 py-0.5' : 'px-2 py-1')}>
        <Search size={compact ? 11 : 12} className="shrink-0 text-muted-foreground" />
        <input
          value={query}
          autoFocus={autoFocus}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => { if (suggestions.length) setOpen(true); }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setHighlight((h) => Math.min(h + 1, suggestions.length - 1)); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setHighlight((h) => Math.max(h - 1, 0)); }
            else if (e.key === 'Enter') {
              e.preventDefault();
              if (open && suggestions[highlight]) choose(suggestions[highlight]);
              else if (query.trim() && onSubmit) onSubmit(query.trim().toUpperCase());
              setOpen(false);
            } else if (e.key === 'Escape') { setOpen(false); }
          }}
          placeholder={placeholder}
          spellCheck={false}
          className={cn('bg-transparent font-mono font-bold text-foreground outline-none placeholder:text-muted-foreground/50', compact ? 'w-16 text-[10px]' : 'w-24 text-[11px]')}
        />
        {loading && <span className="h-3 w-3 shrink-0 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground/70" />}
      </div>
      {results}
    </div>
  );
}
