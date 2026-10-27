'use client';

// ── Chunk reload guard ───────────────────────────────────────────────────────
// A long-lived SPA tab keeps the JS runtime it booted with. After a rebuild the
// old chunk files are gone, so lazily opening a tab (Graph Studio, Overview,
// Tables…) fails to fetch and the page stays blank. Reload once so the shell
// picks up the current build instead of looking broken. The timestamp guard
// prevents a reload loop when the failure is a genuinely offline server.

import { useEffect } from 'react';

const GUARD_KEY = 'be_chunk_reload_at';
const RELOAD_WINDOW_MS = 60_000;

function isChunkError(value: unknown): boolean {
  if (!value) return false;
  const message = value instanceof Error ? `${value.name} ${value.message}` : String(value);
  return /ChunkLoadError|Loading chunk [\w-]+ failed|Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module/i.test(message);
}

function reloadOnce() {
  try {
    const last = Number(sessionStorage.getItem(GUARD_KEY) ?? 0);
    if (Date.now() - last < RELOAD_WINDOW_MS) return;
    sessionStorage.setItem(GUARD_KEY, String(Date.now()));
  } catch {
    /* storage disabled — still reload once per page instance below */
  }
  window.location.reload();
}

export function ChunkReloadGuard() {
  useEffect(() => {
    const onError = (event: ErrorEvent) => {
      if (isChunkError(event.error) || isChunkError(event.message)) reloadOnce();
    };
    const onRejection = (event: PromiseRejectionEvent) => {
      if (isChunkError(event.reason)) reloadOnce();
    };
    window.addEventListener('error', onError);
    window.addEventListener('unhandledrejection', onRejection);
    return () => {
      window.removeEventListener('error', onError);
      window.removeEventListener('unhandledrejection', onRejection);
    };
  }, []);
  return null;
}
