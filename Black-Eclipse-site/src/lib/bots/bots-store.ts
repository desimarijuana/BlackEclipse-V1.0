// ── Bots workspace store ─────────────────────────────────────────────────────
// One client-side source of truth for the bot list and the selected bot/group,
// shared by the Bots workspace AND the sidebar's bot panel so the two can never
// drift. All reads go through the real automation API; mutations call `hydrate()`
// to refresh from the server (no optimistic invention).

'use client';

import { create } from 'zustand';
import {
  getAutomationStatuses,
  listAutomations,
  type AutomationStatusSummaryView,
  type AutomationView,
} from '@/lib/harness/clients/automation-browser';
import { isBotAutomation } from '@/lib/bots/state';

/** botId → the last execution id whose output the operator has actually seen
 *  in that bot's chat. The sidebar's unread dot is driven by this: a bot has an
 *  unseen message when its latest terminal run is newer than the one recorded
 *  here. Persisted client-side (the repo convention for ephemeral chat UI). */
const SEEN_KEY = 'be_bots_seen_v1';

/** botIds the operator pinned to the top of the sidebar list. Local UI
 *  preference, like the seen ledger — pinning never changes the automation. */
const PINNED_KEY = 'be_bots_pinned_v1';

/** The last successful list + statuses, so Bots paints in MILLISECONDS on a
 *  fresh page load (or while the Python runtime is still cold-starting). The
 *  network hydrate replaces it as soon as it returns; a failed refresh keeps
 *  the cache on screen and surfaces the error banner. */
const CACHE_KEY = 'be_bots_cache_v1';

interface BotsCache {
  bots: AutomationView[];
  statusById: Record<string, AutomationStatusSummaryView>;
}

const EMPTY_CACHE: BotsCache = { bots: [], statusById: {} };

function isCachedBot(value: unknown): value is AutomationView {
  if (!value || typeof value !== 'object') return false;
  const bot = value as Record<string, unknown>;
  return typeof bot.id === 'string' && typeof bot.name === 'string' && typeof bot.state === 'string';
}

function loadBotsCache(): BotsCache {
  if (typeof window === 'undefined') return EMPTY_CACHE;
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return EMPTY_CACHE;
    const parsed = JSON.parse(raw) as { bots?: unknown; statusById?: unknown };
    const bots = Array.isArray(parsed?.bots) ? parsed.bots.filter(isCachedBot).filter(isBotAutomation) : [];
    const statusById: Record<string, AutomationStatusSummaryView> = {};
    if (parsed?.statusById && typeof parsed.statusById === 'object') {
      for (const [id, status] of Object.entries(parsed.statusById as Record<string, unknown>)) {
        if (status && typeof status === 'object') {
          statusById[id] = status as AutomationStatusSummaryView;
        }
      }
    }
    return { bots, statusById };
  } catch {
    return EMPTY_CACHE;
  }
}

let lastCacheJson = '';

function persistBotsCache(bots: AutomationView[], statusById: Record<string, AutomationStatusSummaryView>): void {
  if (typeof window === 'undefined') return;
  try {
    const payload = JSON.stringify({ bots, statusById } satisfies BotsCache);
    // The 20 s poll usually returns identical data; do not rewrite the whole
    // blob (and block the main thread) unless something actually changed.
    if (payload === lastCacheJson) return;
    lastCacheJson = payload;
    localStorage.setItem(CACHE_KEY, payload);
  } catch {
    /* quota / private mode — in-memory only */
  }
}

/** The last successful sweep, read once when the client store is created. */
const initialCache = loadBotsCache();

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

function persistSeenRuns(seenRuns: Record<string, string>): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(SEEN_KEY, JSON.stringify(seenRuns));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

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

/** One in-flight hydrate shared by every caller. The sidebar, the workspace and
 *  action callbacks can all ask at once; they must not each fetch the list and
 *  fan out a status request per bot. */
let hydrateInFlight: Promise<void> | null = null;

/** Bots whose DELETE is still in flight (or already succeeded). Hydrate drops
 *  them, so a concurrent refresh cannot re-add a row the operator just removed. */
const deletedIds = new Set<string>();

interface BotsStore {
  bots: AutomationView[];
  statusById: Record<string, AutomationStatusSummaryView>;
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
  /** Undo a `forget` when the delete request failed (bot must come back). */
  release: (botId: string) => void;
  loading: boolean;
  error: string | null;
  /** True once at least one batched status sweep has succeeded. The sidebar
   *  seeds its unread ledger only after this, so a bot created during this
   *  session still raises a dot for its first run. */
  statusLoaded: boolean;
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
  // Seed synchronously from the last successful sweep: the first Bots render
  // (and a deep link straight to a bot) has the real list and latest runs, so
  // the user sees the workspace immediately while the network refresh runs.
  bots: initialCache.bots,
  statusById: initialCache.statusById,
  seenRuns: {},
  pinnedIds: [],
  loading: initialCache.bots.length === 0,
  error: null,
  statusLoaded: false,
  selectedId: null,
  selectedGroupId: null,
  createOpen: false,
  groupCreateOpen: false,

  markSeen: (botId, runId) => {
    if (!runId || get().seenRuns[botId] === runId) return;
    const seenRuns = { ...get().seenRuns, [botId]: runId };
    persistSeenRuns(seenRuns);
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
    deletedIds.add(botId);
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
    const nextBots = bots.filter((b) => b.id !== botId);
    const nextStatus = Object.fromEntries(Object.entries(statusById).filter(([id]) => id !== botId));
    set({
      bots: nextBots,
      statusById: nextStatus,
      seenRuns: nextSeen,
      pinnedIds: nextPins,
      selectedId: selectedId === botId ? null : selectedId,
    });
    persistBotsCache(nextBots, nextStatus);
  },

  release: (botId) => {
    deletedIds.delete(botId);
  },

  hydrate: () => {
    if (hydrateInFlight) return hydrateInFlight;
    // Load the persisted UI ledgers once, so pins/unread dots survive reloads.
    const seenRuns = seenLoaded ? get().seenRuns : loadSeenRuns();
    const pinnedIds = pinnedLoaded ? get().pinnedIds : loadPinnedIds();
    seenLoaded = true;
    pinnedLoaded = true;
    const seq = ++hydrateSeq;

    const task = (async () => {
      let bots: AutomationView[];
      try {
        bots = (await listAutomations()).filter((b) => isBotAutomation(b) && !deletedIds.has(b.id));
      } catch (err) {
        if (seq !== hydrateSeq) return;
        set({ loading: false, error: err instanceof Error ? err.message : 'failed to load bots' });
        return;
      }
      if (seq !== hydrateSeq) return;

      // Paint the list as soon as it arrives. Statuses drive only the unread dot
      // and the subtitle, so they hydrate in the background instead of holding
      // the whole workspace blank behind N extra round-trips.
      set({ bots, seenRuns, pinnedIds, loading: false, error: null });
      persistBotsCache(bots, get().statusById);
      const sel = get().selectedId;
      if (sel && !bots.some((b) => b.id === sel)) set({ selectedId: null });

      // Fetch the latest run for every bot in ONE request (not one per bot) so a
      // large bot list does not fan out N HTTP round-trips. Statuses drive only
      // the unread dot and subtitle, so a failure keeps the previous map instead
      // of blanking the sidebar.
      try {
        const statusById = await getAutomationStatuses();
        if (seq !== hydrateSeq) return;
        // The FIRST successful status sweep seeds the unread ledger: a bot that
        // already had history when the app opened is not "unread", but a bot
        // created later (or one with no run yet) still raises a dot for its
        // first completed run.
        const firstSweep = !get().statusLoaded;
        let seenRuns = get().seenRuns;
        if (firstSweep) {
          seenRuns = { ...seenRuns };
          for (const bot of get().bots) {
            const last = statusById[bot.id]?.lastExecution;
            if (last && seenRuns[bot.id] === undefined) seenRuns[bot.id] = last.id;
          }
          persistSeenRuns(seenRuns);
        }
        set({ statusById, statusLoaded: true, seenRuns });
        persistBotsCache(get().bots, statusById);
      } catch {
        /* keep the previous statuses; the next hydrate retries */
      }
    })().finally(() => {
      hydrateInFlight = null;
    });

    hydrateInFlight = task;
    return task;
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
