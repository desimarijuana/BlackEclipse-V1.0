// The `/goal` handler — the one slash command whose failure mode was silent
// (no session, no workspace, a zombie goal when the engine is off). These tests
// pin the contract the loop depends on.

import { describe, expect, it, vi } from "vitest";
import { autonomyHandlers } from "./command-handlers-autonomy";
import { parseAndBind } from "./command-parser";
import { resolveCommand } from "./command-registry";
import type { CommandDeps, FrontDoorResult } from "./command-router";

interface Route {
  match: (path: string, init?: { method?: string; body?: unknown }) => boolean;
  reply: (path: string, init?: { method?: string; body?: unknown }) => FrontDoorResult;
}

function ok(data: unknown): FrontDoorResult {
  return { ok: true, status: 200, data };
}

function harness(routes: Route[]) {
  const calls: Array<{ path: string; init?: { method?: string; body?: unknown } }> = [];
  const request = vi.fn(async (path: string, init?: { method?: string; body?: unknown }) => {
    calls.push({ path, init });
    const route = routes.find((item) => item.match(path, init));
    if (!route) throw new Error(`unexpected route ${init?.method ?? "GET"} ${path}`);
    return route.reply(path, init);
  });
  const deps = { frontDoor: { request } } as unknown as CommandDeps;
  return { deps, calls };
}

async function runGoal(text: string, deps: CommandDeps, chatId: string | undefined = "sess_1") {
  const spec = resolveCommand("goal");
  expect(spec).toBeTruthy();
  const parsed = parseAndBind(text, spec ? [spec] : []);
  expect(parsed).toBeTruthy();
  expect(parsed!.args.errors).toEqual([]);
  const out = await autonomyHandlers["autonomy.goal"](
    { operator: true, chatId },
    spec!,
    parsed!.args,
    deps,
  );
  return out;
}

const tasksRoute: Route = {
  match: (path) => path === "/api/code/tasks",
  reply: () => ok({ tasks: [{ workspaceId: "ws_1", sessionId: "sess_1" }] }),
};

const createRoute: Route = {
  match: (path, init) => path === "/api/goals" && init?.method === "POST",
  reply: () => ok({ goal: { id: "goal_1", status: "active", usedTurns: 1, maxTurns: 5 } }),
};

async function runLoop(text: string, deps: CommandDeps, chatId: string | undefined = "sess_1") {
  const spec = resolveCommand("loop");
  expect(spec).toBeTruthy();
  const parsed = parseAndBind(text, spec ? [spec] : []);
  expect(parsed).toBeTruthy();
  expect(parsed!.args.errors).toEqual([]);
  return autonomyHandlers["autonomy.loop"](
    { operator: true, chatId },
    spec!,
    parsed!.args,
    deps,
  );
}

describe("/goal", () => {
  it("binds the session, the newest workspace, and every repeated gate", async () => {
    const { deps, calls } = harness([tasksRoute, createRoute]);
    const out = await runGoal(
      "/goal ship the widget --gate typecheck --gate unit_test=src/lib/widget.test.ts --turns 7 --parallel",
      deps,
    );

    expect(out.status).toBe("completed");
    const create = calls.find((call) => call.path === "/api/goals" && call.init?.method === "POST");
    expect(create).toBeTruthy();
    const body = create!.init!.body as Record<string, unknown>;
    expect(body.sessionId).toBe("sess_1");
    expect(body.workspaceId).toBe("ws_1");
    expect(body.maxTurns).toBe(7);
    expect(body.allowParallel).toBe(true);
    expect(body.gates).toEqual([
      { id: "gate-1", check: "typecheck", args: {} },
      { id: "gate-2", check: "unit_test", args: { files: ["src/lib/widget.test.ts"] } },
    ]);
  });

  it("refuses a gate goal when no workspace exists instead of creating a dead end", async () => {
    const { deps, calls } = harness([
      { match: (path) => path === "/api/code/tasks", reply: () => ok({ tasks: [] }) },
    ]);
    const out = await runGoal("/goal fix it --gate typecheck", deps);
    expect(out.status).toBe("invalid");
    expect(out.error?.code).toBe("NO_WORKSPACE");
    expect(calls.some((call) => call.path === "/api/goals")).toBe(false);
  });

  it("reports an off engine as a named, actionable failure", async () => {
    const { deps } = harness([
      tasksRoute,
      {
        match: (path, init) => path === "/api/goals" && init?.method === "POST",
        reply: () => ({
          ok: false,
          status: 409,
          data: { error: "the goal loop is off; enable HARNESS_GOAL_LOOP=on" },
        }),
      },
    ]);
    const out = await runGoal("/goal ship it", deps);
    expect(out.status).toBe("failed");
    expect(out.error?.code).toBe("GOAL_ENGINE_OFF");
    expect(out.blocks?.[0]).toMatchObject({ type: "callout" });
  });

  it("pins an explicit verifier type instead of guessing it from a code noun", async () => {
    const { deps, calls } = harness([tasksRoute, createRoute]);
    const out = await runGoal(
      "/goal research a strategy and backtest it on real data --type finance",
      deps,
    );
    expect(out.status).toBe("completed");
    const create = calls.find((call) => call.path === "/api/goals" && call.init?.method === "POST");
    expect((create!.init!.body as Record<string, unknown>).taskType).toBe("finance");
  });

  it("re-judges a blocked goal without starting a new turn", async () => {
    const { deps, calls } = harness([
      {
        match: (path) => path.startsWith("/api/goals?"),
        reply: () => ok({ goals: [{ id: "goal_1", status: "blocked", usedTurns: 2, maxTurns: 2 }] }),
      },
      {
        match: (path, init) => path.endsWith("/reevaluate") && init?.method === "POST",
        reply: () => ok({
          goal: { id: "goal_1", status: "completed", usedTurns: 2, maxTurns: 2 },
          verdict: { verdict: "done", reason: "verified" },
        }),
      },
    ]);
    const out = await runGoal("/goal retry", deps);
    expect(out.status).toBe("completed");
    expect(calls.some((call) => call.path.endsWith("/reevaluate"))).toBe(true);
    expect(JSON.stringify(out.blocks)).toContain("done");
  });

  it("extends a capped goal by a bounded number of turns", async () => {
    const { deps, calls } = harness([
      {
        match: (path) => path.startsWith("/api/goals?"),
        reply: () => ok({ goals: [{ id: "goal_1", status: "blocked", usedTurns: 5, maxTurns: 5 }] }),
      },
      {
        match: (path, init) => path.endsWith("/extend") && init?.method === "POST",
        reply: () => ok({ goal: { id: "goal_1", status: "active", usedTurns: 5, maxTurns: 10 } }),
      },
    ]);
    const out = await runGoal("/goal extend 5", deps);
    expect(out.status).toBe("completed");
    const extend = calls.find((call) => call.path.endsWith("/extend"));
    expect(extend?.init?.body).toEqual({ turns: 5 });
  });

  it("shows the gates and the verdict history", async () => {
    const { deps, calls } = harness([
      {
        match: (path) => path.startsWith("/api/goals?"),
        reply: () => ok({ goals: [{ id: "goal_1", status: "active" }] }),
      },
      {
        match: (path) => path === "/api/goals/goal_1",
        reply: () =>
          ok({
            goal: {
              id: "goal_1",
              objective: "ship it",
              status: "active",
              usedTurns: 2,
              maxTurns: 5,
              gates: [{ id: "gate-1", check: "typecheck" }],
            },
          }),
      },
      {
        match: (path) => path === "/api/goals/goal_1/verdicts",
        reply: () => ok({ verdicts: [{ turn: 2, verdict: "continue", reason: "typecheck failed" }] }),
      },
    ]);
    const out = await runGoal("/goal show goal_1", deps);
    expect(out.status).toBe("completed");
    const rendered = JSON.stringify(out.blocks);
    expect(rendered).toContain("typecheck");
    expect(rendered).toContain("continue");
    expect(calls.some((call) => call.path === "/api/goals/goal_1/verdicts")).toBe(true);
  });
});

describe("/loop", () => {
  const loopsRoute: Route = {
    match: (path) => path.startsWith("/api/loops?"),
    reply: () =>
      ok({
        loops: [{
          id: "loop_1", kind: "loop", status: "active", prompt: "check the build",
          intervalSeconds: 300, usedTicks: 0, maxTicks: 50,
        }],
      }),
  };

  it("lists the session's loops", async () => {
    const { deps } = harness([loopsRoute]);
    const out = await runLoop("/loop status", deps);
    expect(out.status).toBe("completed");
    expect(JSON.stringify(out.blocks)).toContain("check the build");
  });

  it("pauses and cancels a loop by id", async () => {
    const { deps, calls } = harness([
      loopsRoute,
      {
        match: (path, init) => path.endsWith("/cancel") && init?.method === "POST",
        reply: () => ok({ loop: { id: "loop_1", status: "cancelled", usedTicks: 0, maxTicks: 50 } }),
      },
    ]);
    const out = await runLoop("/loop cancel", deps);
    expect(out.status).toBe("completed");
    expect(calls.some((call) => call.path === "/api/loops/loop_1/cancel")).toBe(true);
  });
});
