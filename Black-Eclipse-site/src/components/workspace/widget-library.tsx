'use client';

// ── WidgetLibrary — searchable, categorized add-widget palette ───────────────
// Reusable across any customizable workspace. Takes the page's widget
// definitions as a prop (no hard-coded registry), so the Command Center, fund
// workspaces, and future pages all share the same library UX.

import React, { useMemo, useState } from 'react';
import { Search, Star, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { WIDGET_CATEGORY_LABEL, type WidgetCategory, type WidgetDefinition } from '@/lib/workspace/widget-def';

const FAV_KEY = 'be_ws_fav_widgets_v1';
const RECENT_KEY = 'be_ws_recent_widgets_v1';

function loadSet(key: string): Set<string> {
  if (typeof window === 'undefined') return new Set();
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return new Set();
    const arr = JSON.parse(raw);
    return new Set(Array.isArray(arr) ? arr : []);
  } catch { return new Set(); }
}

function saveSet(key: string, set: Set<string>) {
  try { localStorage.setItem(key, JSON.stringify([...set])); } catch { /* best effort */ }
}

const CATEGORY_ORDER: WidgetCategory[] = [
  'markets', 'portfolio', 'trading', 'macro', 'news', 'intelligence', 'ai', 'research',
];

export function WidgetLibrary({
  widgets,
  widgetIcon,
  onAdd,
  onClose,
  placed,
}: {
  widgets: WidgetDefinition[];
  widgetIcon: (name: string) => React.ComponentType<{ size?: number; className?: string }>;
  onAdd: (widgetId: string) => void;
  onClose: () => void;
  placed: Set<string>;
}) {
  const [query, setQuery] = useState('');
  const [favorites, setFavorites] = useState<Set<string>>(() => loadSet(FAV_KEY));
  const [recents, setRecents] = useState<string[]>(() => [...loadSet(RECENT_KEY)]);

  const toggleFavorite = (id: string) => {
    setFavorites(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      saveSet(FAV_KEY, next);
      return next;
    });
  };

  const add = (id: string) => {
    onAdd(id);
    setRecents(prev => {
      const next = [id, ...prev.filter(x => x !== id)].slice(0, 8);
      saveSet(RECENT_KEY, new Set(next));
      return next;
    });
  };

  const q = query.trim().toLowerCase();
  const filtered = useMemo(() => {
    if (!q) return widgets;
    return widgets.filter(w =>
      w.label.toLowerCase().includes(q) ||
      w.desc.toLowerCase().includes(q) ||
      w.category.toLowerCase().includes(q));
  }, [q, widgets]);

  const favWidgets = widgets.filter(w => favorites.has(w.id));
  const recentWidgets = recents.map(id => widgets.find(w => w.id === id)).filter(Boolean) as WidgetDefinition[];

  const byCategory = useMemo(() => {
    const map = new Map<WidgetCategory, WidgetDefinition[]>();
    for (const cat of CATEGORY_ORDER) {
      const items = filtered.filter(w => w.category === cat);
      if (items.length) map.set(cat, items);
    }
    return map;
  }, [filtered]);

  return (
    <div className="fixed inset-0 z-40 flex justify-end animate-fade-in" data-nodrag>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <aside className="relative flex w-96 max-w-[90vw] flex-col h-full border-l border-white/15 dark:border-white/10 glass-card-strong shadow-2xl shadow-black/40 animate-slide-in">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border/10">
          <span className="font-serif text-sm font-semibold text-foreground">Add Widget</span>
          <button onClick={onClose} className="rounded-lg p-1 text-muted-foreground hover:text-foreground hover:bg-accent cursor-pointer">
            <X size={14} />
          </button>
        </div>

        {/* Search */}
        <div className="px-4 py-3 border-b border-border/10">
          <div className="flex items-center gap-2 rounded-xl border border-white/10 dark:border-white/10 glass-card-subtle px-3 py-2">
            <Search size={13} className="text-muted-foreground/70 shrink-0" />
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search widgets…"
              className="h-6 flex-1 border-0 bg-transparent outline-none px-0 text-xs text-foreground placeholder:text-muted-foreground/60"
              autoFocus
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto scrollbar-hide p-4 flex flex-col gap-5">
          {/* Favorites */}
          {!q && favWidgets.length > 0 && (
            <section>
              <h4 className="flex items-center gap-1.5 text-[9px] uppercase tracking-widest font-bold text-muted-foreground mb-2">
                <Star size={10} className="text-amber-400" /> Favorites
              </h4>
              <div className="flex flex-col gap-1.5">
                {favWidgets.map(w => <WidgetRow key={w.id} w={w} fav onAdd={add} onToggleFav={toggleFavorite} placed={placed} widgetIcon={widgetIcon} />)}
              </div>
            </section>
          )}

          {/* Recently used */}
          {!q && recentWidgets.length > 0 && (
            <section>
              <h4 className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground mb-2">Recently Used</h4>
              <div className="flex flex-col gap-1.5">
                {recentWidgets.map(w => <WidgetRow key={w.id} w={w} onAdd={add} onToggleFav={toggleFavorite} placed={placed} widgetIcon={widgetIcon} />)}
              </div>
            </section>
          )}

          {/* Categories */}
          {q ? (
            <section>
              <h4 className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground mb-2">Results</h4>
              <div className="flex flex-col gap-1.5">
                {filtered.map(w => <WidgetRow key={w.id} w={w} onAdd={add} onToggleFav={toggleFavorite} placed={placed} widgetIcon={widgetIcon} />)}
              </div>
              {filtered.length === 0 && (
                <p className="text-xs text-muted-foreground/70 italic py-6 text-center">No widgets match “{query}”.</p>
              )}
            </section>
          ) : (
            CATEGORY_ORDER.map(cat => {
              const items = byCategory.get(cat);
              if (!items) return null;
              return (
                <section key={cat}>
                  <h4 className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground mb-2">{WIDGET_CATEGORY_LABEL[cat]}</h4>
                  <div className="flex flex-col gap-1.5">
                    {items.map(w => <WidgetRow key={w.id} w={w} onAdd={add} onToggleFav={toggleFavorite} placed={placed} widgetIcon={widgetIcon} />)}
                  </div>
                </section>
              );
            })
          )}
        </div>
      </aside>
    </div>
  );
}

function WidgetRow({
  w, onAdd, onToggleFav, placed, fav, widgetIcon,
}: {
  w: WidgetDefinition;
  onAdd: (id: string) => void;
  onToggleFav: (id: string) => void;
  placed: Set<string>;
  fav?: boolean;
  widgetIcon: (name: string) => React.ComponentType<{ size?: number; className?: string }>;
}) {
  const Icon = widgetIcon(w.icon);
  return (
    <div className="group flex items-center gap-2 rounded-xl border border-white/10 dark:border-white/10 glass-card-subtle hover:bg-accent/50 hover:border-primary/40 px-3 py-2.5 transition-all">
      <button
        onClick={() => onAdd(w.id)}
        className="flex min-w-0 flex-1 items-center gap-2 text-left cursor-pointer"
      >
        <Icon size={14} className="shrink-0 text-muted-foreground group-hover:text-primary transition-colors" />
        <span className="min-w-0">
          <span className="block text-xs font-bold text-foreground">
            {w.label}
            {placed.has(w.id) && <span className="ml-1.5 text-[9px] font-mono text-emerald-400">placed</span>}
          </span>
          <span className="block text-[10px] text-muted-foreground leading-snug">{w.desc}</span>
        </span>
      </button>
      <button
        onClick={() => onToggleFav(w.id)}
        className={cn('shrink-0 rounded-lg p-1 cursor-pointer transition-colors',
          fav ? 'text-amber-400' : 'text-muted-foreground/40 hover:text-amber-400')}
        title={fav ? 'Remove from favorites' : 'Add to favorites'}
      >
        <Star size={13} fill={fav ? 'currentColor' : 'none'} />
      </button>
    </div>
  );
}
