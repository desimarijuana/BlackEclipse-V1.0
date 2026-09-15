'use client';

// ── LayoutTabs — the named-workspace selector row ────────────────────────────
// Each tab is a NAMED LAYOUT the user creates ("US", "Crypto", "My Tech Sheet",
// …). Clicking a tab swaps in that layout's own persisted widgets. The Add flow
// only creates the layout — it drops the new tab straight into inline rename so
// the user types its name right on the tab (same field as double-click rename).
//
// Uses the shared frosted-glass <TabBar> so it matches every other tab strip.

import React, { useState } from 'react';
import { Globe, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { TabBar, type TabItem } from '@/components/ui/tab-bar';
import { useMarketViews } from '@/lib/dashboard/market-views';

export function MarketTabs() {
  const { views, activeId, active, setActiveId, create, remove, rename } = useMarketViews();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  // A new layout inherits the active layout's data context (no country picker).
  const inheritMarket = active?.market ?? 'US';

  // Add → create a layout immediately, then rename it inline on the tab.
  const addLayout = () => {
    const id = create(`Layout ${views.length + 1}`, inheritMarket);
    setEditingId(id);
    setDraft(`Layout ${views.length + 1}`);
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
        onFocus={e => e.currentTarget.select()}
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
        <button
          type="button"
          onClick={addLayout}
          className={cn(
            'inline-flex shrink-0 items-center gap-1.5 rounded-2xl border border-white/15 px-3.5 py-2 text-xs font-bold transition-all cursor-pointer',
            'dark:border-white/10 bg-accent/30 text-muted-foreground hover:border-primary/40 hover:text-primary',
          )}
          title="Add a new layout"
        >
          <Plus size={12} /> New layout
        </button>
      )}
    />
  );
}
