'use client';

// ── Read-aloud React surface ────────────────────────────────────────────────
// Components never touch `speechSynthesis` directly. This hook exposes the
// engine snapshot (for the Stop state) plus the persisted preferences, and
// keeps the plain-Markdown path synchronous so speaking still happens inside
// the user's click gesture.

import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react';
import { hasResponseFence } from '@/lib/response/fence-check';
import { tts, type TtsSnapshot } from './speech';
import { useTtsStore, type TtsPreferences } from './store';
import { toSpeakableText } from './text';

export interface UseTts extends TtsSnapshot {
  prefs: TtsPreferences;
  /** Speak a reply. Structured responses are projected to Markdown first. */
  speak: (key: string, content: string) => void;
  stop: () => void;
  togglePause: () => void;
  /** Audition a plain sentence (used by Settings; works while disabled). */
  preview: (text: string) => void;
}

export function useTtsState(): TtsSnapshot {
  return useSyncExternalStore(tts.subscribe, tts.getSnapshot, tts.getServerSnapshot);
}

export function useTts(): UseTts {
  const state = useTtsState();
  const prefs = useTtsStore((store) => store.prefs);
  const hydrate = useTtsStore((store) => store.hydrate);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  // Turning the feature off silences anything already playing, so the switch
  // cannot leave a voice running with no visible Stop control.
  useEffect(() => {
    if (!prefs.enabled) tts.stop();
  }, [prefs.enabled]);

  const speak = useCallback(
    (key: string, content: string) => {
      if (!prefs.enabled) return;
      if (!hasResponseFence(content)) {
        // No await before speaking: iOS only allows speech from a gesture.
        tts.speak(key, toSpeakableText(content), prefs);
        return;
      }
      void import('@/lib/response/projection').then(({ projectContentMarkdown }) => {
        tts.speak(key, toSpeakableText(projectContentMarkdown(content)), prefs);
      });
    },
    [prefs],
  );

  const preview = useCallback(
    (text: string) => {
      tts.speak('__tts_preview__', toSpeakableText(text), prefs);
    },
    [prefs],
  );

  return {
    ...state,
    prefs,
    speak,
    stop: () => tts.stop(),
    togglePause: () => tts.togglePause(),
    preview,
  };
}

export interface SpeakableMessage {
  id: string;
  role: string;
  content: string;
  status?: string | null;
}

/**
 * Speak each newly completed assistant turn when auto-speak is on.
 *
 * The first effect run primes the last message without speaking it, so loading
 * a saved conversation (or toggling the setting) never replays history. A turn
 * is marked as handled even when auto-speak is off, so enabling it later starts
 * with the NEXT reply rather than the one already on screen.
 */
export function useAutoSpeak(messages: readonly SpeakableMessage[]): void {
  const { prefs, speak } = useTts();
  const last = messages[messages.length - 1];
  const spokenRef = useRef<string | null>(null);
  const primedRef = useRef(false);

  useEffect(() => {
    if (!last) return;
    if (!primedRef.current) {
      primedRef.current = true;
      spokenRef.current = last.id;
      return;
    }
    if (last.role !== 'assistant') return;
    if (last.status !== 'completed') return;
    if (spokenRef.current === last.id) return;
    spokenRef.current = last.id;
    if (!prefs.enabled || !prefs.autoSpeak) return;
    speak(last.id, last.content);
  }, [last, prefs.enabled, prefs.autoSpeak, speak]);
}
