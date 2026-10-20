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

/** botId → the last execution id whose output the operator has actually seen
 *  in that bot's chat. The sidebar's unread dot is driven by this: a bot has an
 *  unseen message when its latest terminal run is newer than the one recorded
 *  here. Persisted client-side (the repo convention for ephemeral chat UI). */
const SEEN_KEY = 'be_bots_seen_v1';

/** botIds the operator pinned to the top of the sidebar list. Local UI
 *  preference, like the seen ledger — pinning never changes the automation. */
const PINNED_KEY = 'be_bots_pinned_v1';

function loadSeenRuns(): Record<string, string> {
  if (typeof window === 'undefined') return {};
  try {
    const raw = localStorage.getItem(SEEN_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const out: Record<string, string> = {};
    if (parsed && typeof parsed === 'object') {
      for (const [id, runId] of Object.entries(parsed)) if (typeof runId === 'string') out[id] = runId;
    }
    return out;
  } catch {
    return {};
  }
}

let seenLoaded = false;

function loadPinnedIds(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(PINNED_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === 'string') : [];
  } catch {
    return [];
  }
}

let pinnedLoaded = false;

/** Monotonic guard: concurrent hydrates must not let an older response
 *  overwrite a newer one (a stale list could resurrect a just-deleted bot). */
let hydrateSeq = 0;

interface BotsStore {
  bots: AutomationView[];
  statusById: Record<string, AutomationStatusView>;
  /** botId → last seen execution id (drives the unread dot). */
  seenRuns: Record<string, string>;
  /** Record that a bot's latest run has been seen (clears its unread dot). */
  markSeen: (botId: string, runId: string | null) => void;
  /** Pinned bot ids, newest pin first. Pinned bots sort above the rest. */
  pinnedIds: string[];
  /** Pin or unpin a bot (persisted locally, never touches the automation). */
  togglePin: (botId: string) => void;
  /** Drop a deleted bot from the local list immediately. */
  forget: (botId: string) => void;
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
  seenRuns: {},
  pinnedIds: [],
  loading: true,
  error: null,
  selectedId: null,
  selectedGroupId: null,
  createOpen: false,
  groupCreateOpen: false,

  markSeen: (botId, runId) => {
    if (!runId || get().seenRuns[botId] === runId) return;
    const seenRuns = { ...get().seenRuns, [botId]: runId };
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(SEEN_KEY, JSON.stringify(seenRuns));
      } catch {
        /* quota / private mode — in-memory only */
      }
    }
    set({ seenRuns });
  },

  togglePin: (botId) => {
    const current = get().pinnedIds;
    const pinnedIds = current.includes(botId)
      ? current.filter((id) => id !== botId)
      : [botId, ...current];
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PINNED_KEY, JSON.stringify(pinnedIds));
      } catch {
        /* quota / private mode — in-memory only */
      }
    }
    set({ pinnedIds });
  },

  forget: (botId) => {
    const { bots, statusById, seenRuns, pinnedIds, selectedId } = get();
    const nextSeen = { ...seenRuns };
    delete nextSeen[botId];
    const nextPins = pinnedIds.filter((id) => id !== botId);
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(SEEN_KEY, JSON.stringify(nextSeen));
        localStorage.setItem(PINNED_KEY, JSON.stringify(nextPins));
      } catch {
        /* quota / private mode — in-memory only */
      }
    }
    set({
      bots: bots.filter((b) => b.id !== botId),
      statusById: Object.fromEntries(Object.entries(statusById).filter(([id]) => id !== botId)),
      seenRuns: nextSeen,
      pinnedIds: nextPins,
      selectedId: selectedId === botId ? null : selectedId,
    });
  },

  hydrate: async () => {
    // Load the persisted UI ledgers once, so pins/unread dots survive reloads.
    const seenRuns = seenLoaded ? get().seenRuns : loadSeenRuns();
    const pinnedIds = pinnedLoaded ? get().pinnedIds : loadPinnedIds();
    seenLoaded = true;
    pinnedLoaded = true;
    const seq = ++hydrateSeq;
    try {
      const bots = await listAutomations();
      // Fetch status for every bot (not just active ones) so a paused bot with an
      // unseen run still surfaces its dot until the operator opens it.
      const candidates = bots.slice(0, MAX_STATUS_FETCH);
      const results = await Promise.allSettled(candidates.map((b) => getAutomationStatus(b.id)));
      // A newer hydrate finished first — its snapshot is authoritative.
      if (seq !== hydrateSeq) return;
      const statusById: Record<string, AutomationStatusView> = {};
      results.forEach((r, i) => {
        if (r.status === 'fulfilled') statusById[candidates[i].id] = r.value;
      });
      set({ bots, statusById, seenRuns, pinnedIds, loading: false, error: null });
      // Drop a selection that no longer exists.
      const sel = get().selectedId;
      if (sel && !bots.some((b) => b.id === sel)) set({ selectedId: null });
    } catch (err) {
      if (seq !== hydrateSeq) return;
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
