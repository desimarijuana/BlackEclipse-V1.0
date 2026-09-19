// ── UI sound preferences ────────────────────────────────────────────────────
// Client-only zustand store for the "UI Sounds" setting, persisted to
// localStorage and hydrated after mount — mirroring the locale/a11y and
// sidebar stores so SSR output stays stable. Defaults to ON at a low volume.

'use client';

import { create } from 'zustand';

export const SOUND_STORAGE_KEY = 'be_sounds_v1';

export interface SoundPreferences {
  enabled: boolean;
  /** Master volume, 0–1. */
  volume: number;
}

export const DEFAULT_SOUND_PREFERENCES: SoundPreferences = {
  enabled: true,
  volume: 0.35,
};

function clampVolume(v: number): number {
  if (!Number.isFinite(v)) return DEFAULT_SOUND_PREFERENCES.volume;
  return Math.min(1, Math.max(0, v));
}

function read(): SoundPreferences {
  if (typeof window === 'undefined') return DEFAULT_SOUND_PREFERENCES;
  try {
    const raw = localStorage.getItem(SOUND_STORAGE_KEY);
    if (!raw) return DEFAULT_SOUND_PREFERENCES;
    const parsed = JSON.parse(raw) as Partial<SoundPreferences>;
    return {
      enabled: parsed.enabled !== false,
      volume: clampVolume(typeof parsed.volume === 'number' ? parsed.volume : DEFAULT_SOUND_PREFERENCES.volume),
    };
  } catch {
    return DEFAULT_SOUND_PREFERENCES;
  }
}

function persist(value: SoundPreferences) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(SOUND_STORAGE_KEY, JSON.stringify(value));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

export interface SoundStore {
  prefs: SoundPreferences;
  hydrated: boolean;
  hydrate: () => void;
  setEnabled: (enabled: boolean) => void;
  setVolume: (volume: number) => void;
}

export const useSoundStore = create<SoundStore>((set, get) => ({
  // SSR-consistent defaults; real values load on mount (no hydration mismatch).
  prefs: DEFAULT_SOUND_PREFERENCES,
  hydrated: false,

  hydrate: () => {
    if (get().hydrated) return;
    set({ prefs: read(), hydrated: true });
  },

  setEnabled: (enabled) => {
    const next = { ...get().prefs, enabled };
    persist(next);
    set({ prefs: next });
  },

  setVolume: (volume) => {
    const next = { ...get().prefs, volume: clampVolume(volume) };
    persist(next);
    set({ prefs: next });
  },
}));
