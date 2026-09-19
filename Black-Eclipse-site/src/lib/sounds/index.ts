// ── UI sounds ───────────────────────────────────────────────────────────────
// Public surface for the terminal-style UI feedback system.

export { sound, requestSound } from './sound-manager';
export { SoundProvider } from './sound-provider';
export {
  DEFAULT_SOUND_PREFERENCES,
  SOUND_STORAGE_KEY,
  useSoundStore,
  type SoundPreferences,
} from './store';
export {
  SOUND_DEFINITIONS,
  SOUND_NAMES,
  isSoundName,
  type SoundDefinition,
  type SoundName,
} from './config';
