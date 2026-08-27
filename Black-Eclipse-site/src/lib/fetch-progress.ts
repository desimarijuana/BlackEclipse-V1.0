'use client';

// Lightweight client-side store that tracks in-flight `fetch` calls made
// during the app boot window. The global loader renders a percentage + bar
// from this so it reflects how much data has actually loaded instead of a
// hardcoded count-up.

type BootState = { total: number; done: number };

let total = 0;
let done = 0;
const listeners = new Set<(s: BootState) => void>();

export function getBootProgress(): BootState {
  return { total, done };
}

export function subscribeBootProgress(fn: (s: BootState) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function emit() {
  const s = { total, done };
  for (const l of listeners) l(s);
}/** Wrap one fetch call; call the returned cleanup when it settles. */
export function trackBootFetch(): () => void {
  total++;
  emit();
  let settled = false;
  return () => {
    if (settled) return;
    settled = true;
    done++;
    emit();
  };
}

/** Instrument window.fetch so every API call during boot updates progress. */
export function installBootFetchTracking(): () => void {
  if (typeof window === 'undefined' || typeof window.fetch !== 'function') return () => {};
  const orig = window.fetch.bind(window);
  const wrapped: typeof fetch = (input, init) => {
    const stop = trackBootFetch();
    return orig(input, init).finally(stop);
  };
  window.fetch = wrapped;
  return () => {
    window.fetch = orig;
  };
}
