'use client';

// ── Voice input state machine ───────────────────────────────────────────────
// One hook for both engines:
//   * `whisper` — record with MediaRecorder, POST to /api/voice/transcribe;
//   * `browser` — SpeechRecognition streams the words directly.
// Selection, permissions, the hard duration cap and cleanup all live here, so
// the composers only need to render a button and insert the returned text.

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  browserRecognitionAvailable,
  startBrowserRecognition,
  type BrowserRecognitionHandle,
} from '@/lib/voice/browser-recognition';
import { loadVoiceConfig, transcribeAudio, VoiceError } from '@/lib/voice/client';
import { VoiceRecorder } from '@/lib/voice/recorder';
import { useVoiceInputStore } from '@/lib/voice/store';
import {
  describeVoiceEngine,
  type VoiceServerConfig,
} from '@/lib/voice/types';

export type VoiceInputState = 'idle' | 'starting' | 'recording' | 'transcribing';

export interface UseVoiceInput {
  state: VoiceInputState;
  elapsedMs: number;
  error: string | null;
  config: VoiceServerConfig | null;
  /** The engine that will actually run right now. */
  engine: 'whisper' | 'browser' | 'none';
  available: boolean;
  start: () => void;
  stop: () => void;
  cancel: () => void;
  clearError: () => void;
}

function microphoneError(err: unknown): string {
  const name = err instanceof DOMException ? err.name : '';
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return 'Microphone access was blocked. Allow the microphone for this site and try again.';
  }
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return 'No microphone was found. Check your system input device.';
  }
  if (name === 'NotReadableError') {
    return 'The microphone is busy in another app. Close it and try again.';
  }
  return 'The microphone could not start. Check permissions and try again.';
}

export function useVoiceInput(onTranscript: (text: string) => void): UseVoiceInput {
  const prefs = useVoiceInputStore((store) => store.prefs);
  const hydrate = useVoiceInputStore((store) => store.hydrate);

  const [state, setState] = useState<VoiceInputState>('idle');
  const [elapsedMs, setElapsedMs] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [config, setConfig] = useState<VoiceServerConfig | null>(null);

  const recorderRef = useRef<VoiceRecorder | null>(null);
  const browserRef = useRef<BrowserRecognitionHandle | null>(null);
  const tickRef = useRef<number | null>(null);
  const capRef = useRef<number | null>(null);
  const startedAtRef = useRef(0);
  const stateRef = useRef(state);
  stateRef.current = state;
  // Synchronous guards: two clicks in one frame must not open two sessions.
  const startingRef = useRef(false);
  const stopRequestedRef = useRef(false);
  const onTranscriptRef = useRef(onTranscript);
  onTranscriptRef.current = onTranscript;
  const stopRef = useRef<() => void>(() => undefined);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  useEffect(() => {
    let alive = true;
    let attempts = 0;
    let retry: number | null = null;
    const load = (refresh: boolean) => {
      void loadVoiceConfig(refresh)
        .then((next) => {
          if (alive) setConfig(next);
        })
        .catch(() => {
          // A dev HMR refresh (or a cold start) can abort the first probe. Retry
          // briefly instead of reporting "no engine" for the rest of the page life.
          if (!alive || attempts >= 2) return;
          attempts += 1;
          retry = window.setTimeout(() => load(true), 1200);
        });
    };
    load(false);
    return () => {
      alive = false;
      if (retry != null) window.clearTimeout(retry);
    };
  }, []);

  // Keep an error visible long enough to read, then let the button return to
  // its normal state. The message is also available on hover the whole time.
  useEffect(() => {
    if (!error) return;
    const timer = window.setTimeout(() => setError(null), 9000);
    return () => window.clearTimeout(timer);
  }, [error]);

  const clearTimers = useCallback(() => {
    if (tickRef.current != null) {
      window.clearInterval(tickRef.current);
      tickRef.current = null;
    }
    if (capRef.current != null) {
      window.clearTimeout(capRef.current);
      capRef.current = null;
    }
  }, []);

  const finish = useCallback(() => {
    clearTimers();
    startingRef.current = false;
    stopRequestedRef.current = false;
    setElapsedMs(0);
    setState('idle');
  }, [clearTimers]);

  const stop = useCallback(async () => {
    if (stateRef.current !== 'recording' || stopRequestedRef.current) return;
    stopRequestedRef.current = true;

    const browser = browserRef.current;
    if (browser) {
      // `onend` commits the final transcript and calls finish().
      browser.stop();
      return;
    }

    const recorder = recorderRef.current;
    if (!recorder) {
      finish();
      return;
    }

    clearTimers();
    setState('transcribing');
    const result = await recorder.stop();
    recorderRef.current = null;

    if (!result) {
      setError('No audio was recorded. Check the microphone and try again.');
      finish();
      return;
    }

    try {
      const { text } = await transcribeAudio({
        blob: result.blob,
        mimeType: result.mimeType,
        durationMs: result.durationMs,
        language: prefs.language,
        prompt: prefs.prompt,
      });
      const clean = text.trim();
      if (clean) onTranscriptRef.current(clean);
      finish();
    } catch (err) {
      setError(err instanceof VoiceError ? err.message : 'Transcription failed. Your audio was discarded.');
      finish();
    }
  }, [clearTimers, finish, prefs.language, prefs.prompt]);
  stopRef.current = () => {
    void stop();
  };

  const cancel = useCallback(() => {
    browserRef.current?.abort();
    browserRef.current = null;
    recorderRef.current?.cancel();
    recorderRef.current = null;
    clearTimers();
    startingRef.current = false;
    stopRequestedRef.current = false;
    setElapsedMs(0);
    setState('idle');
  }, [clearTimers]);

  const start = useCallback(async () => {
    if (startingRef.current || stateRef.current !== 'idle') return;
    startingRef.current = true;
    setError(null);
    setState('starting');

    let resolved = config;
    try {
      // The client caches the probe; Settings resets that cache after a save, so
      // this await always reflects the latest provider without a page reload.
      const fresh = await loadVoiceConfig();
      resolved = fresh;
      setConfig(fresh);
    } catch {
      // Keep the last known config; a transient probe failure must not break a
      // provider that was already working.
    }

    const browserAvailable = browserRecognitionAvailable();
    const engine = describeVoiceEngine(prefs.engine, resolved?.ready === true, browserAvailable);

    if (engine === 'none') {
      startingRef.current = false;
      setState('idle');
      if (prefs.engine === 'whisper') {
        setError(
          'Whisper dictation is not configured. Add an OpenAI or Groq key in Settings › AI, or switch the engine to Browser.',
        );
      } else if (prefs.engine === 'browser') {
        setError(
          'This browser has no speech recognition. Configure a Whisper provider in Settings › Voice.',
        );
      } else {
        setError(
          'Voice input is unavailable. Add an OpenAI or Groq key in Settings › AI, or use a Chromium-based browser.',
        );
      }
      return;
    }

    startedAtRef.current = Date.now();
    setElapsedMs(0);
    tickRef.current = window.setInterval(() => {
      setElapsedMs(Date.now() - startedAtRef.current);
    }, 200);
    capRef.current = window.setTimeout(() => {
      stopRef.current();
    }, Math.max(10, prefs.maxSeconds) * 1000);

    if (engine === 'browser') {
      try {
        browserRef.current = startBrowserRecognition({
          lang: prefs.language,
          onFinal: (text) => {
            if (text.trim()) onTranscriptRef.current(text.trim());
          },
          onError: (message) => {
            setError(message);
            browserRef.current = null;
            finish();
          },
          onEnd: () => {
            browserRef.current = null;
            finish();
          },
        });
        setState('recording');
      } catch (err) {
        browserRef.current = null;
        clearTimers();
        startingRef.current = false;
        setState('idle');
        setError(err instanceof Error ? err.message : 'Browser dictation could not start.');
      }
      return;
    }

    const recorder = new VoiceRecorder();
    try {
      await recorder.start();
      recorderRef.current = recorder;
      setState('recording');
    } catch (err) {
      clearTimers();
      startingRef.current = false;
      setState('idle');
      setError(microphoneError(err));
    }
  }, [clearTimers, config, finish, prefs.engine, prefs.language, prefs.maxSeconds]);

  // Never leave the mic (or a recognition session) running after unmount.
  useEffect(
    () => () => {
      browserRef.current?.abort();
      browserRef.current = null;
      recorderRef.current?.cancel();
      recorderRef.current = null;
      clearTimers();
    },
    [clearTimers],
  );

  const engine = describeVoiceEngine(prefs.engine, config?.ready === true, browserRecognitionAvailable());

  return {
    state,
    elapsedMs,
    error,
    config,
    engine,
    available: engine !== 'none',
    start: () => {
      void start();
    },
    stop: () => {
      void stop();
    },
    cancel,
    clearError: () => setError(null),
  };
}
