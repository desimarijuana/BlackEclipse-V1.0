'use client';

// ── Ask the shell to restart onto a staged build ────────────────────────────
//
// Staging an update (build only) is safe to run from the server. Promoting it is
// not: `desktop-promote.js` stops the window and `taskkill /T`s the server tree,
// so a promote spawned by the server would be killed halfway through. The shell
// is the one process whose child survives that (`stopShell` kills only the
// window pid), so the restart is requested from the shell.
//
// Transport is a Tauri EVENT, not an app command: Tauri 2 denies app-defined
// commands to the loopback origin the window loads, while core event commands
// are allowed on the capability-listed origin. Same contract as
// `src/lib/desktop/taskbar.ts`.

export const UPDATE_EVENT = 'be-update';

interface TauriBridge {
  __TAURI__?: {
    event?: { emit?: (event: string, payload: unknown) => Promise<unknown> };
  };
  __TAURI_INTERNALS__?: {
    invoke?: (cmd: string, args?: unknown) => Promise<unknown>;
  };
}

export function canRestartFromShell(): boolean {
  if (typeof window === 'undefined') return false;
  const bridge = window as unknown as TauriBridge;
  return Boolean(bridge.__TAURI__?.event?.emit || bridge.__TAURI_INTERNALS__?.invoke);
}

/**
 * Emit the restart request. Returns false when the window is not the desktop
 * shell (or an older shell without the listener), so the UI can fall back to the
 * manual command instead of pretending something happened.
 */
export function requestUpdateRestart(channel = 'stable'): boolean {
  return emitUpdate({ action: 'restart', channel });
}

/**
 * Ask the shell to run the updater itself. Preferred over the HTTP route: the
 * runner then lives outside the server tree, so neither the shell's supervisor
 * restart nor the promote step can kill it mid-build.
 */
export function requestUpdateApply(channel = 'stable'): boolean {
  return emitUpdate({ action: 'apply', channel });
}

function emitUpdate(payload: { action: 'apply' | 'restart'; channel: string }): boolean {
  if (typeof window === 'undefined') return false;
  const bridge = window as unknown as TauriBridge;
  try {
    const api = bridge.__TAURI__?.event;
    if (api && typeof api.emit === 'function') {
      void Promise.resolve(api.emit(UPDATE_EVENT, payload)).catch(() => undefined);
      return true;
    }
    const internals = bridge.__TAURI_INTERNALS__;
    if (internals && typeof internals.invoke === 'function') {
      void Promise.resolve(
        internals.invoke('plugin:event|emit', { event: UPDATE_EVENT, payload }),
      ).catch(() => undefined);
      return true;
    }
  } catch {
    /* bridge unavailable — caller shows the manual path */
  }
  return false;
}
