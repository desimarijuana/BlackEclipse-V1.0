// ── Goal transcript ───────────────────────────────────────────────────────────
// The chat-visible shape of a goal turn. A goal turn is ONE transcript message:
// it starts as a live activity card while the turn works and is finalised with
// the verdict, so the steps and the verdict never split into two bubbles.
//
// Pure builders (no React, no fetch) so the wording and the status mapping are
// unit-testable; `stock-chat.tsx` only stores the result.

import type { Message } from '@/types/chat';

import type { GoalTurnActivity, GoalVerdictLine } from './use-goal-verdict-watch';

/** The turn's single message id. Idempotent by `goalId:turn`. */
export function goalTurnMessageId(goalId: string, turn: number): string {
  return `goal-${goalId}-${turn}`;
}

/** A live step card for a turn that is still working. */
export function goalActivityMessage(
  snapshot: GoalTurnActivity,
  existing?: Message,
): Message {
  return {
    id: goalTurnMessageId(snapshot.goalId, snapshot.turn),
    role: 'assistant',
    content:
      `**Goal · turn ${snapshot.turn}** — ` +
      (snapshot.status === 'running' ? 'working' : snapshot.status),
    status:
      snapshot.status === 'running'
        ? 'tool_running'
        : snapshot.status === 'failed'
          ? 'error'
          : 'completed',
    activities: snapshot.activities,
    // Keep what a previous poll already wrote (a quote, a late approval card).
    ...(existing?.attachments ? { attachments: existing.attachments } : {}),
  };
}

/** The same turn, closed by its verdict — the steps stay visible beside it. */
export function goalVerdictMessage(line: GoalVerdictLine, existing?: Message): Message {
  return {
    id: goalTurnMessageId(line.goalId, line.turn),
    role: 'assistant',
    content: `**Goal · turn ${line.turn}** — **${line.verdict}**\n\n${line.reason}`,
    status: line.verdict === 'blocked' ? 'error' : 'completed',
    ...(existing?.activities ? { activities: existing.activities } : {}),
  };
}
