// ── Browser dictation ──────────────────────────────────────────────────────
// SpeechRecognition is the zero-config fallback: no key, no server, and it
// streams words as you speak. It is Chromium-only and its audio handling is
// owned by the browser vendor (Chrome/Edge use a cloud service), so Whisper is
// preferred whenever a transcription provider is configured. This module keeps
// the prefixed API and its event quirks in one place.
//
// It is deliberately PATIENT: browsers end a recognition session on a long
// pause, so a breath used to end the whole dictation. The session now restarts
// itself on an unexpected `onend` and only finishes when the operator stops.

interface SpeechAlternativeLike {
  transcript: string;
}

interface SpeechResultLike {
  isFinal: boolean;
  length: number;
  [index: number]: SpeechAlternativeLike;
}

interface SpeechResultListLike {
  length: number;
  [index: number]: SpeechResultLike;
}

interface SpeechResultEventLike {
  resultIndex: number;
  results: SpeechResultListLike;
}

interface SpeechErrorEventLike {
  error: string;
}

interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: ((event: SpeechErrorEventLike) => void) | null;
  onresult: ((event: SpeechResultEventLike) => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

function recognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === 'undefined') return null;
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/**
 * True inside the Tauri desktop shell.
 *
 * WebView2 exposes `webkitSpeechRecognition` but has no speech service behind
 * it: `start()` succeeds, then the session errors or ends almost immediately.
 * Selecting it there produced exactly that symptom (dictation "stopping" after
 * a second), so the shell never offers browser dictation — it uses Whisper, or
 * reports honestly that no provider is configured.
 */
export function isDesktopShell(): boolean {
  if (typeof window === 'undefined') return false;
  const w = window as unknown as Record<string, unknown>;
  return Boolean(w.__TAURI__ || w.__TAURI_INTERNALS__);
}

export function browserRecognitionAvailable(): boolean {
  if (isDesktopShell()) return false;
  return recognitionCtor() !== null;
}

export function describeRecognitionError(code: string): string {
  switch (code) {
    case 'not-allowed':
    case 'service-not-allowed':
      return 'Microphone access was blocked. Allow the microphone for this site, or configure a Whisper provider in Settings › Voice.';
    case 'no-speech':
      return 'No speech was detected. Try again a little closer to the microphone.';
    case 'audio-capture':
      return 'No microphone was found. Check your system input device.';
    case 'network':
      return 'Browser dictation needs a network connection. Configure Whisper in Settings › Voice for offline/server transcription.';
    case 'aborted':
      return '';
    default:
      return `Browser dictation failed (${code}).`;
  }
}

export interface BrowserRecognitionOptions {
  lang?: string;
  onInterim?: (text: string) => void;
  onFinal: (text: string) => void;
  onError: (message: string) => void;
  onEnd?: () => void;
}

export interface BrowserRecognitionHandle {
  stop: () => void;
  abort: () => void;
}

/** Cap the automatic restarts so a broken microphone cannot loop forever. */
const MAX_RESTARTS = 80;
const RESTART_DELAY_MS = 300;

export function startBrowserRecognition(
  options: BrowserRecognitionOptions,
): BrowserRecognitionHandle {
  const Ctor = recognitionCtor();
  if (!Ctor) throw new Error('Browser dictation is not available');

  const lang = options.lang || (typeof navigator !== 'undefined' ? navigator.language : 'en-US');

  // Everything final is accumulated across restarts; `interim` belongs to the
  // current session only.
  let finalText = '';
  let stopping = false;
  let failed = false;
  let settled = false;
  let restarts = 0;
  let recognition: SpeechRecognitionLike | null = null;
  let restartTimer: number | null = null;

  const clearRestart = () => {
    if (restartTimer != null) {
      window.clearTimeout(restartTimer);
      restartTimer = null;
    }
  };

  const settle = () => {
    if (settled) return;
    settled = true;
    clearRestart();
    options.onEnd?.();
    const text = finalText.trim();
    if (!failed && text) options.onFinal(text);
  };

  const start = () => {
    if (settled) return;
    try {
      const rec = new Ctor();
      recognition = rec;
      rec.lang = lang;
      // Keep the session open across pauses. Some engines still end it after a
      // long silence, which is what `onend` below handles.
      rec.continuous = true;
      rec.interimResults = true;
      rec.maxAlternatives = 1;

      rec.onresult = (event) => {
        let interim = '';
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const result = event.results[i];
          const alternative = result[0];
          if (!alternative) continue;
          if (result.isFinal) finalText += alternative.transcript;
          else interim += alternative.transcript;
        }
        // Show the whole dictation so far, not just the current fragment.
        options.onInterim?.(`${finalText}${interim}`.trimStart());
      };

      rec.onerror = (event) => {
        // `aborted` is our own stop; `no-speech` is a pause, not a failure.
        if (event.error === 'aborted' || event.error === 'no-speech') return;
        failed = true;
        const message = describeRecognitionError(event.error);
        if (message) options.onError(message);
      };

      rec.onend = () => {
        if (settled) return;
        if (stopping || failed) {
          settle();
          return;
        }
        if (restarts >= MAX_RESTARTS) {
          settle();
          return;
        }
        // A pause ended the vendor session — keep listening.
        restarts += 1;
        clearRestart();
        restartTimer = window.setTimeout(() => {
          restartTimer = null;
          start();
        }, RESTART_DELAY_MS);
      };

      rec.start();
    } catch {
      if (settled) return;
      // A restart that lands while the previous session is still tearing down
      // throws InvalidStateError; retry shortly instead of dropping the words.
      clearRestart();
      restartTimer = window.setTimeout(() => {
        restartTimer = null;
        if (restarts < MAX_RESTARTS) {
          restarts += 1;
          start();
        } else {
          settle();
        }
      }, RESTART_DELAY_MS * 2);
    }
  };

  start();

  return {
    stop: () => {
      stopping = true;
      // `stop()` flushes the pending final result, then fires `onend`.
      try {
        recognition?.stop();
      } catch {
        settle();
      }
      // A session that never fired `onend` must not hold the UI hostage.
      window.setTimeout(() => {
        if (!settled) settle();
      }, 1200);
    },
    abort: () => {
      failed = true;
      try {
        recognition?.abort();
      } catch {
        settle();
      }
    },
  };
}
