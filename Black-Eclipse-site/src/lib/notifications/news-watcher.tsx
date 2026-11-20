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
//
// Delivery is user-controlled in Settings › News › Pop-ups & notifications
// (`lib/news/notification-prefs`): background watch, in-app pop-up, desktop
// notification, alert sound, upcoming releases, watchlist-only and minimum
// score. The ledger entry is always recorded while the watch is on, so turning
// off pop-ups/sound never hides a story from the bell.

import { useEffect, useRef } from 'react';
import { ALERT_NOTIFY_EVENT } from '@/lib/alerts/browser-notifier';
import type { NotificationRequest } from './store';
import {
  readNewsWatchlist,
  useNewsNotificationPrefs,
  type NewsNotificationPrefs,
} from '@/lib/news/notification-prefs';
import {
  buildNewsNotifications,
  diffNewsNotifications,
  type WatchedNewsAlert,
  type WatchedNewsEvent,
} from './news-diff';

const POLL_MS = 120_000;
const ALERT_LIMIT = 5;
const LOOKBACK_HOURS = 24;

function announce(
  notification: { id: string; title: string; body: string; url?: string },
  prefs: NewsNotificationPrefs,
): void {
  const detail: NotificationRequest = {
    id: notification.id,
    title: notification.title,
    body: notification.body,
    url: notification.url,
    tab: 'news',
    kind: 'alert',
    // Each lane can be suppressed independently. The ledger entry is written
    // regardless (unless this were a test), so the bell still records it.
    toast: prefs.popup,
    desktop: prefs.desktop,
    sound: prefs.sound ? 'notification' : undefined,
  };
  window.dispatchEvent(new CustomEvent(ALERT_NOTIFY_EVENT, { detail }));
}

export function NewsAlertWatcher() {
  const prefs = useNewsNotificationPrefs((s) => s.prefs);
  const hydrate = useNewsNotificationPrefs((s) => s.hydrate);
  const seenRef = useRef<Set<string>>(new Set());
  const seededRef = useRef(false);
  const lastPollRef = useRef(0);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  useEffect(() => {
    let cancelled = false;

    // A disabled watcher keeps no history: re-enabling starts from "now" and
    // seeds the first poll instead of replaying everything published meanwhile.
    if (!prefs.enabled) {
      seededRef.current = false;
      seenRef.current = new Set();
      return;
    }

    const poll = async () => {
      // Throttle in a hidden tab — nobody can see the toast right now.
      if (document.hidden && Date.now() - lastPollRef.current < 60_000) return;
      lastPollRef.current = Date.now();
      const currentPrefs = useNewsNotificationPrefs.getState().prefs;
      try {
        const params = new URLSearchParams({
          limit: String(ALERT_LIMIT),
          hours: String(LOOKBACK_HOURS),
          minScore: String(currentPrefs.minScore),
        });
        const watchlist = readNewsWatchlist();
        if (watchlist.length > 0) params.set('tickers', watchlist.join(','));
        const res = await fetch(`/api/news/alerts?${params.toString()}`, { cache: 'no-store' });
        if (!res.ok || cancelled) return;
        const data = await res.json();
        const alerts: WatchedNewsAlert[] = Array.isArray(data?.alerts) ? data.alerts : [];
        const events: WatchedNewsEvent[] = Array.isArray(data?.upcoming) ? data.upcoming : [];

        // Watchlist-only is a client-side filter: the API uses tickers to
        // sharpen the score, not to restrict the result set.
        const watchSet = new Set(watchlist);
        const visibleAlerts = currentPrefs.watchlistOnly
          ? alerts.filter((a) => a.ticker && watchSet.has(String(a.ticker).toUpperCase()))
          : alerts;
        const visibleEvents = currentPrefs.includeReleases ? events : [];

        const current = buildNewsNotifications(visibleAlerts, visibleEvents);
        const seed = !seededRef.current;
        const { notifications, next } = diffNewsNotifications(current, seenRef.current, { seed });
        seenRef.current = next;
        seededRef.current = true;

        for (const notification of notifications) announce(notification, currentPrefs);
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
  }, [
    prefs.enabled,
    prefs.minScore,
    prefs.watchlistOnly,
    prefs.includeReleases,
  ]);

  return null;
}
