// ── Global command-center store ─────────────────────────────────────────────
// Client-side zustand store bridging the search bar (mounted in the root
// layout) to the SPA shell (stock-chat). Holds overlay open/close, the
// resolved results, keyboard selection, recent queries, and the navigation
// dispatcher. The shell subscribes to `pendingDestination` to change tabs.

'use client';

import { create } from 'zustand';
import type { Destination } from './types';
import type { SearchItem, ResolvedSearch } from './resolver';
import { loadUniverseIndex } from './universe';
import { loadCalendar } from './events';
import { loadGlobalEntities } from './global';

export interface RecentQuery {
  text: string;
  ts: number;
}

const RECENT_KEY = 'black-eclipse:search-recents';

function loadRecents(): RecentQuery[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    return raw ? (JSON.parse(raw) as RecentQuery[]) : [];
  } catch {
    return [];
  }
}

function saveRecents(list: RecentQuery[]) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(list));
  } catch {
    /* ignore quota errors */
  }
}

interface CommandStore {
  open: boolean;
  query: string;
  resolved: ResolvedSearch | null;
  selectedIndex: number;
  recents: RecentQuery[];
  pendingDestination: Destination | null;
  /** Fund id to open in the Portfolio tab (consumed by PortfolioScreen). */
  pendingFundId: string | null;
  /** Market/country code to load into the screener (consumed by MarketOverview). */
  pendingMarket: string | null;

  // Universe index status (Phase 2).
  universeReady: boolean;
  universeLoading: boolean;
  universeError: string | null;

  // Economic calendar status (Phase 5).
  calendarReady: boolean;

  // Server-side global entities (journal/news/reports) status.
  globalReady: boolean;

  // Overlay lifecycle.
  setOpen: (open: boolean) => void;
  toggle: () => void;
  setQuery: (q: string) => void;
  setSelectedIndex: (i: number) => void;
  ensureUniverse: () => void;
  ensureCalendar: () => void;
  ensureGlobal: () => void;

  // Result selection.
  selectResult: (index: number) => void;
  runPrimary: () => void;

  // Navigation dispatcher — the shell consumes this.
  dispatch: (destination: Destination) => void;
  consumeDestination: () => Destination | null;
  consumeFundId: () => string | null;
  consumeMarket: () => string | null;

  recordRecent: (text: string) => void;
  removeRecent: (text: string) => void;
  clearRecents: () => void;
}

export const useCommandStore = create<CommandStore>((set, get) => ({
  open: false,
  query: '',
  resolved: null,
  selectedIndex: 0,
  recents: typeof window !== 'undefined' ? loadRecents() : [],
  pendingDestination: null,
  pendingFundId: null,
  pendingMarket: null,

  universeReady: false,
  universeLoading: false,
  universeError: null,
  calendarReady: false,
  globalReady: false,

  setOpen: (open) => set({ open, selectedIndex: 0 }),
  toggle: () => set((s) => ({ open: !s.open, selectedIndex: 0 })),
  setQuery: (q) => set({ query: q, selectedIndex: 0 }),
  setSelectedIndex: (i) => set({ selectedIndex: i }),

  ensureUniverse: () => {
    const s = get();
    if (s.universeReady || s.universeLoading) return;
    set({ universeLoading: true, universeError: null });
    void loadUniverseIndex()
      .then(() => set({ universeReady: true, universeLoading: false }))
      .catch((err) =>
        set({
          universeLoading: false,
          universeError: err instanceof Error ? err.message : 'failed to load index',
        })
      );
  },

  ensureCalendar: () => {
    if (get().calendarReady) return;
    void loadCalendar().then(() => set({ calendarReady: true }));
  },

  ensureGlobal: () => {
    if (get().globalReady) return;
    void loadGlobalEntities().then(() => set({ globalReady: true }));
  },

  selectResult: (index) => {
    const s = get();
    const item = s.resolved?.items[index];
    if (!item) return;
    const dest = item.entity.destination;
    if (!dest) return;
    s.dispatch(dest);
    s.recordRecent(s.query);
    set({ open: false, query: '', resolved: null, selectedIndex: 0 });
  },

  runPrimary: () => {
    const s = get();
    const r = s.resolved;
    if (!r) return;
    // Prefer the highlighted selection; else the primary action (action intent).
    if (r.items.length > 0 && s.selectedIndex < r.items.length) {
      s.selectResult(s.selectedIndex);
      return;
    }
    const action = r.primaryAction;
    if (action) {
      const dest = action.run({ query: s.query, normalized: s.query.toLowerCase() });
      if (dest) {
        s.dispatch(dest);
        s.recordRecent(s.query);
        set({ open: false, query: '', resolved: null, selectedIndex: 0 });
      }
    }
  },

  dispatch: (destination) => {
    set({ pendingDestination: destination });
  },

  consumeDestination: () => {
    const s = get();
    const d = s.pendingDestination;
    if (d) set({ pendingDestination: null });
    return d;
  },

  consumeFundId: () => {
    const s = get();
    const id = s.pendingFundId;
    if (id) set({ pendingFundId: null });
    return id;
  },

  consumeMarket: () => {
    const s = get();
    const id = s.pendingMarket;
    if (id) set({ pendingMarket: null });
    return id;
  },

  recordRecent: (text) => {
    const t = text.trim();
    if (!t) return;
    const list = [{ text: t, ts: Date.now() }, ...get().recents.filter((r) => r.text !== t)].slice(0, 8);
    saveRecents(list);
    set({ recents: list });
  },

  removeRecent: (text) => {
    const list = get().recents.filter((r) => r.text !== text);
    saveRecents(list);
    set({ recents: list });
  },

  clearRecents: () => {
    saveRecents([]);
    set({ recents: [] });
  },
}));

export function selectSearchItem(item: SearchItem): Destination | null {
  return item.entity.destination ?? null;
}
