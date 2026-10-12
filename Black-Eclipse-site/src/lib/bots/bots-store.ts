// ── Bots workspace store ─────────────────────────────────────────────────────
// One client-side source of truth for the bot list and the selected bot/group,
// shared by the Bots workspace AND the sidebar's bot panel so the two can never
// drift. All reads go through the real automation API; mutations call `hydrate()`
// to refresh from the server (no optimistic invention).

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
  /** The selected bot, or null. Mutual exclusive with `selectedGroupId`. */
  selectedId: string | null;
  /** The selected group chat room, or null. */
  selectedGroupId: string | null;
  /** Whether the New bot dialog is open (driven by the header button AND the
   *  sidebar "+"). */
  createOpen: boolean;
  /** Whether the New group chat dialog is open. */
  groupCreateOpen: boolean;
  /** Fetch bots + their statuses from the runtime. */
  hydrate: () => Promise<void>;
  /** Select a bot and reflect it in the URL (`?tab=bots&bot=<id>`). */
  select: (id: string | null) => void;
  /** Select a group room and reflect it in the URL (`?tab=bots&group=<id>`). */
  selectGroup: (id: string | null) => void;
  /** Open the New bot dialog and clear any selection. */
  openCreate: () => void;
  setCreateOpen: (open: boolean) => void;
  /** Open the New group dialog and clear any selection. */
  openGroupCreate: () => void;
  setGroupCreateOpen: (open: boolean) => void;
}

function setUrlParam(key: string, value: string | null) {
  if (typeof window === 'undefined') return;
  const url = new URL(window.location.href);
  if (value) url.searchParams.set(key, value);
  else url.searchParams.delete(key);
  window.history.replaceState(window.history.state, '', url.toString());
}

export const useBotsStore = create<BotsStore>((set, get) => ({
  bots: [],
  statusById: {},
  loading: true,
  error: null,
  selectedId: null,
  selectedGroupId: null,
  createOpen: false,
  groupCreateOpen: false,

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
    set({ selectedId: id, selectedGroupId: null, ...(id ? { createOpen: false, groupCreateOpen: false } : {}) });
    setUrlParam('bot', id);
    if (id) setUrlParam('group', null);
  },

  selectGroup: (id) => {
    set({ selectedGroupId: id, selectedId: null, ...(id ? { createOpen: false, groupCreateOpen: false } : {}) });
    setUrlParam('group', id);
    if (id) setUrlParam('bot', null);
  },

  openCreate: () => {
    set({ createOpen: true, selectedId: null, selectedGroupId: null });
    setUrlParam('bot', null);
    setUrlParam('group', null);
  },

  setCreateOpen: (open) => set({ createOpen: open }),

  openGroupCreate: () => {
    set({ groupCreateOpen: true, selectedId: null, selectedGroupId: null });
    setUrlParam('bot', null);
    setUrlParam('group', null);
  },

  setGroupCreateOpen: (open) => set({ groupCreateOpen: open }),
}));
