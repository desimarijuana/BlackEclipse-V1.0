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
  DEFAULT_MESSAGE_VARIANT,
  DEFAULT_PACK,
  MESSAGE_VARIANTS,
  SOUND_DEFINITIONS,
  SOUND_PACKS,
  SOUND_NAMES,
  isMessageVariant,
  isSoundName,
  isSoundPackId,
  messageVariantSrc,
  packSoundSrc,
  type MessageVariant,
  type MessageVariantOption,
  type SoundDefinition,
  type SoundName,
  type SoundPack,
  type SoundPackId,
} from './config';
