'use client';

// ── Goal verdict watch ────────────────────────────────────────────────────────
// A goal turn runs as a background task, so its verdict is not part of the chat
// run's SSE stream. This hook polls the goal front door while a conversation is
// open and hands every NEW verdict to the transcript, which is what makes the
// loop visible as chat lines ("turn 2/5 — continue: …") instead of only in the
// status strip. The first poll only primes the seen-set, so reopening a chat
// never replays old verdicts.

import { useEffect, useRef, type MutableRefObject } from 'react';
import {
  goalVerdictHistory,
  listGoals,
} from '@/lib/harness/clients/autonomy-browser';

export interface GoalVerdictLine {
  goalId: string;
  turn: number;
  verdict: string;
  reason: string;
}

const OPEN_STATUSES = new Set(['active', 'paused', 'blocked']);

export function useGoalVerdictWatch(
  chatId: string | null | undefined,
  onVerdict: MutableRefObject<((line: GoalVerdictLine) => void) | null>,
): void {
  const seen = useRef<Set<string>>(new Set());
  const primed = useRef(false);

  useEffect(() => {
    seen.current = new Set();
    primed.current = false;
    if (!chatId) return;
    let stopped = false;
    let timer: number | undefined;

    const schedule = (ms: number) => {
      if (!stopped) timer = window.setTimeout(() => void poll(), ms);
    };

    const poll = async () => {
      if (stopped) return;
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
        schedule(15_000);
        return;
      }
      try {
        const goals = await listGoals({ sessionId: chatId });
        const open = goals.filter((goal) => OPEN_STATUSES.has(goal.status));
        for (const goal of open.slice(0, 3)) {
          const verdicts = await goalVerdictHistory(goal.id);
          for (const verdict of verdicts) {
            const key = `${goal.id}:${verdict.turn}:${verdict.createdAt ?? ''}`;
            if (seen.current.has(key)) continue;
            seen.current.add(key);
            if (primed.current) {
              onVerdict.current?.({
                goalId: goal.id,
                turn: verdict.turn,
                verdict: verdict.verdict,
                reason: verdict.reason,
              });
            }
          }
        }
        primed.current = true;
      } catch {
        // The runtime may be starting or the goal may have been deleted; the
        // transcript is optional, so the next poll simply retries.
      }
      schedule(5_000);
    };

    void poll();
    return () => {
      stopped = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [chatId, onVerdict]);
}
