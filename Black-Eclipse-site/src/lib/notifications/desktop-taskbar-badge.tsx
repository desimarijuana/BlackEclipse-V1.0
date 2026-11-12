'use client';

// ── Desktop taskbar badge ───────────────────────────────────────────────────
// Bridges the notification ledger + in-flight activity to the native taskbar.
// Mounted once at the app root next to `BrowserTabIndicator`; outside the
// desktop shell it renders nothing and emits nothing.
//
// The badge follows `totalUnread` — the same number the sidebar badges and the
// browser tab indicator use — so there is exactly one definition of "unread".
// Focus is tracked for two reasons: only a new arrival while the window is in
// the background may flash, and coming back marks the visible tab read (the
// ledger keeps background arrivals unread on purpose).

import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import {
  isDesktopActivity,
  subscribeDesktopActivity,
} from '@/lib/desktop/activity';
import {
  deriveTaskbarSignal,
  emitTaskbarSignal,
  hasDesktopShell,
  useTaskbarBadgeEnabled,
} from '@/lib/desktop/taskbar';
import { isViewerFocused } from '@/lib/notifications/focus';
import { totalUnread, useNotificationsStore } from './store';

export function DesktopTaskbarBadge() {
  const items = useNotificationsStore((s) => s.items);
  const hydrated = useNotificationsStore((s) => s.hydrated);
  const unread = totalUnread(items);
  const working = useSyncExternalStore(subscribeDesktopActivity, isDesktopActivity, () => false);
  const { enabled } = useTaskbarBadgeEnabled();
  const [focused, setFocused] = useState(true);
  // `null` until the first emit: a badge restored from localStorage on reload
  // must not flash, and there is no previous observation to compare against.
  const previousUnread = useRef<number | null>(null);

  // Window focus. Coming back to the app means the visible tab has now been
  // seen, so its items stop badging; `isViewerFocused` is the shared rule. This
  // runs in the browser too — the ledger keeps background arrivals unread there
  // as well, so something has to clear them when the window comes back.
  useEffect(() => {
    const sync = () => {
      const next = isViewerFocused();
      setFocused(next);
      if (!next) return;
      const { activeTab, markTabRead } = useNotificationsStore.getState();
      if (activeTab) markTabRead(activeTab);
    };
    sync();
    window.addEventListener('focus', sync);
    window.addEventListener('blur', sync);
    document.addEventListener('visibilitychange', sync);
    return () => {
      window.removeEventListener('focus', sync);
      window.removeEventListener('blur', sync);
      document.removeEventListener('visibilitychange', sync);
    };
  }, []);

  // Emit on every relevant change. Waiting for hydration means the first emit
  // already carries the RESTORED count, so a reload shows the dot without a
  // flash; only a later new arrival can ask for attention.
  useEffect(() => {
    if (!hasDesktopShell() || !hydrated) return;
    const previous = previousUnread.current ?? unread;
    const signal = deriveTaskbarSignal({
      unread,
      focused,
      enabled,
      previousUnread: previous,
      working,
    });
    previousUnread.current = unread;
    emitTaskbarSignal(signal);
  }, [hydrated, unread, focused, enabled, working]);

  return null;
}
