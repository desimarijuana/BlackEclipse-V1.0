'use client';

// ── Bot run completion watcher ───────────────────────────────────────────────
// Mounted once at the app root (src/app/layout.tsx). Bots are automations, so
// this watches every ACTIVE bot's latest execution (GET /api/automations plus
// ONE batched GET /api/automations/statuses) and announces runs that finished:
// a `bots`-tab notification, a toast, and the loud `taskdone` alarm for
// completions (failures / timeouts / blocks use the regular alert cue).
//
// The first successful poll seeds the tracking map without notifying — booting
// the app never replays old runs. The batch status request is all-or-nothing,
// so a failed poll keeps the previous tracking map and retries next tick. The
// chat surfaces already show a run the operator is watching; this watcher is
// the "you were elsewhere" channel.

import { useEffect, useRef } from 'react';
import { ALERT_NOTIFY_EVENT } from '@/lib/alerts/browser-notifier';
import { getAutomationStatuses, listAutomations } from '@/lib/harness/automation-browser';
import {
  seedBotRuns,
  selectBotRunTransitions,
  type BotRunNotification,
  type WatchedBotRun,
} from './bots-run-diff';
import type { NotificationRequest } from './store';

const POLL_MS = 30_000;
/** Bots announced per tick; the batched status call still covers the whole list. */
const MAX_BOTS = 20;

function announce(notification: BotRunNotification): void {
  const detail: NotificationRequest = {
    id: notification.id,
    title: notification.title,
    body: notification.body,
    tab: 'bots',
    kind: 'bot',
    sound: notification.ok ? 'taskdone' : 'notification',
  };
  window.dispatchEvent(new CustomEvent(ALERT_NOTIFY_EVENT, { detail }));
}

export function BotsRunWatcher() {
  const trackedRef = useRef(new Map<string, { executionId: string | null; state: string }>());
  const seededRef = useRef(false);
  const lastPollRef = useRef(0);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      // Throttle while hidden: this tick is the most expensive of the three
      // watchers (list + statuses for every active bot), so backing off to
      // every 2 min in the background saves a real fan-out.
      if (document.hidden && Date.now() - lastPollRef.current < 120_000) return;
      lastPollRef.current = Date.now();
      try {
        const automations = await listAutomations();
        if (cancelled) return;
        const active = automations.filter((a) => a.state === 'active').slice(0, MAX_BOTS);
        const statuses = await getAutomationStatuses();
        if (cancelled) return;

        const views: WatchedBotRun[] = active.map((automation) => {
          const last = statuses[automation.id]?.lastExecution;
          return {
            automationId: automation.id,
            automationName: automation.name,
            executionId: last?.id ?? null,
            state: last?.state ?? 'none',
            errorClass: last?.errorClass ?? null,
            outcomeReason: last?.outcomeReason ?? null,
            output: last?.output ?? null,
          };
        });

        if (!seededRef.current) {
          seededRef.current = true;
          trackedRef.current = seedBotRuns(views);
          return;
        }

        const { notifications, next } = selectBotRunTransitions(views, trackedRef.current);
        trackedRef.current = next;
        for (const notification of notifications) announce(notification);
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
