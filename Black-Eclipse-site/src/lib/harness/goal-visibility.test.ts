import { describe, expect, it } from "vitest";
import { isLiveGoal, visibleGoalBarGoals } from "./goal-visibility";
import type { GoalView } from "@/lib/harness/clients/autonomy-browser";

function goal(overrides: Partial<GoalView>): GoalView {
  return {
    id: "goal_1",
    objective: "needs more room",
    acceptance: [],
    planId: null,
    taskId: null,
    status: "active",
    budget: {},
    contract: {},
    gates: [],
    maxTurns: 5,
    usedTurns: 0,
    lastVerdict: null,
    sessionId: null,
    nextRunAt: null,
    noProgress: 0,
    currentRunId: null,
    modelProvider: null,
    modelName: null,
    workspaceId: null,
    createdAt: "2026-11-21T00:00:00.000Z",
    updatedAt: "2026-11-21T00:00:00.000Z",
    taskStatus: null,
    ...overrides,
  } as GoalView;
}

describe("goal bar visibility", () => {
  it("hides an idle 0-turn goal that never ran or scheduled", () => {
    expect(isLiveGoal(goal({ status: "active" }))).toBe(false);
    expect(isLiveGoal(goal({ status: "paused" }))).toBe(false);
  });

  it("shows a goal that is running, scheduled, or has history", () => {
    expect(isLiveGoal(goal({ currentRunId: "run_1" }))).toBe(true);
    expect(isLiveGoal(goal({ nextRunAt: "2026-11-21T01:00:00Z" }))).toBe(true);
    expect(isLiveGoal(goal({ usedTurns: 1 }))).toBe(true);
    expect(isLiveGoal(goal({ status: "blocked" }))).toBe(true);
    expect(isLiveGoal(goal({ taskStatus: "TODO" }))).toBe(true);
  });

  it("hides cancelled/completed and caps the strip", () => {
    expect(isLiveGoal(goal({ status: "cancelled", usedTurns: 1 }))).toBe(false);
    const list = [
      goal({ id: "a", usedTurns: 1 }),
      goal({ id: "b", usedTurns: 1 }),
      goal({ id: "c", usedTurns: 1 }),
      goal({ id: "d", usedTurns: 1 }),
    ];
    expect(visibleGoalBarGoals(list).map((g) => g.id)).toEqual(["a", "b", "c"]);
  });
});
