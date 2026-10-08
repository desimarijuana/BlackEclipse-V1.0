'use client';

// ── Global alert notification provider ─────────────────────────────────────
// Mounted once at the app root (src/app/layout.tsx). It makes a fired price
// alert visible EVERYWHERE in the app — not just on the /alerts tab.
//
// Two delivery layers, so an alert is never silent:
//   1. An in-app toast (bottom-right) — always shown when an alert fires, on
//      every tab, with no browser permission required.
//   2. A native OS (desktop) notification via the Web Notification API — only
//      when the user opted in AND the browser granted permission. The Settings
//      toggle reports the honest permission state (`off`/`blocked`/`on`).
//
// It watches GET /api/alerts/live (the always-recorded fired-alert stream). A
// bounded set of seen ids (lib/alerts/event-diff.ts) guarantees exactly one
// notice per event, even though the feed is capped at 50 rows. The first poll
// seeds the set without notifying, so opening the app never replays history.
//
// A `be:alert-notify` window event lets any surface (the Settings test button,
// future callers) raise the same toast+desktop pair without duplicating logic.

import { useCallback, useEffect, useRef, useState } from 'react';
import { ALERT_NOTIFY_EVENT, isEnabled, showAlertNotification } from '@/lib/alerts/browser-notifier';
import { seedSeen, selectNewEvents, type LiveAlertEvent } from '@/lib/alerts/event-diff';

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
  const seenRef = useRef<Set<string>>(new Set());
  const seededRef = useRef(false);
  const [toasts, setToasts] = useState<Toast[]>([]);

  const pushToast = useCallback((title: string, body: string) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setToasts((prev) => [...prev.slice(-(MAX_TOASTS - 1)), { id, title, body }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), TOAST_MS);
  }, []);

  // The one place an alert becomes visible: always the toast, plus the desktop
  // notification when the user opted in and permission is granted.
  const announce = useCallback(
    (title: string, body: string, alertId?: string, test?: boolean) => {
      pushToast(test ? `Test — ${title}` : title, body);
      if (isEnabled()) showAlertNotification({ alertName: title, msg: body, alertId, test });
    },
    [pushToast],
  );

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
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
          announce('BlackEclipse alert', e.detail || 'Alert fired', e.alertId);
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
  }, [announce]);

  // External surfaces (Settings test button) raise the same pair.
  useEffect(() => {
    const onNotify = (ev: Event) => {
      const d = (ev as CustomEvent<{ title?: string; body?: string; test?: boolean }>).detail || {};
      announce(d.title || 'BlackEclipse', d.body || 'Alert', undefined, d.test);
    };
    window.addEventListener(ALERT_NOTIFY_EVENT, onNotify);
    return () => window.removeEventListener(ALERT_NOTIFY_EVENT, onNotify);
  }, [announce]);

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
