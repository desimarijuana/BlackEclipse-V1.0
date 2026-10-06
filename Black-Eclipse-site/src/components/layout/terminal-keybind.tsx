'use client';

import { useEffect } from 'react';
import { useTerminalStore } from '@/lib/terminal/store';

/** Fire once per page: fetch the terminal JS + the runtime so the shell opens
 *  instantly when the user asks for it. Idempotent and best-effort. */
let prewarmed = false;
function prewarmTerminal(): void {
  // 1. Warm the Python agent runtime via its HTTP proxy — a cold spawn is the
  //    slow part. Never import the server-only runtime module from the client
  //    (it pulls in `fs`/`child_process` and breaks the bundle).
  void fetch('/api/terminal/capabilities', { method: 'GET' }).catch(() => {});
  // 2. Warm the terminal JS chunk + the xterm wasm so the dynamic import is a
  //    cache hit when the dock mounts.
  void import('@xterm/xterm').catch(() => {});
  void import('@xterm/addon-fit').catch(() => {});
}

/**
 * The global terminal toggle: Ctrl/Cmd + ` (backquote).
 *
 * Why a dedicated capture-phase listener in the root layout:
 *
 *   * It is mounted for the life of the app, so the shortcut works whether the
 *     panel is open or closed — the panel itself only mounts when open, which is
 *     exactly when a "can't open it" bug bites.
 *   * It listens in the CAPTURE phase on `window`, so it runs BEFORE any other
 *     handler and before the browser/OS default. A focused element (including the
 *     xterm textarea, which swallows keydown) cannot block it.
 *   * It matches on `event.code === 'Backquote'`, which is layout-independent —
 *     `event.key` differs across keyboard layouts (e.g. ` or ~ or §), which is a
 *     common reason a backquote shortcut silently fails.
 *
 * The header button is the no-shortcut path, so a machine where backquote is
 * genuinely reserved still has a working toggle.
 */
/**
 * Whether a keydown is the terminal toggle. A pure predicate (unit-tested) so
 * the matching rule lives in one place. Matches on `code` (layout-independent)
 * with a `key` fallback for keyboards that report `~`/§ without a backquote code.
 */
export function isTerminalShortcut(
  event: Pick<KeyboardEvent, 'ctrlKey' | 'metaKey' | 'code' | 'key'>,
): boolean {
  if (!event.ctrlKey && !event.metaKey) return false;
  return event.code === 'Backquote' || event.key === '`' || event.key === '~';
}

export function TerminalKeybind() {
  const toggle = useTerminalStore((s) => s.toggle);

  // Prewarm once per page load, then again whenever the terminal is opened (so a
  // runtime that died is ready by the time the dock asks for a shell).
  useEffect(() => {
    if (prewarmed) return;
    prewarmed = true;
    const timer = setTimeout(prewarmTerminal, 1200);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!isTerminalShortcut(event)) return;
      // Take the key before the browser or a focused terminal sees it.
      event.preventDefault();
      event.stopPropagation();
      toggle();
    };
    // Capture phase, so nothing else can consume it first.
    window.addEventListener('keydown', onKeyDown, { capture: true });
    return () => window.removeEventListener('keydown', onKeyDown, { capture: true });
  }, [toggle]);

  return null;
}
