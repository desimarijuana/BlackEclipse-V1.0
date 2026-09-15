'use client';

// ── LayoutTabs — the named-workspace selector row ────────────────────────────
// Each tab is a NAMED LAYOUT the user creates ("US", "Crypto", "My Tech Sheet",
// …). Clicking a tab swaps in that layout's own persisted widgets. The Add flow
// only asks for a NAME — it never asks the user to pick a country. Double-click
// a tab to rename it.
//
// Uses the shared frosted-glass <TabBar> so it matches every other tab strip.

import React, { useEffect, useRef, useState } from 'react';
import { Globe, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { TabBar, type TabItem } from '@/components/ui/tab-bar';
import { useMarketViews } from '@/lib/dashboard/market-views';

export function MarketTabs() {
  const { views, activeId, active, setActiveId, create, remove, rename } = useMarketViews();
  const [adding, setAdding] = useState(false);
  const [draftName, setDraftName] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const addRef = useRef<HTMLDivElement>(null);
  // A new layout inherits the active layout's data context (no country picker).
  const inheritMarket = active?.market ?? 'US';

  // Close the add popover on outside click / Esc.
  useEffect(() => {
    if (!adding) return;
    const onDoc = (e: MouseEvent) => {
      if (addRef.current && !addRef.current.contains(e.target as Node)) { setAdding(false); setDraftName(''); }
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { setAdding(false); setDraftName(''); } };
    document.addEventListener('mousedown', onDoc);
    window.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      window.removeEventListener('keydown', onKey);
    };
  }, [adding]);

  const commitAdd = () => {
    create(draftName || 'New layout', inheritMarket);
    setAdding(false);
    setDraftName('');
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
        className="w-24 rounded-lg border border-primary/40 bg-background/70 px-1.5 py-0.5 text-xs font-bold text-foreground outline-none focus:ring-1 focus:ring-primary"
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
          Layouts
        </span>
      )}
      trailing={(
        <div className="flex shrink-0 items-center gap-1.5">
          {/* Add a named layout */}
          <div className="relative" ref={addRef}>
            <button
              type="button"
              onClick={() => setAdding(v => !v)}
              className={cn(
                'glass-button flex items-center gap-1.5 rounded-2xl px-3.5 py-2 text-xs font-bold transition-all cursor-pointer',
                adding ? 'text-primary' : 'text-muted-foreground hover:text-primary',
              )}
              title="Add a new layout"
            >
              <Plus size={12} /> Add
            </button>

            {adding && (
              <div className="absolute right-0 top-full z-50 mt-2 w-64 rounded-2xl border border-white/15 dark:border-white/10 glass-card-strong p-2.5 shadow-2xl shadow-black/40 animate-fade-in">
                <p className="mb-1.5 px-0.5 text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
                  New layout
                </p>
                <input
                  autoFocus
                  type="text"
                  value={draftName}
                  onChange={e => setDraftName(e.target.value)}
                  onKeyDown={e => {
                    if (e.key !== 'Enter') return;
                    e.preventDefault();
                    commitAdd();
                  }}
                  placeholder="Name it anything (e.g. My Tech Sheet)…"
                  className="w-full rounded-xl border border-border/30 bg-background/60 px-2.5 py-1.5 text-xs text-foreground outline-none focus:ring-1 focus:ring-primary"
                />
                <button
                  type="button"
                  onClick={commitAdd}
                  className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-xl border border-primary/40 bg-primary/15 px-3 py-1.5 text-xs font-bold text-primary transition-colors hover:bg-primary/25 cursor-pointer"
                >
                  <Plus size={11} /> Create layout
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    />
  );
}
