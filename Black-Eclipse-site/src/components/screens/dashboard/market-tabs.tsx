'use client';

// ── MarketTabs — the country / market selector row ──────────────────────────
// The row of market tabs at the top of the Command Center. Clicking a tab makes
// that market's data the active context for every market-aware widget AND swaps
// in that market's own saved workspace layout (so each country can arrange its
// own widgets). Favourites are pinned to the front; users can add custom markets
// (e.g. PSX) and star/remove them.

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Check, Plus, Search, Star, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { MARKET_OPTIONS, marketViewName, useMarketViews } from '@/lib/dashboard/market-views';

const CODE_RE = /^[A-Za-z]{2,6}$/;

export function MarketTabs() {
  const { orderedViews, activeId, setActiveId, add, remove, toggleFavorite } = useMarketViews();
  const [adding, setAdding] = useState(false);
  const [query, setQuery] = useState('');
  const boxRef = useRef<HTMLDivElement>(null);

  const existing = useMemo(() => new Set(orderedViews.map(v => v.id)), [orderedViews]);

  const options = useMemo(() => {
    const q = query.trim().toLowerCase();
    return MARKET_OPTIONS
      .filter(o => !existing.has(o.id))
      .filter(o => !q || o.name.toLowerCase().includes(q) || o.id.toLowerCase().includes(q));
  }, [query, existing]);

  const codeCandidate = query.trim().toUpperCase();
  const canAddCode = CODE_RE.test(query.trim()) && !existing.has(codeCandidate);

  // Close the add popover on outside click / Esc.
  useEffect(() => {
    if (!adding) return;
    const onDoc = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) { setAdding(false); setQuery(''); }
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { setAdding(false); setQuery(''); } };
    document.addEventListener('mousedown', onDoc);
    window.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      window.removeEventListener('keydown', onKey);
    };
  }, [adding]);

  const pick = (id: string, name?: string) => {
    add(id, name);
    setAdding(false);
    setQuery('');
  };

  return (
    <div className="relative mb-3">
      <div className="glass-card flex items-center gap-2 overflow-hidden rounded-2xl px-2.5 py-2">
        <span className="hidden shrink-0 pl-1 text-[10px] font-bold uppercase tracking-widest text-muted-foreground sm:inline">
          Markets
        </span>

        <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto scrollbar-hide">
          {orderedViews.map(v => {
            const active = v.id === activeId;
            return (
              <div
                key={v.id}
                className={cn(
                  'group inline-flex shrink-0 items-center gap-1.5 rounded-xl border px-2.5 py-1 text-xs font-bold transition-all cursor-pointer',
                  active
                    ? 'border-primary/40 bg-primary/15 text-primary'
                    : 'border-white/15 dark:border-white/10 bg-accent/20 text-muted-foreground hover:border-primary/30 hover:text-foreground',
                )}
                onClick={() => setActiveId(v.id)}
                title={marketViewName(v.id)}
              >
                {v.favorite && <Star size={11} className="shrink-0 fill-amber-400 text-amber-400" />}
                <span className="truncate">{v.name}</span>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); toggleFavorite(v.id); }}
                  className={cn(
                    'shrink-0 cursor-pointer rounded p-0.5 transition-colors',
                    v.favorite ? 'text-amber-400' : 'text-muted-foreground/40 hover:text-amber-400',
                  )}
                  title={v.favorite ? 'Unpin from favourites' : 'Pin to favourites'}
                >
                  <Star size={10} className={v.favorite ? 'fill-amber-400' : ''} />
                </button>
                {orderedViews.length > 1 && (
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); remove(v.id); }}
                    className="shrink-0 cursor-pointer rounded p-0.5 text-muted-foreground/40 opacity-0 transition-opacity hover:text-rose-400 group-hover:opacity-100"
                    title={`Remove ${v.name}`}
                  >
                    <X size={10} />
                  </button>
                )}
              </div>
            );
          })}

          {/* Add market */}
          <div className="relative shrink-0" ref={boxRef}>
            <button
              type="button"
              onClick={() => setAdding(v => !v)}
              className={cn(
                'inline-flex items-center gap-1 rounded-xl border border-dashed px-2.5 py-1 text-xs font-bold transition-all cursor-pointer',
                adding
                  ? 'border-primary/40 bg-primary/15 text-primary'
                  : 'border-white/20 dark:border-white/10 text-muted-foreground hover:border-primary/40 hover:text-primary',
              )}
            >
              <Plus size={12} /> Add
            </button>

            {adding && (
              <div className="absolute left-0 top-full z-50 mt-2 w-64 rounded-2xl border border-white/15 dark:border-white/10 glass-card-strong p-2 shadow-2xl shadow-black/40 animate-fade-in">
                <div className="relative mb-1.5">
                  <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/60" />
                  <input
                    autoFocus
                    type="text"
                    value={query}
                    onChange={e => setQuery(e.target.value)}
                    onKeyDown={e => {
                      if (e.key !== 'Enter') return;
                      e.preventDefault();
                      if (options[0]) pick(options[0].id, options[0].name);
                      else if (canAddCode) pick(codeCandidate);
                    }}
                    placeholder="Search countries or type a code…"
                    className="w-full rounded-xl border border-border/30 bg-background/60 py-1.5 pl-7 pr-2 text-xs text-foreground outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>

                <div className="max-h-56 overflow-y-auto scrollbar-hide">
                  {options.map(o => (
                    <button
                      key={o.id}
                      type="button"
                      onClick={() => pick(o.id, o.name)}
                      className="flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs hover:bg-accent/50 cursor-pointer"
                    >
                      <span className="font-semibold text-foreground">{o.name}</span>
                      <span className="font-mono text-[9px] text-muted-foreground">{o.id}</span>
                    </button>
                  ))}

                  {canAddCode && !options.some(o => o.id === codeCandidate) && (
                    <button
                      type="button"
                      onClick={() => pick(codeCandidate)}
                      className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs text-primary hover:bg-primary/10 cursor-pointer"
                    >
                      <Plus size={11} /> Add custom “{codeCandidate}”
                    </button>
                  )}

                  {options.length === 0 && !canAddCode && (
                    <p className="px-2.5 py-3 text-center text-[10px] italic text-muted-foreground/60">
                      No markets match “{query}”.
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        <span className="hidden shrink-0 items-center gap-1 pr-1 text-[9px] font-semibold uppercase tracking-widest text-muted-foreground/60 lg:flex">
          <Check size={10} className="text-primary" />
          Each market keeps its own widgets
        </span>
      </div>
    </div>
  );
}
