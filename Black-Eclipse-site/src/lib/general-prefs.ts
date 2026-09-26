// ── General preferences (Settings › General) ────────────────────────────────
// Small, presentation-layer preferences that are not part of the server-backed
// `AppPreferences` (market/refresh) nor the theme store (colors/branding).
// Stored in localStorage and read synchronously at boot, matching the currency
// / timezone / sidebar conventions in this repo.
//
//   * `startScreen` — which tab the app opens on when the URL carries no
//     explicit deep link. `history` restores the last visited tab instead.
//   * `confirmDestructive` — require a confirmation before clearing local data.

'use client';

import type { AppTab } from './search/types';

/** The tab shown at boot when there is no explicit deep link. */
export type StartScreen = 'history' | 'chat' | 'dashboard' | 'portfolio' | 'market-workspace';

export interface GeneralPrefs {
  startScreen: StartScreen;
  /** Ask before clearing local data (chats/watchlist/portfolio). */
  confirmDestructive: boolean;
}

export const GENERAL_PREFS_KEY = 'be_general_prefs_v1';
const LAST_TAB_KEY = 'be_last_tab_v1';

export const DEFAULT_GENERAL_PREFS: GeneralPrefs = {
  startScreen: 'chat',
  confirmDestructive: true,
};

export const START_SCREEN_OPTIONS: { id: StartScreen; label: string; hint: string }[] = [
  { id: 'history', label: 'Last screen', hint: 'Resume where you left off' },
  { id: 'chat', label: 'ChatBot', hint: 'The agent' },
  { id: 'dashboard', label: 'Command Center', hint: 'Dashboard widgets' },
  { id: 'portfolio', label: 'Portfolio', hint: 'Holdings & P&L' },
  { id: 'market-workspace', label: 'Chart Workspace', hint: 'Charting workspace' },
];

/** Tabs allowed as a start screen — keeps persisted junk from booting nowhere. */
const START_TABS: readonly AppTab[] = ['chat', 'dashboard', 'portfolio', 'market-workspace'];

function isStartScreen(value: unknown): value is StartScreen {
  return value === 'history' || (typeof value === 'string' && (START_TABS as readonly string[]).includes(value));
}

export function normalizeGeneralPrefs(raw: unknown): GeneralPrefs {
  const value = raw && typeof raw === 'object' && !Array.isArray(raw)
    ? (raw as Record<string, unknown>)
    : {};
  return {
    startScreen: isStartScreen(value.startScreen) ? value.startScreen : DEFAULT_GENERAL_PREFS.startScreen,
    confirmDestructive: value.confirmDestructive !== false,
  };
}

export function loadGeneralPrefs(): GeneralPrefs {
  if (typeof window === 'undefined') return DEFAULT_GENERAL_PREFS;
  try {
    const raw = localStorage.getItem(GENERAL_PREFS_KEY);
    if (!raw) return DEFAULT_GENERAL_PREFS;
    return normalizeGeneralPrefs(JSON.parse(raw));
  } catch {
    return DEFAULT_GENERAL_PREFS;
  }
}

export function saveGeneralPrefs(prefs: GeneralPrefs): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(GENERAL_PREFS_KEY, JSON.stringify(normalizeGeneralPrefs(prefs)));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

/** Record the last visited tab so `startScreen: 'history'` can restore it. */
export function recordLastTab(tab: AppTab): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(LAST_TAB_KEY, tab);
  } catch {
    /* ignore */
  }
}

/**
 * The tab to boot into, given the saved preferences and the last visited tab.
 * Returns null when the caller should fall back to its own default (an explicit
 * URL deep link always wins upstream of this helper).
 */
export function resolveStartTab(prefs: GeneralPrefs = loadGeneralPrefs()): AppTab | null {
  if (prefs.startScreen === 'history') {
    if (typeof window === 'undefined') return null;
    try {
      const last = localStorage.getItem(LAST_TAB_KEY);
      return last && (START_TABS as readonly string[]).includes(last) ? (last as AppTab) : null;
    } catch {
      return null;
    }
  }
  return prefs.startScreen;
}
