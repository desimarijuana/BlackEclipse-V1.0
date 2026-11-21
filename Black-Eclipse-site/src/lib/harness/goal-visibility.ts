// ── Goal-bar visibility (pure) ──────────────────────────────────────────────
// The chat strip is for work that is actually happening. A goal with no run,
// no wake-up, no turns and no verdict is a stale/queued record — showing it on
// every chat reads as "a goal is running" when nothing is. It stays in the
// goals store and can be managed there; it just does not occupy the composer.

import type { GoalView } from "@/lib/harness/clients/autonomy-browser";

export const OPEN_GOAL_STATUSES = ["active", "paused", "blocked"] as const;

export function isLiveGoal(goal: GoalView): boolean {
  if (!(OPEN_GOAL_STATUSES as readonly string[]).includes(goal.status)) return false;
  return (
    Boolean(goal.currentRunId) ||
    Boolean(goal.nextRunAt) ||
    goal.usedTurns > 0 ||
    goal.status === "blocked" ||
    Boolean(goal.lastVerdict) ||
    goal.taskStatus === "TODO"
  );
}

/** The goals the chat strip may show, newest-first order preserved, capped. */
export function visibleGoalBarGoals(goals: GoalView[], limit = 3): GoalView[] {
  return goals.filter(isLiveGoal).slice(0, limit);
}
