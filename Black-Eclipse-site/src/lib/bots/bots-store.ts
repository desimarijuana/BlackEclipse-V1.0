// ── Bots workspace store ─────────────────────────────────────────────────────
// One client-side source of truth for the bot list and the selected bot, shared
// by the Bots workspace AND the sidebar's bot panel so the two can never drift.
// All reads go through the real automation API; mutations call `hydrate()` to
// refresh from the server (no optimistic invention).

'use client';

import { create } from 'zustand';
import {
  getAutomationStatus,
  listAutomations,
  type AutomationStatusView,
  type AutomationView,
} from '@/lib/harness/automation-browser';

const MAX_STATUS_FETCH = 60;

interface BotsStore {
  bots: AutomationView[];
  statusById: Record<string, AutomationStatusView>;
  loading: boolean;
  error: string | null;
  selectedId: string | null;
  /** Whether the guided creation panel is open (driven by the header button AND
   *  the sidebar "+"). */
  createOpen: boolean;
  /** Fetch bots + their statuses from the runtime. */
  hydrate: () => Promise<void>;
  /** Select a bot and reflect it in the URL (`?tab=bots&bot=<id>`). */
  select: (id: string | null) => void;
  /** Open the creation panel and clear any selection. */
  openCreate: () => void;
  setCreateOpen: (open: boolean) => void;
}

export const useBotsStore = create<BotsStore>((set, get) => ({
  bots: [],
  statusById: {},
  loading: true,
  error: null,
  selectedId: null,
  createOpen: false,

  hydrate: async () => {
    try {
      const bots = await listAutomations();
      const candidates = bots.filter((b) => b.state === 'active').slice(0, MAX_STATUS_FETCH);
      const results = await Promise.allSettled(candidates.map((b) => getAutomationStatus(b.id)));
      const statusById: Record<string, AutomationStatusView> = {};
      results.forEach((r, i) => {
        if (r.status === 'fulfilled') statusById[candidates[i].id] = r.value;
      });
      set({ bots, statusById, loading: false, error: null });
      // Drop a selection that no longer exists.
      const sel = get().selectedId;
      if (sel && !bots.some((b) => b.id === sel)) set({ selectedId: null });
    } catch (err) {
      set({ loading: false, error: err instanceof Error ? err.message : 'failed to load bots' });
    }
  },

  select: (id) => {
    set({ selectedId: id, ...(id ? { createOpen: false } : {}) });
    if (typeof window === 'undefined') return;
    const url = new URL(window.location.href);
    if (id) url.searchParams.set('bot', id);
    else url.searchParams.delete('bot');
    window.history.replaceState(window.history.state, '', url.toString());
  },

  openCreate: () => {
    set({ createOpen: true, selectedId: null });
    if (typeof window === 'undefined') return;
    const url = new URL(window.location.href);
    url.searchParams.delete('bot');
    window.history.replaceState(window.history.state, '', url.toString());
  },

  setCreateOpen: (open) => set({ createOpen: open }),
}));
