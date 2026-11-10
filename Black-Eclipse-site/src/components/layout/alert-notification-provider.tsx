'use client';

// ── Global notification provider ────────────────────────────────────────────
// Mounted once at the app root (src/app/layout.tsx). It makes a fired price
// alert — or any raised notification — visible EVERYWHERE in the app, not just
// on the owning tab.
//
// Three delivery layers, so an event is never silent:
//   1. An in-app toast (bottom-right) — always shown, on every tab, with no
//      browser permission required.
//   2. The notification ledger (`lib/notifications/store`) — the toast's item
//      is recorded against its owning tab, so the sidebar shows a red unread
//      badge until that tab is opened.
//   3. A native OS (desktop) notification via the Web Notification API — only
//      when the user opted in AND the browser granted permission. The Settings
//      toggle reports the honest permission state (`off`/`blocked`/`on`).
// A caller may also request a sound cue (`sound` in the detail).
//
// It watches GET /api/alerts/live (the always-recorded fired-alert stream). A
// bounded set of seen ids (lib/alerts/event-diff.ts) guarantees exactly one
// notice per event, even though the feed is capped at 50 rows. The first poll
// seeds the set without notifying, so opening the app never replays history.
//
// The `be:alert-notify` window event is the unified "raise a notification"
// channel: price alerts, agent approval requests, the task watcher and the
// Settings test button all go through it, so toast/desktop/ledger/sound logic
// exists exactly once.

import { useCallback, useEffect, useRef, useState } from 'react';
import { ALERT_NOTIFY_EVENT, isEnabled, showAlertNotification } from '@/lib/alerts/browser-notifier';
import { seedSeen, selectNewEvents, type LiveAlertEvent } from '@/lib/alerts/event-diff';
import { isSoundName, sound } from '@/lib/sounds';
import { useNotificationsStore, useHydrateNotifications, type NotificationRequest } from '@/lib/notifications/store';

const POLL_MS = 10_000;
const TOAST_MS = 8_000;
const MAX_TOASTS = 4;

// Re-exported for the surfaces that already import it from this module.
export { ALERT_NOTIFY_EVENT };

interface Toast {
  id: string;
  title: string;
  body: string;
}

export function AlertNotificationProvider() {
  useHydrateNotifications();
  const seenRef = useRef<Set<string>>(new Set());
  const seededRef = useRef(false);
  const lastPollRef = useRef(0);
  const [toasts, setToasts] = useState<Toast[]>([]);

  const pushToast = useCallback((title: string, body: string) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setToasts((prev) => [...prev.slice(-(MAX_TOASTS - 1)), { id, title, body }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), TOAST_MS);
  }, []);

  // The one place a notification becomes visible: the ledger, always the
  // toast, the desktop notification when opted in, and an optional sound cue.
  const raise = useCallback(
    (req: NotificationRequest) => {
      const title = req.title || 'BlackEclipse';
      const body = req.body || 'Alert';
      pushToast(req.test ? `Test — ${title}` : title, body);
      if (isEnabled()) showAlertNotification({ alertName: title, msg: body, alertId: req.alertId, test: req.test });
      // Validated: the detail arrives via a window event, so the cue name is
      // runtime input, not a compile-time SoundName.
      if (req.sound && isSoundName(req.sound)) sound.play(req.sound);
      // A test raise is a settings probe, not an event — never badge.
      if (!req.test) {
        useNotificationsStore.getState().push({
          id: req.id,
          tab: req.tab ?? 'alerts',
          kind: req.kind ?? 'alert',
          title,
          body,
          url: req.url,
        });
      }
    },
    [pushToast],
  );

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      // Throttle while the tab is hidden: keep alerts reasonably timely but
      // stop the every-10s request storm when nobody is looking at the app.
      if (document.hidden && Date.now() - lastPollRef.current < 60_000) return;
      lastPollRef.current = Date.now();
      try {
        const res = await fetch('/api/alerts/live', { cache: 'no-store' });
        if (!res.ok || cancelled) return;
        const data = await res.json();
        const events: LiveAlertEvent[] = data.events || [];

        if (!seededRef.current) {
          seededRef.current = true;
          seenRef.current = seedSeen(events, seenRef.current);
          return;
        }

        const { fresh, seen } = selectNewEvents(events, seenRef.current);
        seenRef.current = seen;
        for (const e of fresh) {
          raise({
            id: e.id,
            title: 'BlackEclipse alert',
            body: e.detail || 'Alert fired',
            alertId: e.alertId,
            tab: 'alerts',
            kind: 'alert',
            // A fired price/news alert is exactly the event the alert cue is
            // for. The cue is a per-cue opt-out in Settings, so this does not
            // make interaction "haptics" audible.
            sound: 'notification',
          });
        }
      } catch {
        /* offline / server down — try again next tick */
      }
    };

    void poll();
    const t = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [raise]);

  // External surfaces (agent approvals, the task watcher, Settings test button)
  // raise the same toast + desktop + ledger + sound through one channel.
  useEffect(() => {
    const onNotify = (ev: Event) => {
      const d = (ev as CustomEvent<Partial<NotificationRequest>>).detail || {};
      raise(d);
    };
    window.addEventListener(ALERT_NOTIFY_EVENT, onNotify);
    return () => window.removeEventListener(ALERT_NOTIFY_EVENT, onNotify);
  }, [raise]);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[120] flex flex-col gap-2 pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          role="alert"
          className="pointer-events-auto w-80 max-w-[calc(100vw-2rem)] rounded-2xl border border-white/10 dark:border-white/5 glass-card-strong shadow-lg p-3.5 animate-fade-in-up"
        >
          <p className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-primary inline-block" />
            {t.title}
          </p>
          <p className="text-[11px] text-muted-foreground mt-1 leading-snug">{t.body}</p>
          <button
            onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}
            className="absolute top-2 right-3 text-muted-foreground hover:text-foreground text-xs cursor-pointer"
            aria-label="Dismiss"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
