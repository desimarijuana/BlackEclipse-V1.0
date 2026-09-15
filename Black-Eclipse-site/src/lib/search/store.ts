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

/** A pinned (favorite) search entity, stored by stable entity id. */
export interface PinnedEntity {
  id: string;
  title: string;
  symbol?: string;
  kind: string;
  /** Serialized destination so a pin can navigate without re-resolving. */
  tab: string;
  params?: Record<string, string>;
  subtitle?: string;
  pinnedAt: number;
}

/** A visited search entity, used to personalize ranking. */
export interface EntityVisit {
  id: string;
  ts: number;
}

const RECENT_KEY = 'black-eclipse:search-recents';
const PIN_KEY = 'black-eclipse:search-pins';
const VISIT_KEY = 'black-eclipse:search-visits';

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

function loadPins(): PinnedEntity[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(PIN_KEY);
    return raw ? (JSON.parse(raw) as PinnedEntity[]) : [];
  } catch {
    return [];
  }
}

function savePins(list: PinnedEntity[]) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(PIN_KEY, JSON.stringify(list));
  } catch {
    /* ignore quota errors */
  }
}

function loadVisits(): EntityVisit[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(VISIT_KEY);
    return raw ? (JSON.parse(raw) as EntityVisit[]) : [];
  } catch {
    return [];
  }
}

function saveVisits(list: EntityVisit[]) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(VISIT_KEY, JSON.stringify(list));
  } catch {
    /* ignore quota errors */
  }
}

/** Recency multiplier for an entity id from its stored visit history. */
export function visitRecencyScore(visits: EntityVisit[], id: string, max = 1): number {
  const v = visits.find((x) => x.id === id);
  if (!v) return 0;
  const ageMs = Date.now() - v.ts;
  const dayMs = 24 * 3600 * 1000;
  // Full score within a day, decaying to 0 over ~30 days.
  const decay = Math.max(0, 1 - ageMs / (30 * dayMs));
  return decay * max;
}

interface CommandStore {
  open: boolean;
  query: string;
  resolved: ResolvedSearch | null;
  selectedIndex: number;
  recents: RecentQuery[];
  pins: PinnedEntity[];
  /** Recently visited entities, used to personalize ranking. */
  visits: EntityVisit[];
  /** Collapsed group keys in the palette (by EntityKind / section key). */
  collapsedGroups: string[];
  pendingDestination: Destination | null;
  /** Fund id to open in the Portfolio tab (consumed by PortfolioScreen). */
  pendingFundId: string | null;
  /** Market/country code to load into the screener (consumed by MarketOverview). */
  pendingMarket: string | null;
  /**
   * Sub-view request, scoped to a tab: `{ tab, subroute, focus? }`. Consumed by
   * the target screen's `useSubroute` hook. A channel (not a single slot) so a
   * keep-alive screen can subscribe and react even when already mounted, and so
   * two screens never steal each other's request. `seq` makes repeat requests
   * for the same sub-view re-fire.
   */
  pendingSubroute: { tab: string; subroute: string; focus?: string; seq: number } | null;
  /** Monotonic counter behind `pendingSubroute.seq`. */
  subrouteSeq: number;

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
  /** Publish a sub-view request for a tab (shell calls this from `apply`). */
  requestSubroute: (tab: string, subroute: string, focus?: string) => void;
  /** Clear the subroute request for a tab once a screen has applied it. */
  clearSubroute: (tab: string) => void;

  recordRecent: (text: string) => void;
  removeRecent: (text: string) => void;
  clearRecents: () => void;

  // Pins (favorites).
  togglePin: (pin: Omit<PinnedEntity, 'pinnedAt'>) => void;
  isPinned: (id: string) => boolean;
  removePin: (id: string) => void;

  /** Record that an entity was opened (personalizes ranking). */
  recordVisit: (id: string) => void;

  // Palette group collapse.
  toggleGroup: (key: string) => void;
}

export const useCommandStore = create<CommandStore>((set, get) => ({
  open: false,
  query: '',
  resolved: null,
  selectedIndex: 0,
  recents: typeof window !== 'undefined' ? loadRecents() : [],
  pins: typeof window !== 'undefined' ? loadPins() : [],
  visits: typeof window !== 'undefined' ? loadVisits() : [],
  collapsedGroups: [],
  pendingDestination: null,
  pendingFundId: null,
  pendingMarket: null,
  pendingSubroute: null,
  subrouteSeq: 0,

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

  requestSubroute: (tab, subroute, focus) =>
    set((s) => ({
      pendingSubroute: { tab, subroute, focus, seq: s.subrouteSeq + 1 },
      subrouteSeq: s.subrouteSeq + 1,
    })),

  clearSubroute: (tab) =>
    set((s) => (s.pendingSubroute?.tab === tab ? { pendingSubroute: null } : {})),

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

  togglePin: (pin) => {
    const list = get().pins;
    const existing = list.find((p) => p.id === pin.id);
    const next = existing
      ? list.filter((p) => p.id !== pin.id)
      : [{ ...pin, pinnedAt: Date.now() }, ...list].slice(0, 12);
    savePins(next);
    set({ pins: next });
  },

  isPinned: (id) => get().pins.some((p) => p.id === id),

  removePin: (id) => {
    const next = get().pins.filter((p) => p.id !== id);
    savePins(next);
    set({ pins: next });
  },

  toggleGroup: (key) =>
    set((s) => ({
      collapsedGroups: s.collapsedGroups.includes(key)
        ? s.collapsedGroups.filter((k) => k !== key)
        : [...s.collapsedGroups, key],
    })),

  recordVisit: (id) =>
    set((s) => {
      const list = [{ id, ts: Date.now() }, ...s.visits.filter((v) => v.id !== id)].slice(0, 50);
      saveVisits(list);
      return { visits: list };
    }),
}));

export function selectSearchItem(item: SearchItem): Destination | null {
  return item.entity.destination ?? null;
}
