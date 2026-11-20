'use client';

// ── News notification preferences ───────────────────────────────────────────
// Client-side controls for the root-mounted `NewsAlertWatcher` — the delivery
// half of high-impact news. The server policy (Settings › Alerts › High-impact
// news alerts) decides WHICH stories are pulled into the channel push lanes;
// these prefs decide what THIS app shows while it is open.
//
// Every switch is honoured individually: a user can keep the header ledger
// (bell + badge) recording without a toast, desktop notification or sound. The
// store is persisted to localStorage and hydrated after mount so SSR output
// stays stable, mirroring the sound/locale stores.

import { create } from 'zustand';

export const NEWS_NOTIFY_STORAGE_KEY = 'be_news_notify_v1';

/** 55 = all high/critical, 65 = strong high, 75 = critical only. */
export type NewsNotifyMinScore = 55 | 65 | 75;

export const NEWS_NOTIFY_MIN_SCORES: readonly NewsNotifyMinScore[] = [55, 65, 75];

export interface NewsNotificationPrefs {
  /** Background watch on/off. Off stops polling entirely (no ledger entries). */
  enabled: boolean;
  /** In-app pop-up card (bottom-right toast). */
  popup: boolean;
  /** Native OS notification; still requires the global desktop opt-in. */
  desktop: boolean;
  /** The alert cue (`notification`) when a story arrives. */
  sound: boolean;
  /** Upcoming high-impact economic releases, not just published stories. */
  includeReleases: boolean;
  /** Only stories tagged with a watchlist ticker. */
  watchlistOnly: boolean;
  /** Minimum deterministic importance score. */
  minScore: NewsNotifyMinScore;
}

export const DEFAULT_NEWS_NOTIFICATION_PREFS: NewsNotificationPrefs = {
  // Preserve the previous always-on watcher by default; every delivery lane
  // can be switched off individually below.
  enabled: true,
  popup: true,
  desktop: true,
  sound: true,
  includeReleases: true,
  watchlistOnly: false,
  minScore: 55,
};

function isMinScore(value: unknown): value is NewsNotifyMinScore {
  return value === 55 || value === 65 || value === 75;
}

function read(): NewsNotificationPrefs {
  if (typeof window === 'undefined') return DEFAULT_NEWS_NOTIFICATION_PREFS;
  try {
    const raw = window.localStorage.getItem(NEWS_NOTIFY_STORAGE_KEY);
    if (!raw) return DEFAULT_NEWS_NOTIFICATION_PREFS;
    const parsed = JSON.parse(raw) as Partial<NewsNotificationPrefs>;
    return {
      enabled: parsed.enabled !== false,
      popup: parsed.popup !== false,
      desktop: parsed.desktop !== false,
      sound: parsed.sound !== false,
      includeReleases: parsed.includeReleases !== false,
      watchlistOnly: parsed.watchlistOnly === true,
      minScore: isMinScore(parsed.minScore) ? parsed.minScore : DEFAULT_NEWS_NOTIFICATION_PREFS.minScore,
    };
  } catch {
    return DEFAULT_NEWS_NOTIFICATION_PREFS;
  }
}

function persist(prefs: NewsNotificationPrefs): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(NEWS_NOTIFY_STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

export interface NewsNotificationStore {
  prefs: NewsNotificationPrefs;
  hydrated: boolean;
  hydrate: () => void;
  update: (patch: Partial<NewsNotificationPrefs>) => void;
  reset: () => void;
}

export const useNewsNotificationPrefs = create<NewsNotificationStore>((set, get) => ({
  prefs: DEFAULT_NEWS_NOTIFICATION_PREFS,
  hydrated: false,

  hydrate: () => {
    if (get().hydrated) return;
    set({ prefs: read(), hydrated: true });
  },

  update: (patch) => {
    const next: NewsNotificationPrefs = { ...get().prefs, ...patch };
    if (!isMinScore(next.minScore)) next.minScore = DEFAULT_NEWS_NOTIFICATION_PREFS.minScore;
    persist(next);
    set({ prefs: next });
  },

  reset: () => {
    persist(DEFAULT_NEWS_NOTIFICATION_PREFS);
    set({ prefs: DEFAULT_NEWS_NOTIFICATION_PREFS });
  },
}));

/** Watchlist symbols — the same storage the Watchlist screen and News tab read. */
export function readNewsWatchlist(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem('watchlist_guest') || '[]');
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((w: { symbol?: string }) => String(w?.symbol || '').toUpperCase())
      .filter(Boolean)
      .slice(0, 100);
  } catch {
    return [];
  }
}
