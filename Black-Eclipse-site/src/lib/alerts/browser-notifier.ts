// ── Browser (OS-level) alert notifications ─────────────────────────────────
// Fired price alerts can surface as native desktop notifications via the Web
// Notification API. This is separate from the in-app notice ring buffer in
// `notifier.ts` (which is only read by the /alerts screen) and from the external
// channels (Telegram / Discord / ntfy / Email / webhook).
//
// Honesty rules that shape this module:
//   * Opt-in only — the preference defaults to OFF, stored in localStorage.
//   * Permission is requested from an explicit user gesture (the Settings
//     toggle / button); we never prompt on page load.
//   * `show()` is a no-op unless the user has opted in AND the browser has
//     actually granted permission. It never fabricates a delivery.
//   * While the app runs in a tab (there is no service worker), notifications
//     only appear while a BlackEclipse page is open. That limitation is stated
//     in the UI, not hidden.

const STORAGE_KEY = 'be_alerts_browser_v1';

/**
 * The window event any surface dispatches to raise the shared in-app toast +
 * desktop notification pair (handled by `AlertNotificationProvider`). Held in
 * this pure lib so non-React callers (e.g. the agent-run hook) can raise a
 * notice without importing the provider component.
 */
export const ALERT_NOTIFY_EVENT = 'be:alert-notify';

/** Preference-change event so mounted surfaces refresh their toggle state. */
export const BROWSER_NOTIFY_EVENT = 'be:alert-notify-pref';

export type NotificationPermissionState = 'unsupported' | 'default' | 'granted' | 'denied';

/** Whether the current environment can show desktop notifications at all. */
export function isSupported(): boolean {
  return typeof window !== 'undefined' && typeof window.Notification !== 'undefined';
}

/** The browser's current permission, or `unsupported` outside a supported client. */
export function permission(): NotificationPermissionState {
  if (!isSupported()) return 'unsupported';
  return window.Notification.permission as NotificationPermissionState;
}

/** The user's stored opt-in. OFF by default — desktop notifications are opt-in. */
export function isEnabled(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

function commit(enabled: boolean): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(STORAGE_KEY, enabled ? '1' : '0');
  } catch {
    /* quota / private mode — in-memory only */
  }
  window.dispatchEvent(new CustomEvent(BROWSER_NOTIFY_EVENT, { detail: { enabled } }));
}

/**
 * Request OS notification permission. MUST be called from a user gesture —
 * browsers reject (or silently ignore) a prompt that is not user-initiated.
 */
export async function requestPermission(): Promise<NotificationPermissionState> {
  if (!isSupported()) return 'unsupported';
  if (window.Notification.permission === 'granted') return 'granted';
  if (window.Notification.permission === 'denied') return 'denied';
  try {
    return (await window.Notification.requestPermission()) as NotificationPermissionState;
  } catch {
    return permission();
  }
}

/**
 * Turn desktop notifications on/off.
 *
 * Enabling requests permission (so call this from a click). If the user blocks
 * the browser prompt we still record the intent, and `effective` in the return
 * reports what will actually happen — the UI should show the honest state.
 */
export async function setEnabled(
  enabled: boolean,
): Promise<{ enabled: boolean; permission: NotificationPermissionState; effective: boolean }> {
  commit(enabled);
  let perm = permission();
  if (enabled && perm === 'default') perm = await requestPermission();
  return { enabled, permission: perm, effective: enabled && perm === 'granted' };
}

export interface AlertNotificationArgs {
  /** Alert name; used as the notification title fallback. */
  alertName?: string;
  /** The already-formatted fire line (e.g. from `describeFire`). */
  msg: string;
  /** Used as the notification tag so a re-fire replaces the previous toast. */
  alertId?: string;
  test?: boolean;
}

/**
 * Show one desktop notification for a fired alert. Returns whether it was
 * actually shown — never claims success when the user has not opted in or
 * permission is not granted.
 */
export function showAlertNotification(args: AlertNotificationArgs): boolean {
  if (!isSupported() || !isEnabled() || permission() !== 'granted') return false;
  try {
    const title = args.test ? `Test alert — ${args.alertName ?? 'BlackEclipse'}` : (args.alertName || 'BlackEclipse alert');
    const n = new window.Notification(title, {
      body: args.msg,
      tag: args.alertId ? `be-alert-${args.alertId}` : 'be-alert',
      silent: false,
    });
    n.onclick = () => {
      try {
        window.focus();
        n.close();
      } catch {
        /* ignore */
      }
    };
    return true;
  } catch {
    return false;
  }
}
