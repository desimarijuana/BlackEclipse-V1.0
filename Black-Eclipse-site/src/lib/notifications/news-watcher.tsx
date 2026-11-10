'use client';

// ── High-alert news watcher ──────────────────────────────────────────────────
// Mounted once at the app root (src/app/layout.tsx). It watches
// `GET /api/news/alerts` — the same deterministic high/critical scan the News
// tab uses — so a market-moving story reaches the header notification ledger
// (bell + sidebar badge) from ANY tab, not only while the News tab is open.
//
// The first successful poll seeds the seen set without notifying (booting never
// replays history or floods the ledger), exactly like the price/task watchers.
// Later polls announce only newly seen stories and imminent high-impact
// releases through the shared `be:alert-notify` window event, so
// AlertNotificationProvider owns toast/desktop/ledger/sound delivery in ONE
// place. A failed poll is skipped silently.

import { useEffect, useRef } from 'react';
import { ALERT_NOTIFY_EVENT } from '@/lib/alerts/browser-notifier';
import type { NotificationRequest } from './store';
import {
  buildNewsNotifications,
  diffNewsNotifications,
  type WatchedNewsAlert,
  type WatchedNewsEvent,
} from './news-diff';

const POLL_MS = 120_000;
const ALERT_LIMIT = 5;
const LOOKBACK_HOURS = 24;

/** Watchlist symbols sharpen the deterministic importance score, same as the News tab. */
function readWatchlist(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem('watchlist_guest') || '[]');
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((w: { symbol?: string }) => String(w?.symbol || '').toUpperCase())
      .filter(Boolean)
      .slice(0, 100);
  } catch {
    return [];
  }
}

function announce(notification: { id: string; title: string; body: string; url?: string }): void {
  const detail: NotificationRequest = {
    id: notification.id,
    title: notification.title,
    body: notification.body,
    url: notification.url,
    tab: 'news',
    kind: 'alert',
    sound: 'notification',
  };
  window.dispatchEvent(new CustomEvent(ALERT_NOTIFY_EVENT, { detail }));
}

export function NewsAlertWatcher() {
  const seenRef = useRef<Set<string>>(new Set());
  const seededRef = useRef(false);
  const lastPollRef = useRef(0);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      // Throttle in a hidden tab — nobody can see the toast right now.
      if (document.hidden && Date.now() - lastPollRef.current < 60_000) return;
      lastPollRef.current = Date.now();
      try {
        const params = new URLSearchParams({
          limit: String(ALERT_LIMIT),
          hours: String(LOOKBACK_HOURS),
        });
        const watchlist = readWatchlist();
        if (watchlist.length > 0) params.set('tickers', watchlist.join(','));
        const res = await fetch(`/api/news/alerts?${params.toString()}`, { cache: 'no-store' });
        if (!res.ok || cancelled) return;
        const data = await res.json();
        const alerts: WatchedNewsAlert[] = Array.isArray(data?.alerts) ? data.alerts : [];
        const events: WatchedNewsEvent[] = Array.isArray(data?.upcoming) ? data.upcoming : [];

        const current = buildNewsNotifications(alerts, events);
        const seed = !seededRef.current;
        const { notifications, next } = diffNewsNotifications(current, seenRef.current, { seed });
        seenRef.current = next;
        seededRef.current = true;

        for (const notification of notifications) announce(notification);
      } catch {
        /* offline / DB unavailable — try again next tick */
      }
    };

    void poll();
    const timer = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  return null;
}
