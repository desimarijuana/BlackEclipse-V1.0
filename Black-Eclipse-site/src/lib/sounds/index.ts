// ── UI sounds ───────────────────────────────────────────────────────────────
// Public surface for the terminal-style UI feedback system.

export { sound, requestSound } from './sound-manager';
export { SoundProvider } from './sound-provider';
export {
  DEFAULT_SOUND_PREFERENCES,
  SOUND_STORAGE_KEY,
  useSoundStore,
  type SoundMode,
  type SoundCueSettings,
  type SoundPreferences,
} from './store';
export {
  DEFAULT_PACK,
  SOUND_DEFINITIONS,
  SOUND_PACKS,
  SOUND_NAMES,
  isSoundName,
  isSoundPackId,
  packSoundSrc,
  type SoundDefinition,
  type SoundName,
  type SoundPack,
  type SoundPackId,
} from './config';
