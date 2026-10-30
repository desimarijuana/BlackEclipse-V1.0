// ── Read-aloud engine ───────────────────────────────────────────────────────
// The ONE `speechSynthesis` wrapper. Browser voices are free, offline and
// require no keys, which is why v1 is browser-native. This module owns the
// browser quirks so no component has to:
//
//   * only one reply is spoken at a time (speaking another cancels the first);
//   * long prose is chunked (Chrome truncates long utterances);
//   * `voiceschanged` is async (voices are not ready on first paint);
//   * stale `onend` callbacks from a cancelled utterance cannot flip the UI;
//   * unavailable environments are reported honestly (never a silent no-op).
//
// It is deliberately not React-aware. Components subscribe through
// `useSyncExternalStore` in `use-tts.ts`.

import { splitForSpeech } from './text';

export interface TtsSnapshot {
  /** The Web Speech API exists in this browser. */
  available: boolean;
  /** The key of the reply currently being spoken, or null when idle. */
  speakingKey: string | null;
  paused: boolean;
}

export interface SpeakOptions {
  voiceURI?: string | null;
  rate?: number;
  pitch?: number;
  volume?: number;
}

type Listener = () => void;

const IDLE: TtsSnapshot = { available: false, speakingKey: null, paused: false };

function speechSynthesisApi(): SpeechSynthesis | null {
  if (typeof window === 'undefined') return null;
  const api = window.speechSynthesis;
  return api && typeof window.SpeechSynthesisUtterance !== 'undefined' ? api : null;
}

class TtsEngine {
  private listeners = new Set<Listener>();
  private snapshot: TtsSnapshot = { available: false, speakingKey: null, paused: false };
  /** Bumped on every stop/new speak so late callbacks from a prior run no-op. */
  private generation = 0;
  private voicesCache: SpeechSynthesisVoice[] | null = null;
  private voicesPromise: Promise<SpeechSynthesisVoice[]> | null = null;

  constructor() {
    this.snapshot = { ...this.snapshot, available: speechSynthesisApi() !== null };
  }

  // Stable arrow properties: `useSyncExternalStore` re-subscribes forever if
  // these identities change between renders.
  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  getSnapshot = (): TtsSnapshot => this.snapshot;

  getServerSnapshot = (): TtsSnapshot => IDLE;

  private set(patch: Partial<TtsSnapshot>) {
    const next = { ...this.snapshot, ...patch };
    if (
      next.available === this.snapshot.available &&
      next.speakingKey === this.snapshot.speakingKey &&
      next.paused === this.snapshot.paused
    ) {
      return;
    }
    this.snapshot = next;
    for (const listener of this.listeners) listener();
  }

  /** Voices are populated asynchronously and change after first paint. */
  loadVoices(): Promise<SpeechSynthesisVoice[]> {
    if (this.voicesPromise) return this.voicesPromise;
    const api = speechSynthesisApi();
    if (!api) {
      this.voicesPromise = Promise.resolve([]);
      return this.voicesPromise;
    }

    this.voicesPromise = new Promise((resolve) => {
      const settle = (): boolean => {
        const voices = api.getVoices();
        if (voices.length === 0) return false;
        this.voicesCache = voices;
        resolve(voices);
        return true;
      };
      if (settle()) return;

      const onChange = () => {
        if (settle()) api.removeEventListener('voiceschanged', onChange);
      };
      api.addEventListener('voiceschanged', onChange);

      // Some browsers never fire the event; resolve with whatever exists so the
      // settings pane can say "no voices" instead of spinning forever.
      setTimeout(() => {
        api.removeEventListener('voiceschanged', onChange);
        const voices = api.getVoices();
        if (voices.length > 0) this.voicesCache = voices;
        resolve(voices);
      }, 1200);
    });
    return this.voicesPromise;
  }

  voices(): SpeechSynthesisVoice[] {
    if (this.voicesCache) return this.voicesCache;
    const api = speechSynthesisApi();
    return api ? api.getVoices() : [];
  }

  private pickVoice(voiceURI?: string | null): SpeechSynthesisVoice | null {
    const voices = this.voices();
    if (voices.length === 0) return null;
    if (voiceURI) {
      const exact = voices.find((voice) => voice.voiceURI === voiceURI);
      if (exact) return exact;
    }
    const navigatorLang =
      (typeof navigator !== 'undefined' && navigator.language) || 'en-US';
    const base = navigatorLang.split('-')[0].toLowerCase();
    return (
      voices.find((voice) => voice.lang === navigatorLang) ??
      voices.find((voice) => voice.lang.toLowerCase().startsWith(base)) ??
      voices.find((voice) => voice.default) ??
      voices[0]
    );
  }

  /**
   * Speak `text` under `key` (a message/response id used by the UI to show the
   * Stop state on the right control). Returns false when nothing was queued.
   */
  speak(key: string, text: string, options: SpeakOptions = {}): boolean {
    const api = speechSynthesisApi();
    if (!api) return false;
    // Two transcript mounts can observe the same completed turn (main chat and
    // the floating dock). The second auto-speak call is the same reply, not a
    // request to restart it.
    if (this.snapshot.speakingKey === key && api.speaking) return true;

    const chunks = splitForSpeech(text, CHUNK_LIMIT);
    if (chunks.length === 0) return false;

    this.halt();
    const generation = this.generation;
    const voice = this.pickVoice(options.voiceURI);
    const rate = clamp(options.rate ?? 1, 0.5, 2);
    const pitch = clamp(options.pitch ?? 1, 0, 2);
    const volume = clamp(options.volume ?? 1, 0, 1);

    this.set({ speakingKey: key, paused: false });

    let index = 0;
    const speakNext = () => {
      if (generation !== this.generation) return;
      if (index >= chunks.length) {
        this.set({ speakingKey: null, paused: false });
        return;
      }

      const utterance = new SpeechSynthesisUtterance(chunks[index]);
      index += 1;
      if (voice) utterance.voice = voice;
      else utterance.lang = (typeof navigator !== 'undefined' && navigator.language) || 'en-US';
      utterance.rate = rate;
      utterance.pitch = pitch;
      utterance.volume = volume;

      utterance.onend = () => speakNext();
      utterance.onerror = (event) => {
        if (generation !== this.generation) return;
        // `interrupted`/`canceled` are our own stop(), not a failure.
        if (event.error === 'interrupted' || event.error === 'canceled') return;
        this.set({ speakingKey: null, paused: false });
      };

      api.speak(utterance);
    };

    // Chrome can stay paused after a previous pause(); clear it before speaking.
    if (api.paused) api.resume();
    speakNext();
    return true;
  }

  stop(): void {
    this.halt();
  }

  pause(): void {
    const api = speechSynthesisApi();
    if (!api || !this.snapshot.speakingKey || api.paused) return;
    api.pause();
    this.set({ paused: true });
  }

  resume(): void {
    const api = speechSynthesisApi();
    if (!api || !this.snapshot.speakingKey || !api.paused) return;
    api.resume();
    this.set({ paused: false });
  }

  togglePause(): void {
    if (this.snapshot.paused) this.resume();
    else this.pause();
  }

  private halt(): void {
    const api = speechSynthesisApi();
    this.generation += 1;
    if (api) api.cancel();
    this.set({ speakingKey: null, paused: false });
  }
}

/** Max utterance length. Chrome truncates/stalls on multi-paragraph strings. */
const CHUNK_LIMIT = 220;

function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, value));
}

export const tts = new TtsEngine();
