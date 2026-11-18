'use client';

// ── Copy, the desktop way ───────────────────────────────────────────────────
//
// Every copy affordance in the app goes through `copyText`, never straight to
// `navigator.clipboard`. Inside the shell that API is answered by WebView2, and
// WebView2 answers it with Chromium's permission bubble — "http://tauri.localhost
// wants to see text and images copied to the clipboard", Allow / Block — drawn
// over the app. It is the same dialog a website gets, which is exactly the "this
// is a browser in a window" read the shell exists to remove.
//
// Transport is a Tauri EVENT, not an app command: Tauri 2 denies app-defined
// commands to the loopback origin the window loads, while core event commands
// are allowed on the capability-listed origin. Same contract as
// `src/lib/desktop/taskbar.ts` and `src/lib/desktop/update-bridge.ts`; the shell
// listens on `be-copy` and writes the OS clipboard natively.
//
// Outside the shell (tests, a plain browser tab) the web API is still correct —
// there, a permission prompt belongs to the browser and is honest.

export const COPY_EVENT = 'be-copy';

interface TauriBridge {
  __TAURI__?: {
    event?: { emit?: (event: string, payload: unknown) => Promise<unknown> };
  };
  __TAURI_INTERNALS__?: {
    invoke?: (cmd: string, args?: unknown) => Promise<unknown>;
  };
}

/** True when the window is the native shell and can copy without a prompt. */
export function canCopyFromShell(): boolean {
  if (typeof window === 'undefined') return false;
  const bridge = window as unknown as TauriBridge;
  return Boolean(bridge.__TAURI__?.event?.emit || bridge.__TAURI_INTERNALS__?.invoke);
}

/**
 * Copy `text` to the clipboard. Resolves `true` when a path accepted it, `false`
 * when every path failed, so a caller can show "Copy failed" instead of a lie.
 *
 * The shell path is fire-and-forget: the emit hands the text over and the native
 * write is logged in `desktop-native.log`, so `true` means "handed to the OS".
 */
export async function copyText(text: string): Promise<boolean> {
  if (typeof text !== 'string') return false;
  if (emitCopy(text)) return true;
  return writeWithBrowser(text);
}

/** Dispatch `be-copy`. False when the bridge is absent or the emit threw. */
function emitCopy(text: string): boolean {
  if (typeof window === 'undefined') return false;
  const bridge = window as unknown as TauriBridge;
  try {
    const api = bridge.__TAURI__?.event;
    if (api && typeof api.emit === 'function') {
      void Promise.resolve(api.emit(COPY_EVENT, { text })).catch(() => undefined);
      return true;
    }
    const internals = bridge.__TAURI_INTERNALS__;
    if (internals && typeof internals.invoke === 'function') {
      void Promise.resolve(
        internals.invoke('plugin:event|emit', { event: COPY_EVENT, payload: { text } }),
      ).catch(() => undefined);
      return true;
    }
  } catch {
    /* bridge unavailable — fall through to the browser path */
  }
  return false;
}

/** `navigator.clipboard`, then the legacy selection copy (needs a user gesture). */
async function writeWithBrowser(text: string): Promise<boolean> {
  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      /* denied or unavailable — try the legacy path */
    }
  }
  return legacyCopy(text);
}

function legacyCopy(text: string): boolean {
  if (typeof document === 'undefined' || !document.body) return false;
  const scratch = document.createElement('textarea');
  scratch.value = text;
  scratch.setAttribute('readonly', '');
  scratch.style.position = 'fixed';
  scratch.style.top = '-1000px';
  scratch.style.opacity = '0';
  document.body.appendChild(scratch);
  scratch.select();
  let ok = false;
  try {
    ok = document.execCommand('copy');
  } catch {
    ok = false;
  }
  scratch.remove();
  return ok;
}
