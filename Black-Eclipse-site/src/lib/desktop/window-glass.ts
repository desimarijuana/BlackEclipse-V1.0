'use client';

// ── Desktop window glass ────────────────────────────────────────────────────
// The native shell applies OS-level acrylic/blur behind a transparent WebView;
// this module owns the front-end half: the persisted preference, the
// `html.glass-window` class that makes the page translucent, and the event that
// tells Rust to apply or clear the acrylic. The browser front door never sees
// any of it (no Tauri bridge), so its theme background is untouched.

import { useCallback, useEffect, useState } from 'react';

const STORAGE_KEY = 'be_window_glass_v1';

export function hasDesktopShell(): boolean {
  if (typeof window === 'undefined') return false;
  const bridge = window as unknown as {
    __TAURI__?: unknown;
    __TAURI_INTERNALS__?: unknown;
  };
  return Boolean(bridge.__TAURI__ || bridge.__TAURI_INTERNALS__);
}

/** Default ON for the desktop shell; always false in a browser. */
export function readWindowGlass(): boolean {
  if (!hasDesktopShell()) return false;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw === null ? true : raw === '1';
  } catch {
    return true;
  }
}

/** Tell Rust to apply/clear the acrylic layer (core events; commands are denied
 *  to the remote app origin). */
function tellShell(enabled: boolean): void {
  try {
    const bridge = window as unknown as {
      __TAURI__?: { event?: { emit?: (event: string, payload: unknown) => Promise<unknown> } };
    };
    const api = bridge.__TAURI__?.event;
    if (api && typeof api.emit === 'function') {
      void api.emit('be-window', { action: 'set-glass', enabled });
      return;
    }
  } catch {
    /* fall through to the injected-script bridge */
  }
  try {
    window.dispatchEvent(new CustomEvent('be-window-action', { detail: { action: 'set-glass', enabled } }));
  } catch {}
}

export function applyWindowGlass(enabled: boolean, persist = true): void {
  if (typeof document === 'undefined') return;
  const on = enabled && hasDesktopShell();
  document.documentElement.classList.toggle('glass-window', on);
  if (persist) {
    try {
      window.localStorage.setItem(STORAGE_KEY, on ? '1' : '0');
    } catch {
      /* storage disabled — the in-memory class still works */
    }
  }
  tellShell(on);
  window.dispatchEvent(new CustomEvent('be:window-glass', { detail: { enabled: on } }));
}

/**
 * Read/apply the setting and keep every mounted consumer in sync. Safe in the
 * browser (returns unavailable), and SSR-safe (state starts false, resolved in
 * an effect).
 */
export function useWindowGlass(): {
  enabled: boolean;
  available: boolean;
  setEnabled: (enabled: boolean) => void;
} {
  const [enabled, setEnabledState] = useState(false);
  const [available, setAvailable] = useState(false);

  useEffect(() => {
    const desktop = hasDesktopShell();
    setAvailable(desktop);
    if (!desktop) return;
    const initial = readWindowGlass();
    setEnabledState(initial);
    applyWindowGlass(initial, false);
    const onChange = (event: Event) => {
      const detail = (event as CustomEvent<{ enabled?: boolean }>).detail;
      if (typeof detail?.enabled === 'boolean') setEnabledState(detail.enabled);
    };
    window.addEventListener('be:window-glass', onChange);
    return () => window.removeEventListener('be:window-glass', onChange);
  }, []);

  const setEnabled = useCallback((next: boolean) => {
    setEnabledState(next);
    applyWindowGlass(next);
  }, []);

  return { enabled, available, setEnabled };
}
