// ─── W4 autonomy command handlers ─────────────────────────────────────────────
// Extracted from command-handlers.ts to keep the dispatch table under its size
// ratchet. These handlers call the front door only; they own no loop or storage.

import {
  fail,
  frontDoorError,
  invalid,
  type Handler,
  type HandlerOutput,
} from "./command-handler-kit";
import { callout, heading, keyValue } from "./command-render";
import type { CommandDeps } from "./command-router";

export const autonomyHandlers: Record<string, Handler> = {
  "autonomy.goal": async (ctx, _spec, args, deps) => {
    const words = (
      Array.isArray(args.positionals.objective) ? (args.positionals.objective as string[]) : []
    ).map((item) => String(item));
    const verb = (words[0] ?? "").toLowerCase();
    const control = ["status", "show", "pause", "resume", "cancel", "extend", "retry", "reevaluate"];

    if (control.includes(verb)) {
      const listed = await deps.frontDoor.request(
        `/api/goals${ctx.chatId ? `?sessionId=${encodeURIComponent(ctx.chatId)}` : ""}`,
        { method: "GET" },
      );
      if (!listed.ok) return fail("GOAL_LIST_FAILED", frontDoorError(listed.data, listed.status));
      const goals = ((listed.data as { goals?: Array<Record<string, unknown>> }).goals ?? []);
      if (verb === "status") {
        if (!goals.length) return { status: "completed", markdownText: "No goals yet. Start one with `/goal <objective>`." };
        return {
          status: "completed",
          blocks: [
            heading("Goals", 2),
            keyValue("Latest", goals.slice(0, 5).map((goal) => ({
              label: String(goal.objective ?? goal.id ?? "goal").slice(0, 60),
              value: `${String(goal.status ?? "-")} · ${String(goal.usedTurns ?? 0)}/${String(goal.maxTurns ?? "-")} turns`,
            }))),
            callout("note", "Details", "`/goal show <id>` prints the gates and every verdict."),
          ],
        };
      }
      const activeGoal = goals.find((goal) =>
        ["active", "paused", "blocked"].includes(String(goal.status)),
      );
      const firstArg = typeof words[1] === "string" ? words[1].trim() : "";
      // `/goal extend 5` names TURNS, not a goal id. A numeric argument is
      // never a valid id, so it is unambiguous.
      const extendTurns = verb === "extend" && /^\d+$/.test(firstArg) ? Number(firstArg) : undefined;
      const target = verb === "extend" && extendTurns !== undefined
        ? activeGoal
        : firstArg
          ? goals.find((goal) => String(goal.id) === firstArg)
          : activeGoal;
      if (!target?.id) return invalid("NO_GOAL", `No goal to ${verb}. Pass a goal id, or start one with \`/goal <objective>\`.`);

      if (verb === "show") {
        const [detail, verdicts] = await Promise.all([
          deps.frontDoor.request(`/api/goals/${encodeURIComponent(String(target.id))}`, { method: "GET" }),
          deps.frontDoor.request(`/api/goals/${encodeURIComponent(String(target.id))}/verdicts`, { method: "GET" }),
        ]);
        if (!detail.ok) return fail("GOAL_READ_FAILED", frontDoorError(detail.data, detail.status));
        const goal = ((detail.data as { goal?: Record<string, unknown> }).goal ?? target);
        const history = ((verdicts.ok ? (verdicts.data as { verdicts?: Array<Record<string, unknown>> }).verdicts : []) ?? []);
        const gates = Array.isArray(goal.gates) ? (goal.gates as Array<Record<string, unknown>>) : [];
        return {
          status: "completed",
          blocks: [
            heading("Goal", 2),
            keyValue("Goal", [
              { label: "Id", value: String(goal.id ?? "-") },
              { label: "Status", value: String(goal.status ?? "-") },
              { label: "Objective", value: String(goal.objective ?? "-") },
              { label: "Turns", value: `${String(goal.usedTurns ?? 0)}/${String(goal.maxTurns ?? "-")}` },
              { label: "Workspace", value: String(goal.workspaceId ?? "none") },
              { label: "Gates", value: gates.length ? gates.map((gate) => String(gate.check ?? gate.id)).join(", ") : "none (judge + verifier)" },
            ]),
            keyValue("Last verdicts", history.slice(0, 5).map((item) => ({
              label: `turn ${String(item.turn ?? "-")}`,
              value: `${String(item.verdict ?? "-")}: ${String(item.reason ?? "").slice(0, 120)}`,
            }))),
          ],
        };
      }

      if (verb === "retry" || verb === "reevaluate") {
        const res = await deps.frontDoor.request(
          `/api/goals/${encodeURIComponent(String(target.id))}/reevaluate`,
          { method: "POST", body: {}, timeoutMs: 180_000 },
        );
        if (!res.ok) return fail("GOAL_ACTION_FAILED", frontDoorError(res.data, res.status));
        const goal = ((res.data as { goal?: Record<string, unknown> }).goal ?? {});
        const verdict = ((res.data as { verdict?: Record<string, unknown> }).verdict ?? {});
        return {
          status: "completed",
          blocks: [
            heading("Goal re-judged", 2),
            keyValue("Goal", [
              { label: "Id", value: String(goal.id ?? target.id) },
              { label: "Status", value: String(goal.status ?? "-") },
              { label: "Turns", value: `${String(goal.usedTurns ?? 0)}/${String(goal.maxTurns ?? "-")}` },
              { label: "Verdict", value: String(verdict.verdict ?? "-") },
              { label: "Reason", value: String(verdict.reason ?? "-").slice(0, 240) },
            ]),
          ],
        };
      }

      if (verb === "extend") {
        const requested = extendTurns
          ?? (typeof args.flags.turns === "number"
            ? args.flags.turns
            : Number(words[2] ?? args.flags.turns ?? 5));
        const turns = Number.isFinite(requested) ? Math.max(1, Math.min(Math.trunc(requested), 100)) : 5;
        const res = await deps.frontDoor.request(
          `/api/goals/${encodeURIComponent(String(target.id))}/extend`,
          { method: "POST", body: { turns } },
        );
        if (!res.ok) return fail("GOAL_ACTION_FAILED", frontDoorError(res.data, res.status));
        const goal = ((res.data as { goal?: Record<string, unknown> }).goal ?? {});
        return {
          status: "completed",
          blocks: [
            heading("Goal extended", 2),
            keyValue("Goal", [
              { label: "Id", value: String(goal.id ?? target.id) },
              { label: "Status", value: String(goal.status ?? "-") },
              { label: "Turns", value: `${String(goal.usedTurns ?? 0)}/${String(goal.maxTurns ?? "-")}` },
            ]),
          ],
        };
      }

      const res = await deps.frontDoor.request(
        `/api/goals/${encodeURIComponent(String(target.id))}/${verb}`,
        { method: "POST", body: { reason: "chat command" } },
      );
      if (!res.ok) return fail("GOAL_ACTION_FAILED", frontDoorError(res.data, res.status));
      const goal = ((res.data as { goal?: Record<string, unknown> }).goal ?? {});
      return {
        status: "completed",
        blocks: [
          heading(`Goal ${verb}`, 2),
          keyValue("Goal", [
            { label: "Id", value: String(goal.id ?? target.id) },
            { label: "Status", value: String(goal.status ?? "-") },
            { label: "Turns", value: `${String(goal.usedTurns ?? 0)}/${String(goal.maxTurns ?? "-")}` },
          ]),
        ],
      };
    }

    const objective = words.join(" ").trim();
    if (!objective) {
      return invalid("MISSING_ARG", "Usage: `/goal <objective>`, optionally `--gate typecheck --turns 10 --workspace <id>`.");
    }
    const gateValues = Array.isArray(args.flags.gate)
      ? (args.flags.gate as unknown[])
      : args.flags.gate !== undefined ? [args.flags.gate] : [];
    const gates = gateValues
      .filter((value): value is string => typeof value === "string" && value.trim().length > 0)
      .slice(0, 12)
      .map((raw, index) => parseGateSpec(raw, index))
      .filter((gate): gate is { id: string; check: string; args: Record<string, unknown> } => gate !== null);
    const acceptValues = Array.isArray(args.flags.accept)
      ? (args.flags.accept as unknown[])
      : args.flags.accept !== undefined ? [args.flags.accept] : [];
    const acceptance = acceptValues.filter(
      (value): value is string => typeof value === "string" && value.trim().length > 0,
    ).slice(0, 24);
    const maxTurns = typeof args.flags.turns === "number"
      ? args.flags.turns
      : typeof args.flags.turns === "string" && args.flags.turns.trim()
        ? Number(args.flags.turns)
        : undefined;
    const explicitWorkspace = typeof args.flags.workspace === "string" ? args.flags.workspace : undefined;
    // A gate with no workspace is a guaranteed dead end, and a user has no way
    // to know a workspace id. Use the session's newest live workspace.
    const workspaceId = explicitWorkspace
      ?? (gates.length ? await findSessionWorkspace(deps, ctx.chatId) : undefined);
    if (gates.length && !workspaceId) {
      return invalid(
        "NO_WORKSPACE",
        "Gates need a live workspace. Open a code task first, or pass `--workspace <id>`.",
      );
    }
    const autonomy = typeof args.flags.autonomy === "string"
      && ["plan_only", "edit_verify", "approve_external"].includes(args.flags.autonomy)
      ? args.flags.autonomy
      : undefined;
    const taskType = typeof args.flags.type === "string"
      && ["code", "research", "document", "workflow", "finance", "data", "general"].includes(args.flags.type)
      ? args.flags.type
      : undefined;
    const res = await deps.frontDoor.request("/api/goals", {
      method: "POST",
      body: {
        objective,
        gates,
        acceptance,
        maxTurns: Number.isFinite(maxTurns) ? maxTurns : undefined,
        workspaceId,
        sessionId: ctx.chatId,
        autonomy,
        taskType,
        allowParallel: args.flags.parallel === true,
      },
      timeoutMs: 60_000,
    });
    if (!res.ok) {
      const message = frontDoorError(res.data, res.status);
      if (/goal loop is off|GOAL_ENGINE_OFF/i.test(message)) {
        return {
          status: "failed",
          error: { code: "GOAL_ENGINE_OFF", message },
          blocks: [
            callout("warning", "Goal loop is off", message),
            callout("note", "How to enable", "Set `HARNESS_GOAL_LOOP=on` (or `shadow` to record verdicts only) and restart the runtime."),
          ],
        };
      }
      if (/already has an active goal/i.test(message)) {
        return invalid("GOAL_ALREADY_ACTIVE", `${message} Finish it with \`/goal cancel\` first.`);
      }
      return fail("GOAL_FAILED", message);
    }
    const goal = ((res.data as { goal?: Record<string, unknown> }).goal ?? {});
    return {
      status: "completed",
      blocks: [
        heading("Goal started", 2),
        keyValue("Goal", [
          { label: "Id", value: String(goal.id ?? "-") },
          { label: "Status", value: String(goal.status ?? "active") },
          { label: "Turns", value: `${String(goal.usedTurns ?? 0)}/${String(goal.maxTurns ?? "-")}` },
          { label: "Workspace", value: String(workspaceId ?? "none") },
          { label: "Gates", value: gates.length ? gates.map((gate) => gate.check).join(", ") : "none (judge + verifier)" },
        ]),
        callout(
          "note",
          "Bounded",
          "A failing gate never completes the goal, and a judge `done` must also pass the task verifier. " +
            "Pause or cancel any time with /goal pause or /goal cancel.",
        ),
      ],
    };
  },

  "autonomy.loop": async (ctx, _spec, args, deps) => {
    if (!ctx.chatId) return invalid("NO_SESSION", "A loop needs an open chat session.");
    const words = (
      Array.isArray(args.positionals.spec) ? (args.positionals.spec as string[]) : []
    ).map((item) => String(item));
    const verb = (words[0] ?? "").toLowerCase();
    const control = ["status", "pause", "resume", "cancel"];
    if (control.includes(verb)) {
      const listed = await deps.frontDoor.request(
        `/api/loops?sessionId=${encodeURIComponent(ctx.chatId)}`,
        { method: "GET" },
      );
      if (!listed.ok) return fail("LOOP_LIST_FAILED", frontDoorError(listed.data, listed.status));
      const loops = ((listed.data as { loops?: Array<Record<string, unknown>> }).loops ?? []);
      if (verb === "status") {
        if (!loops.length) return { status: "completed", markdownText: "No loops in this session. Start one with `/loop 5m <prompt>`." };
        return {
          status: "completed",
          blocks: [
            heading("Loops", 2),
            keyValue("Active", loops.slice(0, 5).map((item) => ({
              label: String(item.prompt ?? item.id ?? "loop").slice(0, 60),
              value: `${String(item.kind ?? "loop")} · ${String(item.status ?? "-")} · every ${String(item.intervalSeconds ?? "-")}s · ${String(item.usedTicks ?? 0)}/${String(item.maxTicks ?? "-")} ticks`,
            }))),
          ],
        };
      }
      const target = typeof words[1] === "string" && words[1].trim()
        ? loops.find((item) => String(item.id) === words[1].trim())
        : loops.find((item) => ["active", "paused"].includes(String(item.status)));
      if (!target?.id) return invalid("NO_LOOP", `No loop to ${verb}. Pass a loop id, or start one with \`/loop 5m <prompt>\`.`);
      const res = await deps.frontDoor.request(
        `/api/loops/${encodeURIComponent(String(target.id))}/${verb}`,
        { method: "POST", body: { reason: "chat command" } },
      );
      if (!res.ok) return fail("LOOP_ACTION_FAILED", frontDoorError(res.data, res.status));
      const loop = ((res.data as { loop?: Record<string, unknown> }).loop ?? {});
      return {
        status: "completed",
        blocks: [
          heading(`Loop ${verb}`, 2),
          keyValue("Loop", [
            { label: "Id", value: String(loop.id ?? target.id) },
            { label: "Status", value: String(loop.status ?? "-") },
            { label: "Ticks", value: `${String(loop.usedTicks ?? 0)}/${String(loop.maxTicks ?? "-")}` },
          ]),
        ],
      };
    }
    let intervalSeconds = 300;
    if (words.length) {
      const match = /^(\d+)\s*(s|m|h)?$/i.exec(words[0]);
      if (match) {
        const unit = (match[2] ?? "m").toLowerCase();
        intervalSeconds = Number(match[1]) * (unit === "h" ? 3600 : unit === "m" ? 60 : 1);
        words.shift();
      }
    }
    const prompt = words.join(" ").trim();
    if (!prompt) return invalid("MISSING_ARG", "Usage: `/loop [interval] <prompt>` (for example `/loop 5m check the build`).");
    return startCadence(ctx, deps, "loop", prompt, intervalSeconds, args.flags);
  },

  "autonomy.heartbeat": async (ctx, _spec, args, deps) => {
    if (!ctx.chatId) return invalid("NO_SESSION", "A heartbeat needs an open chat session.");
    const words = (
      Array.isArray(args.positionals.spec) ? (args.positionals.spec as string[]) : []
    ).map((item) => String(item));
    if ((words[0] ?? "").toLowerCase() === "every") words.shift();
    let intervalSeconds = 600;
    if (words.length) {
      const match = /^(\d+)\s*(s|m|h)?$/i.exec(words[0]);
      if (match) {
        const unit = (match[2] ?? "m").toLowerCase();
        intervalSeconds = Number(match[1]) * (unit === "h" ? 3600 : unit === "m" ? 60 : 1);
        words.shift();
      }
    }
    const prompt = words.join(" ").trim();
    if (!prompt) {
      return invalid("MISSING_ARG", "Usage: `/heartbeat every <interval> <prompt>` (for example `/heartbeat every 10m check alerts`).");
    }
    return startCadence(ctx, deps, "heartbeat", prompt, intervalSeconds, args.flags);
  },
};

// The closed gate vocabulary and the argument name each class accepts. A gate
// is never a shell string: the server validates every argument against the
// class's ArgSpec, so `check=path` can only ever narrow a known check.
const GATE_ARG_NAME: Record<string, string> = {
  unit_test: "files",
  python_test: "paths",
  format_check: "files",
};

function parseGateSpec(
  raw: string,
  index: number,
): { id: string; check: string; args: Record<string, unknown> } | null {
  const text = raw.trim();
  if (!text) return null;
  const eq = text.indexOf("=");
  const check = (eq >= 0 ? text.slice(0, eq) : text).trim().toLowerCase();
  if (!check) return null;
  const args: Record<string, unknown> = {};
  const argName = GATE_ARG_NAME[check];
  if (eq >= 0 && argName) {
    const values = text.slice(eq + 1).split(",").map((item) => item.trim()).filter(Boolean).slice(0, 32);
    if (values.length) args[argName] = values;
  }
  return { id: `gate-${index + 1}`, check, args };
}

/** The newest live workspace this chat can run gates in, or undefined. */
async function findSessionWorkspace(
  deps: CommandDeps,
  sessionId?: string,
): Promise<string | undefined> {
  const res = await deps.frontDoor.request("/api/code/tasks", { method: "GET" });
  if (!res.ok) return undefined;
  const tasks = ((res.data as { tasks?: Array<Record<string, unknown>> }).tasks ?? []);
  const withWorkspace = tasks.filter((task) => typeof task.workspaceId === "string" && task.workspaceId);
  const owned = sessionId
    ? withWorkspace.find((task) => String(task.sessionId ?? "") === sessionId)
    : undefined;
  const chosen = owned ?? withWorkspace[0];
  return chosen ? String(chosen.workspaceId) : undefined;
}

async function startCadence(
  ctx: { chatId?: string },
  deps: CommandDeps,
  kind: "loop" | "heartbeat",
  prompt: string,
  intervalSeconds: number,
  flags: Record<string, unknown>,
): Promise<HandlerOutput> {
  const mode = flags.mode === "self-paced" || flags.mode === "self_paced" ? "self_paced" : "fixed";
  const maxTicks = typeof flags.ticks === "number"
    ? flags.ticks
    : typeof flags.ticks === "string" && flags.ticks.trim()
      ? Number(flags.ticks)
      : undefined;
  const res = await deps.frontDoor.request("/api/loops", {
    method: "POST",
    body: {
      sessionId: ctx.chatId,
      kind,
      prompt,
      intervalSeconds,
      mode,
      maxTicks: Number.isFinite(maxTicks) ? maxTicks : undefined,
    },
    timeoutMs: 60_000,
  });
  if (!res.ok) return fail("LOOP_FAILED", frontDoorError(res.data, res.status));
  const loop = ((res.data as { loop?: Record<string, unknown> }).loop ?? {});
  return {
    status: "completed",
    blocks: [
      heading(kind === "heartbeat" ? "Heartbeat started" : "Loop started", 2),
      keyValue(kind === "heartbeat" ? "Heartbeat" : "Loop", [
        { label: "Id", value: String(loop.id ?? "-") },
        { label: "Status", value: String(loop.status ?? "active") },
        { label: "Every", value: `${String(loop.intervalSeconds ?? intervalSeconds)}s (${mode})` },
        { label: "Next tick", value: String(loop.nextTickAt ?? "scheduled") },
        { label: "Ticks", value: `${String(loop.usedTicks ?? 0)}/${String(loop.maxTicks ?? "-")}` },
      ]),
      callout(
        "note",
        "Idle-aware",
        kind === "heartbeat"
          ? "It waits while you are active, coalesces missed ticks, and stops when the reply stops changing."
          : "It never fires while this session is busy, and an unchanged reply pauses it.",
      ),
    ],
  };
}
