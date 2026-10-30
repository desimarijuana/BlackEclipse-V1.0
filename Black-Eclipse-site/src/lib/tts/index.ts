// ── Read-aloud (text-to-speech) ─────────────────────────────────────────────
// Public surface for Eclipse's browser-native speech system. v1 uses the Web
// Speech API: free, offline, no keys, no server round-trip, and no transcript
// text leaves the device.

export { tts } from './speech';
export type { SpeakOptions, TtsSnapshot } from './speech';
export { TtsProvider } from './tts-provider';
export { useAutoSpeak, useTts, useTtsState } from './use-tts';
export type { SpeakableMessage, UseTts } from './use-tts';
export { speakableText } from './content';
export { splitForSpeech, toSpeakableText } from './text';
export {
  DEFAULT_TTS_PREFERENCES,
  TTS_STORAGE_KEY,
  useTtsStore,
  type TtsPreferences,
} from './store';
