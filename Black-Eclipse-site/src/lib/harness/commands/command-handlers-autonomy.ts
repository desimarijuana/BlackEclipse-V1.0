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
  "autonomy.goal": async (_ctx, _spec, args, deps) => {
    const words = (
      Array.isArray(args.positionals.objective) ? (args.positionals.objective as string[]) : []
    ).map((item) => String(item));
    const verb = (words[0] ?? "").toLowerCase();
    const control = ["status", "pause", "resume", "cancel"];

    if (control.includes(verb)) {
      const listed = await deps.frontDoor.request("/api/goals", { method: "GET" });
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
          ],
        };
      }
      const target = typeof words[1] === "string" && words[1].trim()
        ? goals.find((goal) => String(goal.id) === words[1].trim())
        : goals.find((goal) => ["active", "paused", "blocked"].includes(String(goal.status)));
      if (!target?.id) return invalid("NO_GOAL", `No goal to ${verb}. Pass a goal id, or start one with \`/goal <objective>\`.`);
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
      .map((check, index) => ({ id: `gate-${index + 1}`, check }));
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
    const workspaceId = typeof args.flags.workspace === "string" ? args.flags.workspace : undefined;
    const res = await deps.frontDoor.request("/api/goals", {
      method: "POST",
      body: {
        objective,
        gates,
        acceptance,
        maxTurns: Number.isFinite(maxTurns) ? maxTurns : undefined,
        workspaceId,
      },
      timeoutMs: 60_000,
    });
    if (!res.ok) return fail("GOAL_FAILED", frontDoorError(res.data, res.status));
    const goal = ((res.data as { goal?: Record<string, unknown> }).goal ?? {});
    return {
      status: "completed",
      blocks: [
        heading("Goal started", 2),
        keyValue("Goal", [
          { label: "Id", value: String(goal.id ?? "-") },
          { label: "Status", value: String(goal.status ?? "active") },
          { label: "Turns", value: `${String(goal.usedTurns ?? 0)}/${String(goal.maxTurns ?? "-")}` },
          { label: "Gates", value: gates.length ? gates.map((gate) => gate.check).join(", ") : "none (judge only)" },
        ]),
        callout(
          "note",
          "Bounded",
          "A failing gate never completes the goal. Pause or cancel any time with /goal pause or /goal cancel.",
        ),
      ],
    };
  },

  "autonomy.loop": async (ctx, _spec, args, deps) => {
    if (!ctx.chatId) return invalid("NO_SESSION", "A loop needs an open chat session.");
    const words = (
      Array.isArray(args.positionals.spec) ? (args.positionals.spec as string[]) : []
    ).map((item) => String(item));
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
