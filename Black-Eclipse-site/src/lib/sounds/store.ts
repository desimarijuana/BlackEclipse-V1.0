// ── UI sound preferences ────────────────────────────────────────────────────
// Client-only zustand store for the "UI Sounds" settings, persisted to
// localStorage and hydrated after mount — mirroring the locale/a11y and
// sidebar stores so SSR output stays stable. Interaction audio (the click /
// tick / toggle "haptics") is **opt-in**: defaults are OFF at 12% volume on the
// Eclipse pack. Event-notification cues (AI result, alert, task done) are
// controlled per-cue and play independently — see `SOUND_DEFINITIONS`.
//
// Customization model:
//   * One active voice `pack`.
//   * Per-cue `volume` multiplier (layered over the master volume).
//   * Per-cue `muted` toggle.
//   * Per-cue `custom` data-URL override (user-uploaded audio), which takes
//     precedence over the pack asset. Kept small and stored in localStorage.
//
// Storage is versioned: the key is bumped to `_v4` so the corrected opt-in
// defaults are not masked by a stored configuration written while interaction
// audio could be re-enabled implicitly.

'use client';

import { create } from 'zustand';
import {
  DEFAULT_PACK,
  SOUND_NAMES,
  isSoundPackId,
  type SoundName,
  type SoundPackId,
} from './config';

// v4: interaction audio is now strictly opt-in (a stored blob without an
// explicit `enabled: true` must not turn the click/tick "haptics" back on), and
// event-notification cues are independent of that master switch. Bumping the
// key retires any older configuration so the corrected defaults apply exactly
// once instead of being masked by a stale `enabled` value.
export const SOUND_STORAGE_KEY = 'be_sounds_v4';

/**
 * Sound modes:
 * - `all`       — every cue (navigation, actions, toggles, alerts).
 * - `essential` — only direct-interaction cues (click/tick/toggle).
 */
export type SoundMode = 'all' | 'essential';

export interface SoundCueSettings {
  /** Per-cue gain multiplier, 0–2 (1 = the definition default). */
  volume: number;
  muted: boolean;
  /** Optional user-uploaded audio as a data URL; overrides the pack asset. */
  custom?: string;
}

export interface SoundPreferences {
  enabled: boolean;
  /** Master volume, 0–1. */
  volume: number;
  mode: SoundMode;
  pack: SoundPackId;
  cues: Record<SoundName, SoundCueSettings>;
}

function defaultCue(name?: SoundName): SoundCueSettings {
  // The task-done alarm is opt-in: it is an event notification, but it is also
  // the loudest cue and was the one users experienced as "always on". AI-result
  // and alert cues stay enabled by default (the explicit ask), while task-done
  // must be switched on. Volume/mute remain independently editable.
  return { volume: 1, muted: name === 'taskdone' };
}

function defaultCues(): Record<SoundName, SoundCueSettings> {
  const cues = {} as Record<SoundName, SoundCueSettings>;
  for (const n of SOUND_NAMES) cues[n] = defaultCue(n);
  return cues;
}

export const DEFAULT_SOUND_PREFERENCES: SoundPreferences = {
  // Off by default — UI audio is opt-in. When enabled it starts quiet (12%),
  // subtle but clearly present over a terminal-scale interaction.
  enabled: false,
  volume: 0.12,
  mode: 'all',
  pack: DEFAULT_PACK,
  cues: defaultCues(),
};

function clamp(v: number, min: number, max: number, fallback: number): number {
  if (!Number.isFinite(v)) return fallback;
  return Math.min(max, Math.max(min, v));
}

function readCues(raw: unknown): Record<SoundName, SoundCueSettings> {
  const out = defaultCues();
  if (!raw || typeof raw !== 'object') return out;
  const rec = raw as Record<string, unknown>;
  for (const name of SOUND_NAMES) {
    const c = rec[name];
    if (!c || typeof c !== 'object') continue;
    const cc = c as Partial<SoundCueSettings>;
    out[name] = {
      volume: clamp(typeof cc.volume === 'number' ? cc.volume : 1, 0, 2, 1),
      muted: cc.muted === true,
      custom: typeof cc.custom === 'string' && cc.custom.startsWith('data:') ? cc.custom : undefined,
    };
  }
  return out;
}

function read(): SoundPreferences {
  if (typeof window === 'undefined') return DEFAULT_SOUND_PREFERENCES;
  try {
    const raw = localStorage.getItem(SOUND_STORAGE_KEY);
    if (!raw) return DEFAULT_SOUND_PREFERENCES;
    const parsed = JSON.parse(raw) as Partial<SoundPreferences>;
    return {
      // Strict opt-in: a stored blob without an explicit `true` must NOT
      // re-enable interaction audio (that was the "haptics are on by default"
      // bug after a partial/legacy write).
      enabled: parsed.enabled === true,
      volume: clamp(typeof parsed.volume === 'number' ? parsed.volume : DEFAULT_SOUND_PREFERENCES.volume, 0, 1, DEFAULT_SOUND_PREFERENCES.volume),
      mode: parsed.mode === 'essential' ? 'essential' : 'all',
      pack: isSoundPackId(parsed.pack) ? parsed.pack : DEFAULT_PACK,
      cues: readCues(parsed.cues),
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
  setMode: (mode: SoundMode) => void;
  setPack: (pack: SoundPackId) => void;
  setCueVolume: (name: SoundName, volume: number) => void;
  setCueMuted: (name: SoundName, muted: boolean) => void;
  setCueCustom: (name: SoundName, dataUrl: string | undefined) => void;
  resetCue: (name: SoundName) => void;
  reset: () => void;
}

function commit(set: (p: Partial<SoundStore>) => void, prefs: SoundPreferences) {
  persist(prefs);
  set({ prefs });
}

export const useSoundStore = create<SoundStore>((set, get) => ({
  prefs: DEFAULT_SOUND_PREFERENCES,
  hydrated: false,

  hydrate: () => {
    if (get().hydrated) return;
    set({ prefs: read(), hydrated: true });
  },

  setEnabled: (enabled) => commit(set, { ...get().prefs, enabled }),

  setVolume: (volume) =>
    commit(set, { ...get().prefs, volume: clamp(volume, 0, 1, DEFAULT_SOUND_PREFERENCES.volume) }),

  setMode: (mode) => commit(set, { ...get().prefs, mode }),

  setPack: (pack) => commit(set, { ...get().prefs, pack }),

  setCueVolume: (name, volume) => {
    const prefs = get().prefs;
    const cues = { ...prefs.cues, [name]: { ...prefs.cues[name], volume: clamp(volume, 0, 2, 1) } };
    commit(set, { ...prefs, cues });
  },

  setCueMuted: (name, muted) => {
    const prefs = get().prefs;
    const cues = { ...prefs.cues, [name]: { ...prefs.cues[name], muted } };
    commit(set, { ...prefs, cues });
  },

  setCueCustom: (name, dataUrl) => {
    const prefs = get().prefs;
    const cues = {
      ...prefs.cues,
      [name]: { ...prefs.cues[name], custom: dataUrl && dataUrl.startsWith('data:') ? dataUrl : undefined },
    };
    commit(set, { ...prefs, cues });
  },

  resetCue: (name) => {
    const prefs = get().prefs;
    const cues = { ...prefs.cues, [name]: defaultCue() };
    commit(set, { ...prefs, cues });
  },

  reset: () => commit(set, { ...DEFAULT_SOUND_PREFERENCES, cues: defaultCues() }),
}));
