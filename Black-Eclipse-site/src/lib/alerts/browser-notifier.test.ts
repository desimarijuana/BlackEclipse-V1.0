import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  isEnabled,
  isSupported,
  permission,
  secureContext,
  setEnabled,
  showAlertNotification,
} from './browser-notifier';

const created: Array<{ title: string; options?: NotificationOptions }> = [];

function installWindow(
  opts: { permission?: NotificationPermission; supported?: boolean; secure?: boolean } = {},
) {
  const store = new Map<string, string>();
  const listeners = new Map<string, Set<(e: unknown) => void>>();
  const g = globalThis as Record<string, unknown>;

  const NotificationMock = function (title: string, options?: NotificationOptions) {
    created.push({ title, options });
    return { onclick: null, close: vi.fn() };
  } as unknown as typeof Notification;
  (NotificationMock as unknown as { permission: string }).permission = opts.permission ?? 'default';
  (NotificationMock as unknown as { requestPermission: () => Promise<string> }).requestPermission = async () => {
    (NotificationMock as unknown as { permission: string }).permission = 'granted';
    return 'granted';
  };

  g.window = {
    isSecureContext: opts.secure ?? true,
    Notification: opts.supported === false ? undefined : NotificationMock,
    localStorage: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
    },
    dispatchEvent: (e: unknown) => {
      const type = (e as { type?: string }).type ?? '';
      listeners.get(type)?.forEach((fn) => fn(e));
      return true;
    },
    addEventListener: (t: string, fn: (e: unknown) => void) => {
      if (!listeners.has(t)) listeners.set(t, new Set());
      listeners.get(t)!.add(fn);
    },
  };
  g.CustomEvent = class {
    type: string;
    detail: unknown;
    constructor(type: string, init?: { detail?: unknown }) {
      this.type = type;
      this.detail = init?.detail;
    }
  };
}

afterEach(() => {
  created.length = 0;
  delete (globalThis as Record<string, unknown>).window;
  delete (globalThis as Record<string, unknown>).CustomEvent;
});

describe('browser-notifier', () => {
  it('reports unsupported without a window/Notification', () => {
    expect(isSupported()).toBe(false);
    expect(secureContext()).toBe(false);
    expect(permission()).toBe('unsupported');
    expect(isEnabled()).toBe(false);
    expect(showAlertNotification({ msg: 'x' })).toBe(false);
  });

  it('distinguishes a secure origin from an insecure one', () => {
    installWindow({ secure: true });
    expect(secureContext()).toBe(true);
    installWindow({ secure: false });
    expect(secureContext()).toBe(false);
  });

  it('defaults to OFF (opt-in) and persists the choice', async () => {
    installWindow();
    expect(isEnabled()).toBe(false);
    const res = await setEnabled(true);
    expect(res.permission).toBe('granted');
    expect(res.effective).toBe(true);
    expect(isEnabled()).toBe(true);
    await setEnabled(false);
    expect(isEnabled()).toBe(false);
  });

  it('does not show when disabled, even if permission is granted', () => {
    installWindow({ permission: 'granted' });
    expect(showAlertNotification({ msg: 'silent' })).toBe(false);
    expect(created).toHaveLength(0);
  });

  it('shows a tagged notification when enabled and granted', async () => {
    installWindow({ permission: 'granted' });
    await setEnabled(true);
    const shown = showAlertNotification({ alertName: 'AAPL watch', msg: 'AAPL rose 3%', alertId: 'a1' });
    expect(shown).toBe(true);
    expect(created).toHaveLength(1);
    expect(created[0].title).toBe('AAPL watch');
    expect(created[0].options?.body).toBe('AAPL rose 3%');
    expect(created[0].options?.tag).toBe('be-alert-a1');
  });

  it('stays honest when the user blocks the browser prompt', async () => {
    installWindow();
    (window.Notification as unknown as { requestPermission: () => Promise<string> }).requestPermission = async () => {
      (window.Notification as unknown as { permission: string }).permission = 'denied';
      return 'denied';
    };
    const res = await setEnabled(true);
    expect(res.enabled).toBe(true);
    expect(res.permission).toBe('denied');
    expect(res.effective).toBe(false);
    expect(showAlertNotification({ msg: 'x' })).toBe(false);
  });
});
