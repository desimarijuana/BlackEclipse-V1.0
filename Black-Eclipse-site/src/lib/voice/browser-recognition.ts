// ── Browser dictation ──────────────────────────────────────────────────────
// SpeechRecognition is the zero-config fallback: no key, no server, and it
// streams words as you speak. It is Chromium-only and its audio handling is
// owned by the browser vendor (Chrome/Edge use a cloud service), so Whisper is
// preferred whenever a transcription provider is configured. This module keeps
// the prefixed API and its event quirks in one place.

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

export function browserRecognitionAvailable(): boolean {
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
      return 'No microphone was found. Check the system input device.';
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

export function startBrowserRecognition(
  options: BrowserRecognitionOptions,
): BrowserRecognitionHandle {
  const Ctor = recognitionCtor();
  if (!Ctor) throw new Error('Browser dictation is not available');

  const recognition = new Ctor();
  recognition.lang = options.lang || (typeof navigator !== 'undefined' ? navigator.language : 'en-US');
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;

  let finalText = '';
  let failed = false;
  let settled = false;

  const settle = () => {
    if (settled) return;
    settled = true;
    options.onEnd?.();
    const text = finalText.trim();
    if (!failed && text) options.onFinal(text);
  };

  recognition.onresult = (event) => {
    let interim = '';
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const result = event.results[i];
      const alternative = result[0];
      if (!alternative) continue;
      if (result.isFinal) finalText += alternative.transcript;
      else interim += alternative.transcript;
    }
    if (interim) options.onInterim?.(interim);
  };

  recognition.onerror = (event) => {
    if (event.error === 'aborted') return;
    failed = true;
    const message = describeRecognitionError(event.error);
    if (message) options.onError(message);
  };

  recognition.onend = () => settle();

  try {
    recognition.start();
  } catch {
    options.onError('Browser dictation could not start. Try again.');
    settle();
  }

  return {
    stop: () => {
      try {
        recognition.stop();
      } catch {
        settle();
      }
    },
    abort: () => {
      failed = true;
      try {
        recognition.abort();
      } catch {
        settle();
      }
    },
  };
}
