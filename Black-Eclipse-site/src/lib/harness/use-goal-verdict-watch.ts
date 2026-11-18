'use client';

// ── Goal watch ────────────────────────────────────────────────────────────────
// A goal turn runs as a background task, so neither its verdict nor its steps
// are part of the chat run's SSE stream. This hook polls the goal front door
// while a conversation is open and emits both:
//
//   • `onActivity` — the turn's live tool steps (and the run that produced them),
//     read from the SAME persisted trace the Agent Workspace replays, so the
//     chat can show `analysis_run`, `get_historical_prices`, … while the turn is
//     still working instead of a blank placeholder.
//   • `onVerdict` — each NEW verdict for the turn.
//
// Only the turn the goal is currently ON is emitted; older verdicts are history
// (they were shown when they happened), so reopening a chat never replays them,
// and a front door that was briefly down cannot swallow the live one either.

import { useEffect, useRef, type MutableRefObject } from 'react';

import {
  goalVerdictHistory,
  listGoals,
} from '@/lib/harness/clients/autonomy-browser';
import { getTask } from '@/lib/harness/clients/tasks-browser';
import type { ActivityItem } from '@/lib/agent/response-model';
import { goalActivitiesFromToolRows, type GoalToolRow } from '@/lib/harness/goal-activity';

export interface GoalVerdictLine {
  goalId: string;
  turn: number;
  verdict: string;
  reason: string;
}

/** One live snapshot of a goal turn's steps. */
export interface GoalTurnActivity {
  goalId: string;
  /** The turn being worked (1-based), matching the verdict's `turn`. */
  turn: number;
  runId: string;
  /** `running` until the turn's task reaches a terminal phase. */
  status: 'running' | 'completed' | 'failed';
  activities: ActivityItem[];
}

export interface GoalWatchHandlers {
  onVerdict: MutableRefObject<((line: GoalVerdictLine) => void) | null>;
  onActivity: MutableRefObject<((snapshot: GoalTurnActivity) => void) | null>;
}

const OPEN_STATUSES = new Set(['active', 'paused', 'blocked']);
const POLL_MS = 5_000;
const HIDDEN_POLL_MS = 15_000;

/** The turn's tool rows, from the runtime's persisted trace. */
async function fetchToolRows(runId: string): Promise<GoalToolRow[]> {
  const res = await fetch(`/api/harness/runs/${encodeURIComponent(runId)}/events`, {
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) return [];
  const body = (await res.json().catch(() => ({}))) as { toolExecutions?: GoalToolRow[] };
  return Array.isArray(body.toolExecutions) ? body.toolExecutions : [];
}

function turnStatus(taskStatus: string | null | undefined): GoalTurnActivity['status'] {
  const phase = String(taskStatus ?? '').toUpperCase();
  if (phase === 'COMPLETED') return 'completed';
  if (phase === 'FAILED' || phase === 'CANCELLED' || phase === 'BLOCKED') return 'failed';
  return 'running';
}

export function useGoalWatch(
  chatId: string | null | undefined,
  handlers: GoalWatchHandlers,
): void {
  const seen = useRef<Set<string>>(new Set());
  const emitted = useRef<Map<string, string>>(new Map());

  useEffect(() => {
    seen.current = new Set();
    emitted.current = new Map();
    if (!chatId) return;
    let stopped = false;
    let timer: number | undefined;

    const schedule = (ms: number) => {
      if (!stopped) timer = window.setTimeout(() => void poll(), ms);
    };

    const poll = async () => {
      if (stopped) return;
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
        schedule(HIDDEN_POLL_MS);
        return;
      }
      try {
        const goals = await listGoals({ sessionId: chatId });
        const open = goals.filter((goal) => OPEN_STATUSES.has(goal.status));
        for (const goal of open.slice(0, 3)) {
          // The turn the goal is ON now. Older verdicts are history (they were
          // already shown when they happened), so only this turn's verdict is
          // eligible — even on the FIRST poll, because a front door that was
          // briefly down must not swallow the verdict that landed meanwhile.
          const currentTurn = Math.max(1, Number(goal.usedTurns) || 1);
          const verdicts = await goalVerdictHistory(goal.id);
          for (const verdict of verdicts) {
            const key = `${goal.id}:${verdict.turn}:${verdict.createdAt ?? ''}`;
            if (seen.current.has(key)) continue;
            seen.current.add(key);
            if (verdict.turn < currentTurn) continue;
            handlers.onVerdict.current?.({
              goalId: goal.id,
              turn: verdict.turn,
              verdict: verdict.verdict,
              reason: verdict.reason,
            });
          }
          if (!goal.taskId || stopped) continue;
          // The live run id lives on the turn's TASK, not on the goal record: a
          // goal records `currentRunId` only once a verdict exists.
          const task = await getTask(goal.taskId).catch(() => null);
          const runId =
            task?.assignedRunId ??
            (task?.executions ?? [])
              .map((execution) => execution.runId)
              .filter(Boolean)
              .pop() ??
            null;
          if (!runId) continue;
          const activities = goalActivitiesFromToolRows(await fetchToolRows(runId));
          const snapshot: GoalTurnActivity = {
            goalId: goal.id,
            turn: Math.max(1, Number(goal.usedTurns) || 1),
            runId,
            status: turnStatus(task?.status),
            activities,
          };
          // Emit only when something actually changed; the transcript already
          // holds the last snapshot.
          const signature = `${snapshot.turn}|${snapshot.status}|${activities
            .map((item) => `${item.id}:${item.status}`)
            .join(',')}`;
          if (emitted.current.get(goal.id) === signature) continue;
          emitted.current.set(goal.id, signature);
          handlers.onActivity.current?.(snapshot);
        }
      } catch {
        // The runtime may be starting or the goal may have been deleted; the
        // transcript is optional, so the next poll simply retries.
      }
      schedule(POLL_MS);
    };

    void poll();
    return () => {
      stopped = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [chatId, handlers.onVerdict, handlers.onActivity]);
}
