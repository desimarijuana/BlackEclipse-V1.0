// ── Text-to-speech preferences ──────────────────────────────────────────────
// Client-only zustand store for read-aloud settings, persisted to localStorage
// and hydrated after mount — the same shape as the Sound prefs store so SSR
// output stays stable. Read-aloud is device-local: no server round-trip, and no
// transcript text is ever sent anywhere (the browser's own voices do the work).
//
// `enabled` is the master switch. `autoSpeak` is a separate, off-by-default
// opt-in: speaking every reply without being asked is hostile.

'use client';

import { create } from 'zustand';

export const TTS_STORAGE_KEY = 'be_tts_v1';

export interface TtsPreferences {
  /** Master switch for the Speak control. */
  enabled: boolean;
  /** Speak a reply automatically once its turn completes. Off by default. */
  autoSpeak: boolean;
  /** `null` = pick a sensible voice from the system locale. */
  voiceURI: string | null;
  /** 0.5–2. */
  rate: number;
  /** 0–2. */
  pitch: number;
  /** 0–1. */
  volume: number;
}

export const DEFAULT_TTS_PREFERENCES: TtsPreferences = {
  enabled: true,
  autoSpeak: false,
  voiceURI: null,
  rate: 1,
  pitch: 1,
  volume: 0.9,
};

function clamp(value: number, min: number, max: number, fallback: number): number {
  if (!Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, value));
}

function read(): TtsPreferences {
  if (typeof window === 'undefined') return DEFAULT_TTS_PREFERENCES;
  try {
    const raw = localStorage.getItem(TTS_STORAGE_KEY);
    if (!raw) return DEFAULT_TTS_PREFERENCES;
    const parsed = JSON.parse(raw) as Partial<TtsPreferences>;
    return {
      enabled: parsed.enabled !== false,
      autoSpeak: parsed.autoSpeak === true,
      voiceURI: typeof parsed.voiceURI === 'string' && parsed.voiceURI ? parsed.voiceURI : null,
      rate: clamp(
        typeof parsed.rate === 'number' ? parsed.rate : DEFAULT_TTS_PREFERENCES.rate,
        0.5,
        2,
        DEFAULT_TTS_PREFERENCES.rate,
      ),
      pitch: clamp(
        typeof parsed.pitch === 'number' ? parsed.pitch : DEFAULT_TTS_PREFERENCES.pitch,
        0,
        2,
        DEFAULT_TTS_PREFERENCES.pitch,
      ),
      volume: clamp(
        typeof parsed.volume === 'number' ? parsed.volume : DEFAULT_TTS_PREFERENCES.volume,
        0,
        1,
        DEFAULT_TTS_PREFERENCES.volume,
      ),
    };
  } catch {
    return DEFAULT_TTS_PREFERENCES;
  }
}

function persist(value: TtsPreferences) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(TTS_STORAGE_KEY, JSON.stringify(value));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

export interface TtsStore {
  prefs: TtsPreferences;
  hydrated: boolean;
  hydrate: () => void;
  setEnabled: (enabled: boolean) => void;
  setAutoSpeak: (autoSpeak: boolean) => void;
  setVoiceURI: (voiceURI: string | null) => void;
  setRate: (rate: number) => void;
  setPitch: (pitch: number) => void;
  setVolume: (volume: number) => void;
  reset: () => void;
}

function commit(set: (patch: Partial<TtsStore>) => void, prefs: TtsPreferences) {
  persist(prefs);
  set({ prefs });
}

export const useTtsStore = create<TtsStore>((set, get) => ({
  prefs: DEFAULT_TTS_PREFERENCES,
  hydrated: false,

  hydrate: () => {
    if (get().hydrated) return;
    set({ prefs: read(), hydrated: true });
  },

  setEnabled: (enabled) => commit(set, { ...get().prefs, enabled }),

  setAutoSpeak: (autoSpeak) => commit(set, { ...get().prefs, autoSpeak }),

  setVoiceURI: (voiceURI) => commit(set, { ...get().prefs, voiceURI: voiceURI || null }),

  setRate: (rate) =>
    commit(set, { ...get().prefs, rate: clamp(rate, 0.5, 2, DEFAULT_TTS_PREFERENCES.rate) }),

  setPitch: (pitch) =>
    commit(set, { ...get().prefs, pitch: clamp(pitch, 0, 2, DEFAULT_TTS_PREFERENCES.pitch) }),

  setVolume: (volume) =>
    commit(set, { ...get().prefs, volume: clamp(volume, 0, 1, DEFAULT_TTS_PREFERENCES.volume) }),

  reset: () => commit(set, { ...DEFAULT_TTS_PREFERENCES }),
}));
