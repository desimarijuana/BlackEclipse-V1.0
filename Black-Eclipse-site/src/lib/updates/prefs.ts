// Client-side update preferences. Local-only, like the other presentation
// prefs: the update check must never introduce an account, install id, or
// server-side user record. "Off" simply means the banner never calls
// /api/updates.

'use client';

export interface UpdatePrefs {
  /** Show the in-app "update available" notice. */
  enabled: boolean;
  /** Version the user closed with the X. */
  dismissedVersion: string | null;
  /** Version the user explicitly skipped ("don't tell me about this one"). */
  skippedVersion: string | null;
}

export const UPDATE_PREFS_KEY = 'be_update_prefs_v1';
export const UPDATE_PREFS_EVENT = 'be:update-prefs';

export const DEFAULT_UPDATE_PREFS: UpdatePrefs = {
  enabled: true,
  dismissedVersion: null,
  skippedVersion: null,
};

export function normalizeUpdatePrefs(raw: unknown): UpdatePrefs {
  const value =
    raw && typeof raw === 'object' && !Array.isArray(raw)
      ? (raw as Record<string, unknown>)
      : {};
  return {
    enabled: value.enabled !== false,
    dismissedVersion:
      typeof value.dismissedVersion === 'string' ? value.dismissedVersion : null,
    skippedVersion:
      typeof value.skippedVersion === 'string' ? value.skippedVersion : null,
  };
}

export function loadUpdatePrefs(): UpdatePrefs {
  if (typeof window === 'undefined') return DEFAULT_UPDATE_PREFS;
  try {
    const raw = localStorage.getItem(UPDATE_PREFS_KEY);
    if (!raw) return DEFAULT_UPDATE_PREFS;
    return normalizeUpdatePrefs(JSON.parse(raw));
  } catch {
    return DEFAULT_UPDATE_PREFS;
  }
}

export function saveUpdatePrefs(prefs: UpdatePrefs): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(UPDATE_PREFS_KEY, JSON.stringify(normalizeUpdatePrefs(prefs)));
  } catch {
    /* quota / private mode — in-memory only */
  }
  window.dispatchEvent(new CustomEvent(UPDATE_PREFS_EVENT));
}

/** Keep two mounted surfaces (banner + Settings) in sync without a store. */
export function subscribeUpdatePrefs(listener: () => void): () => void {
  if (typeof window === 'undefined') return () => {};
  window.addEventListener(UPDATE_PREFS_EVENT, listener);
  window.addEventListener('storage', listener);
  return () => {
    window.removeEventListener(UPDATE_PREFS_EVENT, listener);
    window.removeEventListener('storage', listener);
  };
}
