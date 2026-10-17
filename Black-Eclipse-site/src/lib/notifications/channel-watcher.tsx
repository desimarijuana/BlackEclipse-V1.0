'use client';

// ── Remote channel watcher ───────────────────────────────────────────────────
// Mounted once at the app root (src/app/layout.tsx). It watches the Channel
// Gateway's message feed (`GET /api/channels/messages`) so a message arriving
// from a connected account (Telegram/Discord/Email/Slack/WhatsApp/webhook) is
// announced everywhere — toast, Settings badge, and the regular notification
// cue. The first successful poll seeds without notifying (booting never replays
// history); a failed poll is skipped silently.
//
// Announcements go through the shared `be:alert-notify` window event, so
// AlertNotificationProvider owns toast/desktop/ledger delivery in ONE place.

import { useEffect, useRef } from 'react';
import { ALERT_NOTIFY_EVENT } from '@/lib/alerts/browser-notifier';
import { selectChannelActivity, type WatchedChannelMessage, type ChannelNotification } from './channel-diff';
import type { NotificationRequest } from './store';

const POLL_MS = 15_000;
const FEED_LIMIT = 50;

function announce(notification: ChannelNotification): void {
  const detail: NotificationRequest = {
    id: notification.id,
    title: notification.title,
    body: notification.body,
    // Connections lives under Settings; that is the tab the badge attaches to.
    tab: 'settings',
    kind: 'agent',
    sound: 'notification',
  };
  window.dispatchEvent(new CustomEvent(ALERT_NOTIFY_EVENT, { detail }));
}

export function ChannelActivityWatcher() {
  const seenRef = useRef<Set<string>>(new Set());
  const seededRef = useRef(false);
  const lastPollRef = useRef(0);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      if (document.hidden && Date.now() - lastPollRef.current < 60_000) return;
      lastPollRef.current = Date.now();
      try {
        const res = await fetch(`/api/channels/messages?limit=${FEED_LIMIT}`, { cache: 'no-store' });
        if (!res.ok || cancelled) return;
        const data = await res.json();
        const messages: WatchedChannelMessage[] = (Array.isArray(data?.messages) ? data.messages : []).filter(
          (m: unknown): m is WatchedChannelMessage =>
            typeof m === 'object' &&
            m !== null &&
            typeof (m as WatchedChannelMessage).id === 'string' &&
            typeof (m as WatchedChannelMessage).direction === 'string',
        );

        const seed = !seededRef.current;
        const { notifications, next } = selectChannelActivity(messages, seenRef.current, { seed });
        seenRef.current = next;
        seededRef.current = true;
        for (const n of notifications) announce(n);
      } catch {
        /* offline / runtime down — try again next tick */
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
