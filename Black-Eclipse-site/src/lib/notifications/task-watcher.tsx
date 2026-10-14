'use client';

// ── Background task watcher ─────────────────────────────────────────────────
// Mounted once at the app root (src/app/layout.tsx). It watches the durable
// Python Task / Plan store (GET /api/tasks) so a task finishing in the
// background is announced everywhere — toast, red Tasks badge, and the loud
// `taskdone` alarm cue.
//
// The first successful poll seeds the status map without notifying, exactly
// like the price-alert provider: booting the app never replays history. A
// failed poll (Python runtime down → 503, offline) is skipped silently; the
// runtime's honest availability state is surfaced by its own screens, not by
// fabricated notifications.
//
// Announcements go through the shared `be:alert-notify` window event, so the
// AlertNotificationProvider owns toast/desktop/ledger delivery in ONE place.

import { useEffect, useRef } from 'react';
import { ALERT_NOTIFY_EVENT } from '@/lib/alerts/browser-notifier';
import { seedTaskStatuses, selectTaskTransitions, type WatchedTask, type TaskNotification } from './task-diff';
import type { NotificationRequest } from './store';

const POLL_MS = 15_000;
const MAX_TASKS = 200;

function announce(notification: TaskNotification): void {
  const detail: NotificationRequest = {
    id: notification.id,
    title: notification.title,
    body: notification.body,
    tab: 'tasks',
    kind: 'task',
    // Completed → the loud completion alarm; failed → the regular alert cue.
    sound: notification.failed ? 'notification' : 'taskdone',
  };
  window.dispatchEvent(new CustomEvent(ALERT_NOTIFY_EVENT, { detail }));
}

export function TaskCompletionWatcher() {
  const statusesRef = useRef<Map<string, string>>(new Map());
  const seededRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const res = await fetch(`/api/tasks?limit=${MAX_TASKS}`, { cache: 'no-store' });
        if (!res.ok || cancelled) return;
        const data = await res.json();
        const tasks: WatchedTask[] = (Array.isArray(data?.tasks) ? data.tasks : [])
          .filter((t: unknown): t is WatchedTask =>
            typeof t === 'object' && t !== null
            && typeof (t as WatchedTask).id === 'string'
            && typeof (t as WatchedTask).status === 'string',
          );

        if (!seededRef.current) {
          seededRef.current = true;
          statusesRef.current = seedTaskStatuses(tasks);
          return;
        }

        const { notifications, next } = selectTaskTransitions(tasks, statusesRef.current);
        statusesRef.current = next;
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
