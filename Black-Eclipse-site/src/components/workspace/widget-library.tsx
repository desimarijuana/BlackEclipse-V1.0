'use client';

// ── WidgetLibrary — searchable, categorized add-widget palette ───────────────
// Reusable across any customizable workspace. Takes the page's widget
// definitions as a prop (no hard-coded registry), so the Command Center, fund
// workspaces, and future pages all share the same library UX.

import React, { useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Search, Star, X } from '@/lib/icons';
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
  'markets', 'portfolio', 'trading', 'macro', 'news', 'intelligence', 'ai', 'research', 'tools', 'geopolitics', 'alerts', 'journal',
];

export function WidgetLibrary({
  widgets,
  widgetIcon,
  onAdd,
  onClose,
  placed,
  onStartAddDrag,
  dragActive = false,
}: {
  widgets: WidgetDefinition[];
  widgetIcon: (name: string) => React.ComponentType<{ size?: number; className?: string }>;
  onAdd: (widgetId: string) => void;
  onClose: () => void;
  placed: Set<string>;
  /** Begin adding a widget: 'hold' = press-drag-release, 'click' = project then double-click. */
  onStartAddDrag?: (widgetId: string, label: string, mode: 'hold' | 'click') => void;
  /** True while an add-drag is in flight — the palette becomes click-through. */
  dragActive?: boolean;
}) {
  const [query, setQuery] = useState('');
  const [favorites, setFavorites] = useState<Set<string>>(() => loadSet(FAV_KEY));
  const [recents, setRecents] = useState<string[]>(() => [...loadSet(RECENT_KEY)]);
  // Portal target — drawers must render at <body> so their backdrop-filter
  // samples the real page. Inside the page tree they sit under transformed
  // ancestors (animate-fade-in-up) which scope/backdrop-root the blur away.
  const [mounted, setMounted] = useState(false);
  React.useEffect(() => setMounted(true), []);

  const toggleFavorite = (id: string) => {
    setFavorites(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      saveSet(FAV_KEY, next);
      return next;
    });
  };

  const begin = (id: string, label: string, mode: 'hold' | 'click') => {
    // Remember it as recently used the moment the user interacts with it.
    setRecents(prev => {
      const next = [id, ...prev.filter(x => x !== id)].slice(0, 8);
      saveSet(RECENT_KEY, new Set(next));
      return next;
    });
    if (onStartAddDrag) onStartAddDrag(id, label, mode);
    else if (mode === 'click') onAdd(id); // fallback when no canvas is wired
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

  const drawer = (
    <div className={cn('fixed inset-0 z-40 flex justify-end', dragActive && 'pointer-events-none')} data-nodrag data-keyboard-overlay="true">
      <div className={cn('absolute inset-0 transition-colors animate-fade-in', dragActive ? 'bg-transparent' : 'bg-black/20')} onClick={onClose} />
      <aside className={cn('relative flex w-96 max-w-[90vw] flex-col h-full glass-drawer shadow-2xl shadow-black/40 animate-slide-in transition-opacity', dragActive && 'opacity-70')}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-border/10">
          <span className="font-serif text-sm font-semibold text-foreground">Add Widget</span>
          <button onClick={onClose} className="rounded-lg p-1 text-muted-foreground hover:text-foreground hover:bg-accent cursor-pointer">
            <X size={14} />
          </button>
        </div>

        {/* Search */}
        <div className="px-4 py-3 border-b border-border/10">
          <div className="flex items-center gap-2 rounded-xl glass-card-subtle px-3 py-2">
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
                {favWidgets.map(w => <WidgetRow key={w.id} w={w} fav onBegin={begin} onToggleFav={toggleFavorite} placed={placed} widgetIcon={widgetIcon} />)}
              </div>
            </section>
          )}

          {/* Recently used */}
          {!q && recentWidgets.length > 0 && (
            <section>
              <h4 className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground mb-2">Recently Used</h4>
              <div className="flex flex-col gap-1.5">
                {recentWidgets.map(w => <WidgetRow key={w.id} w={w} onBegin={begin} onToggleFav={toggleFavorite} placed={placed} widgetIcon={widgetIcon} />)}
              </div>
            </section>
          )}

          {/* Categories */}
          {q ? (
            <section>
              <h4 className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground mb-2">Results</h4>
              <div className="flex flex-col gap-1.5">
                {filtered.map(w => <WidgetRow key={w.id} w={w} onBegin={begin} onToggleFav={toggleFavorite} placed={placed} widgetIcon={widgetIcon} />)}
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
                    {items.map(w => <WidgetRow key={w.id} w={w} onBegin={begin} onToggleFav={toggleFavorite} placed={placed} widgetIcon={widgetIcon} />)}
                  </div>
                </section>
              );
            })
          )}
        </div>
      </aside>
    </div>
  );

  if (!mounted) return null;
  return createPortal(drawer, document.body);
}

function WidgetRow({
  w, onBegin, onToggleFav, placed, fav, widgetIcon,
}: {
  w: WidgetDefinition;
  onBegin: (id: string, label: string, mode: 'hold' | 'click') => void;
  onToggleFav: (id: string) => void;
  placed: Set<string>;
  fav?: boolean;
  widgetIcon: (name: string) => React.ComponentType<{ size?: number; className?: string }>;
}) {
  const Icon = widgetIcon(w.icon);
  // Two add modes:
  //  - hold  → press and move past a small threshold starts a drag-and-drop
  //  - click → a click (no movement) starts "project" mode (double-click place)
  const dragRef = useRef<{ x: number; y: number; active: boolean } | null>(null);

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    dragRef.current = { x: e.clientX, y: e.clientY, active: false };
    const onMove = (ev: PointerEvent) => {
      const d = dragRef.current;
      if (!d || d.active) return;
      if (Math.hypot(ev.clientX - d.x, ev.clientY - d.y) > 5) {
        d.active = true;
        onBegin(w.id, w.label, 'hold');
      }
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      // Keep `active` around until the click event (if any) fires so it can be suppressed.
      window.setTimeout(() => { dragRef.current = null; }, 0);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  return (
    <div className="group flex items-center gap-2 rounded-xl glass-card-subtle hover:bg-accent/50 px-3 py-2.5 transition-all">
      <button
        onPointerDown={onPointerDown}
        onClick={() => { if (dragRef.current?.active) return; onBegin(w.id, w.label, 'click'); }}
        className="flex min-w-0 flex-1 items-center gap-2 text-left cursor-pointer"
        title="Click to project, then double-click to place · or hold and drag"
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
        <Star size={13} weight={fav ? 'fill' : 'regular'} />
      </button>
    </div>
  );
}
