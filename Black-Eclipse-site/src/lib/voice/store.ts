'use client';

// ── Voice input preferences ────────────────────────────────────────────────
// Client-only zustand store, persisted to localStorage and hydrated after mount
// (same pattern as the sound/TTS stores). These are per-device choices: which
// engine to prefer, language, vocabulary hint and the recording cap. The
// provider/key side is server-owned and lives in JDDS SystemConfig — never here.

import { create } from 'zustand';
import {
  DEFAULT_VOICE_INPUT_PREFERENCES,
  isVoiceEngine,
  type VoiceEngine,
  type VoiceInputPreferences,
} from './types';

export const VOICE_STORAGE_KEY = 'be_voice_input_v1';

function clampSeconds(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_VOICE_INPUT_PREFERENCES.maxSeconds;
  return Math.min(120, Math.max(10, Math.round(value)));
}

function read(): VoiceInputPreferences {
  if (typeof window === 'undefined') return DEFAULT_VOICE_INPUT_PREFERENCES;
  try {
    const raw = localStorage.getItem(VOICE_STORAGE_KEY);
    if (!raw) return DEFAULT_VOICE_INPUT_PREFERENCES;
    const parsed = JSON.parse(raw) as Partial<VoiceInputPreferences>;
    return {
      engine: isVoiceEngine(parsed.engine) ? parsed.engine : 'auto',
      language: typeof parsed.language === 'string' ? parsed.language : '',
      prompt: typeof parsed.prompt === 'string' ? parsed.prompt : DEFAULT_VOICE_INPUT_PREFERENCES.prompt,
      maxSeconds: clampSeconds(
        typeof parsed.maxSeconds === 'number'
          ? parsed.maxSeconds
          : DEFAULT_VOICE_INPUT_PREFERENCES.maxSeconds,
      ),
    };
  } catch {
    return DEFAULT_VOICE_INPUT_PREFERENCES;
  }
}

function persist(value: VoiceInputPreferences) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(VOICE_STORAGE_KEY, JSON.stringify(value));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

export interface VoiceInputStore {
  prefs: VoiceInputPreferences;
  hydrated: boolean;
  hydrate: () => void;
  setEngine: (engine: VoiceEngine) => void;
  setLanguage: (language: string) => void;
  setPrompt: (prompt: string) => void;
  setMaxSeconds: (seconds: number) => void;
  reset: () => void;
}

function commit(set: (patch: Partial<VoiceInputStore>) => void, prefs: VoiceInputPreferences) {
  persist(prefs);
  set({ prefs });
}

export const useVoiceInputStore = create<VoiceInputStore>((set, get) => ({
  prefs: DEFAULT_VOICE_INPUT_PREFERENCES,
  hydrated: false,

  hydrate: () => {
    if (get().hydrated) return;
    set({ prefs: read(), hydrated: true });
  },

  setEngine: (engine) => commit(set, { ...get().prefs, engine }),

  setLanguage: (language) => commit(set, { ...get().prefs, language: language.trim() }),

  setPrompt: (prompt) => commit(set, { ...get().prefs, prompt }),

  setMaxSeconds: (seconds) => commit(set, { ...get().prefs, maxSeconds: clampSeconds(seconds) }),

  reset: () => commit(set, { ...DEFAULT_VOICE_INPUT_PREFERENCES }),
}));
