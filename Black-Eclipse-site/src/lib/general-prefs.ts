// ── General preferences (Settings › General) ────────────────────────────────
// Small, presentation-layer preferences that are not part of the server-backed
// `AppPreferences` (market/refresh) nor the theme store (colors/branding).
// Stored in localStorage and read synchronously, matching the currency /
// timezone / sidebar conventions in this repo.
//
//   * `confirmDestructive` — require a confirmation before clearing local data.
//
// The app always boots on the Eclipse Agent page (chat); an explicit URL deep
// link is the only way to open another screen directly. There is no saved
// "start screen" preference. An older `startScreen` key in stored JSON is
// ignored by `normalizeGeneralPrefs`, so existing installs keep working.

'use client';

export interface GeneralPrefs {
  /** Ask before clearing local data (chats/watchlist/portfolio). */
  confirmDestructive: boolean;
}

export const GENERAL_PREFS_KEY = 'be_general_prefs_v1';

export const DEFAULT_GENERAL_PREFS: GeneralPrefs = {
  confirmDestructive: true,
};

export function normalizeGeneralPrefs(raw: unknown): GeneralPrefs {
  const value = raw && typeof raw === 'object' && !Array.isArray(raw)
    ? (raw as Record<string, unknown>)
    : {};
  return {
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
