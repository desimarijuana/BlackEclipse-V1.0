'use client';

// ── Global alert notification provider ─────────────────────────────────────
// Mounted once at the app root (src/app/layout.tsx). Watches the always-recorded
// fired-alert stream (GET /api/alerts/live — the same source the /alerts screen
// reads) and raises a native OS notification via the Web Notification API.
//
// Why a global poll rather than wiring the /alerts screen: that screen is only
// mounted on its own tab, so a fired alert was otherwise silent everywhere else.
// The live feed records every fire regardless of channels configured, so this is
// the reliable signal. It polls a small JSON GET every 10s even while desktop
// notifications are off: keeping the seen-set current is what lets a user enable
// them later without the still-buffered alerts firing as a backlog burst. It
// never *notifies* unless the user has opted in.
//
// De-duplication is a bounded set of seen ids (lib/alerts/event-diff.ts), not a
// single "last seen" id — the feed is capped at 50 rows, so a burst could
// otherwise re-announce an event after it scrolls out of the window. The first
// poll SEEDS the set without notifying, so opening the app never re-announces
// history.

import { useEffect, useRef } from 'react';
import { isEnabled, showAlertNotification } from '@/lib/alerts/browser-notifier';
import { seedSeen, selectNewEvents, type LiveAlertEvent } from '@/lib/alerts/event-diff';

const POLL_MS = 10_000;

export function AlertNotificationProvider() {
  const seenRef = useRef<Set<string>>(new Set());
  const seededRef = useRef(false);

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
        if (!fresh.length || !isEnabled()) return;

        for (const e of fresh) {
          showAlertNotification({ msg: e.detail || 'Alert fired', alertId: e.alertId });
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
  }, []);

  return null;
}
