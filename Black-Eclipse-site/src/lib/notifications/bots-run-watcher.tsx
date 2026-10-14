'use client';

// ── Bot run completion watcher ───────────────────────────────────────────────
// Mounted once at the app root (src/app/layout.tsx). Bots are automations, so
// this watches every ACTIVE bot's latest execution (GET /api/automations plus
// one GET /api/automations/{id}/status per bot) and announces runs that
// finished: a `bots`-tab notification, a toast, and the loud `taskdone` alarm
// for completions (failures / timeouts / blocks use the regular alert cue).
//
// The first successful poll seeds the tracking map without notifying — booting
// the app never replays old runs. Statuses that fail to load keep their
// previous tracking entry instead of being dropped, so a transient failure
// cannot swallow a completion. The chat surfaces already show a run the
// operator is watching; this watcher is the "you were elsewhere" channel.

import { useEffect, useRef } from 'react';
import { ALERT_NOTIFY_EVENT } from '@/lib/alerts/browser-notifier';
import { getAutomationStatus, listAutomations } from '@/lib/harness/automation-browser';
import {
  seedBotRuns,
  selectBotRunTransitions,
  type BotRunNotification,
  type WatchedBotRun,
} from './bots-run-diff';
import type { NotificationRequest } from './store';

const POLL_MS = 30_000;
/** Status requests per tick are capped exactly like the Bots workspace store. */
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

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const automations = await listAutomations();
        if (cancelled) return;
        const active = automations.filter((a) => a.state === 'active').slice(0, MAX_BOTS);
        const results = await Promise.allSettled(active.map((a) => getAutomationStatus(a.id)));
        if (cancelled) return;

        const views: WatchedBotRun[] = [];
        const failedIds: string[] = [];
        results.forEach((result, index) => {
          const automation = active[index];
          if (result.status === 'rejected') {
            failedIds.push(automation.id);
            return;
          }
          const last = result.value.lastExecution;
          views.push({
            automationId: automation.id,
            automationName: automation.name,
            executionId: last?.id ?? null,
            state: last?.state ?? 'none',
            errorClass: last?.errorClass ?? null,
            outcomeReason: last?.outcomeReason ?? null,
          });
        });

        if (!seededRef.current) {
          if (failedIds.length > 0) return; // incomplete sweep — seed on a clean one
          seededRef.current = true;
          trackedRef.current = seedBotRuns(views);
          return;
        }

        const { notifications, next } = selectBotRunTransitions(views, trackedRef.current);
        // Transient status failures keep their previous entry; otherwise the
        // vanished-then-reappeared automation would re-seed and could swallow a
        // completion that happened in between.
        for (const id of failedIds) {
          const prev = trackedRef.current.get(id);
          if (prev) next.set(id, prev);
        }
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
