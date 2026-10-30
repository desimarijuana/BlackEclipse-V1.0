'use client';

// Mounted once at the app root. Hydrates the persisted read-aloud preferences
// after mount (keeping SSR output stable) and cancels speech when the document
// is torn down so the OS voice cannot outlive the page.

import { useEffect } from 'react';
import { tts } from './speech';
import { useTtsStore } from './store';

export function TtsProvider() {
  const hydrate = useTtsStore((store) => store.hydrate);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  useEffect(() => {
    const stop = () => tts.stop();
    window.addEventListener('pagehide', stop);
    return () => {
      window.removeEventListener('pagehide', stop);
      stop();
    };
  }, []);

  return null;
}
