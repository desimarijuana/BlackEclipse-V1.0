// ─── W4 autonomy command specs ────────────────────────────────────────────────
// Extracted from command-registry.ts to keep the canonical catalog under its
// size ratchet. `autonomyCommandSpecs(version)` returns the three specs; the
// registry spreads them in the same order.

import type { CommandSpec } from "./command-registry";

export function autonomyCommandSpecs(version: string): CommandSpec[] {
  const GOAL: CommandSpec = {
    id: "autonomy.goal",
    name: "goal",
    aliases: [],
    summary: "Set an objective Eclipse works toward until its gates pass.",
    description:
      "Create a durable goal with a contract, optional deterministic gates and a turn cap. " +
      "A failing gate never completes the goal; the advisory judge is consulted only after every gate passes. " +
      "Use `/goal status`, `/goal pause`, `/goal resume` or `/goal cancel` to inspect or control the most recent goal.",
    category: "runtime",
    tags: ["autonomy", "goal", "loop"],
    version,
    status: "available",
    args: [{ name: "objective", description: "What to achieve, or a control word.", variadic: true }],
    flags: [
      {
        name: "gate",
        description: "A deterministic check that must pass (repeatable).",
        type: "string",
        values: ["unit_test", "python_test", "typecheck", "lint", "build", "format_check"],
      },
      { name: "turns", description: "Maximum turns.", type: "number" },
      { name: "workspace", description: "Workspace id the gates run in.", type: "string" },
      { name: "accept", description: "An acceptance line (repeatable).", type: "string" },
    ],
    handler: { type: "native", target: "autonomy.goal" },
    permissions: { approval: "none" },
    risk: "medium",
    executionMode: "async",
    output: { type: "response", summary: "The goal id, turn count and last verdict." },
    examples: [
      "/goal ship the watchlist widget with passing checks --gate typecheck",
      "/goal status",
      "/goal pause",
    ],
  };

  const LOOP: CommandSpec = {
    id: "autonomy.loop",
    name: "loop",
    aliases: [],
    summary: "Repeat a prompt on a cadence in this session.",
    description:
      "Start a session loop that runs the prompt on an interval (for example `5m`) until its tick cap. " +
      "A loop never fires while the session is busy, and an unchanged reply pauses it.",
    category: "runtime",
    tags: ["autonomy", "loop", "cadence"],
    version,
    status: "available",
    args: [{ name: "spec", description: "Optional interval, then the prompt.", variadic: true }],
    flags: [
      { name: "mode", description: "Fixed or self-paced.", type: "string", values: ["fixed", "self-paced"] },
      { name: "ticks", description: "Maximum ticks.", type: "number" },
    ],
    handler: { type: "native", target: "autonomy.loop" },
    permissions: { approval: "none" },
    risk: "low",
    executionMode: "async",
    output: { type: "response", summary: "The loop id, cadence and next tick." },
    examples: ["/loop 5m check the build", "/loop --mode self-paced summarize new issues"],
  };

  const HEARTBEAT: CommandSpec = {
    id: "autonomy.heartbeat",
    name: "heartbeat",
    aliases: ["hb"],
    summary: "Wake this session when it is idle.",
    description:
      "Start an idle-only heartbeat in this session. Missed ticks coalesce to one, a user message wins, " +
      "and an unchanged reply is not delivered.",
    category: "runtime",
    tags: ["autonomy", "heartbeat", "idle"],
    version,
    status: "available",
    args: [{ name: "spec", description: "`every <interval> <prompt>`.", variadic: true }],
    flags: [
      { name: "mode", description: "Fixed or self-paced.", type: "string", values: ["fixed", "self-paced"] },
      { name: "ticks", description: "Maximum ticks.", type: "number" },
    ],
    handler: { type: "native", target: "autonomy.heartbeat" },
    permissions: { approval: "none" },
    risk: "low",
    executionMode: "async",
    output: { type: "response", summary: "The heartbeat id, cadence and next tick." },
    examples: ["/heartbeat every 10m check for new alerts"],
  };

  return [GOAL, LOOP, HEARTBEAT];
}
