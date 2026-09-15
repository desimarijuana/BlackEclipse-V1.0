'use client';

// ── MarketTabs — the country / market selector row ──────────────────────────
// The row of market tabs at the top of the Command Center. Clicking a tab makes
// that market's data the active context for every market-aware widget AND swaps
// in that market's own saved workspace layout (so each country can arrange its
// own widgets). Users can add custom markets and double-click a tab to rename it.
//
// Uses the shared frosted-glass <TabBar> so it matches every other tab strip in
// the terminal (portfolio, journal, screener) instead of a bespoke pill.

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Globe, Plus, Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { TabBar, type TabItem } from '@/components/ui/tab-bar';
import { MARKET_OPTIONS, useMarketViews } from '@/lib/dashboard/market-views';

const CODE_RE = /^[A-Za-z]{2,6}$/;

export function MarketTabs() {
  const { views, activeId, setActiveId, add, remove, rename } = useMarketViews();
  const [adding, setAdding] = useState(false);
  const [query, setQuery] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const boxRef = useRef<HTMLDivElement>(null);

  const existing = useMemo(() => new Set(views.map(v => v.id)), [views]);

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

  const startRename = (id: string) => {
    const view = views.find(v => v.id === id);
    if (!view) return;
    setEditingId(id);
    setDraft(view.name);
  };

  const commitRename = () => {
    if (editingId) rename(editingId, draft);
    setEditingId(null);
    setDraft('');
  };

  const items: TabItem[] = views.map(v => ({
    id: v.id,
    icon: v.id === activeId ? Globe : undefined,
    editing: editingId === v.id,
    label: editingId === v.id ? (
      <input
        autoFocus
        value={draft}
        onChange={e => setDraft(e.target.value)}
        onClick={e => e.stopPropagation()}
        onBlur={commitRename}
        onKeyDown={e => {
          e.stopPropagation();
          if (e.key === 'Enter') { e.preventDefault(); commitRename(); }
          else if (e.key === 'Escape') { setEditingId(null); setDraft(''); }
        }}
        className="w-20 rounded-lg border border-primary/40 bg-background/70 px-1.5 py-0.5 text-xs font-bold text-foreground outline-none focus:ring-1 focus:ring-primary"
      />
    ) : v.name,
  }));

  return (
    <TabBar
      className="mb-3"
      items={items}
      activeId={activeId}
      onChange={setActiveId}
      onItemDoubleClick={startRename}
      onItemRemove={views.length > 1 ? remove : undefined}
      leading={(
        <span className="hidden shrink-0 pl-3 pr-1 text-[10px] font-bold uppercase tracking-widest text-muted-foreground sm:inline">
          Markets
        </span>
      )}
      trailing={(
        <div className="relative shrink-0" ref={boxRef}>
          <button
            type="button"
            onClick={() => setAdding(v => !v)}
            className={cn(
              'glass-button flex items-center gap-1.5 rounded-2xl px-3.5 py-2 text-xs font-bold transition-all cursor-pointer',
              adding ? 'text-primary' : 'text-muted-foreground hover:text-primary',
            )}
            title="Add a market"
          >
            <Plus size={12} /> Add
          </button>

          {adding && (
            <div className="absolute right-0 top-full z-50 mt-2 w-64 rounded-2xl border border-white/15 dark:border-white/10 glass-card-strong p-2 shadow-2xl shadow-black/40 animate-fade-in">
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
      )}
    />
  );
}
