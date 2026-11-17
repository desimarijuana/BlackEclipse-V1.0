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
      "A failing gate never completes the goal; the advisory judge is consulted only after every gate passes, " +
      "and a `done` verdict must also pass the task-type verifier. " +
      "Use `/goal status`, `/goal show <id>`, `/goal pause|resume|cancel`, `/goal retry`, or `/goal extend <turns>` to inspect or control it.",
    category: "runtime",
    tags: ["autonomy", "goal", "loop"],
    version,
    status: "available",
    args: [{ name: "objective", description: "What to achieve, or a control word (status, show, pause, resume, cancel, extend).", variadic: true }],
    flags: [
      {
        name: "gate",
        description: "A deterministic check that must pass (repeatable). `check=path` scopes a file/check.",
        type: "string",
        values: ["unit_test", "python_test", "typecheck", "lint", "build", "format_check"],
        repeatable: true,
      },
      { name: "turns", description: "Maximum turns (or extra turns for `extend`).", type: "number" },
      { name: "workspace", description: "Workspace id the gates run in (defaults to the session's newest workspace).", type: "string" },
      { name: "accept", description: "An acceptance line (repeatable).", type: "string", repeatable: true },
      { name: "autonomy", description: "Execution profile for the goal's turns.", type: "string", values: ["plan_only", "edit_verify", "approve_external"] },
      { name: "type", description: "Pin the completion verifier class.", type: "string", values: ["code", "research", "document", "workflow", "finance", "data", "general"] },
      { name: "parallel", description: "Allow a second active goal in this session.", type: "boolean" },
    ],
    handler: { type: "native", target: "autonomy.goal" },
    permissions: { approval: "none" },
    risk: "medium",
    executionMode: "async",
    output: { type: "response", summary: "The goal id, turn count and last verdict." },
    examples: [
      "/goal ship the watchlist widget with passing checks --gate typecheck",
      "/goal fix the parser --gate unit_test=src/lib/parse.test.ts --turns 6",
      "/goal status",
      "/goal show goal_abc123",
      "/goal extend 5",
    ],
  };

  const LOOP: CommandSpec = {
    id: "autonomy.loop",
    name: "loop",
    aliases: [],
    summary: "Repeat a prompt on a cadence in this session.",
    description:
      "Start a session loop that runs the prompt on an interval (for example `5m`) until its tick cap. " +
      "A loop never fires while the session is busy, and an unchanged reply pauses it. " +
      "Use `/loop status`, `/loop pause`, `/loop resume` or `/loop cancel` to inspect or control it.",
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
