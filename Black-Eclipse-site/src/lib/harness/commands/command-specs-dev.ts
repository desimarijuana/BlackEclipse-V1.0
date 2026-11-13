// ─── Dev command specs ────────────────────────────────────────────────────────
// Extracted from command-registry.ts to keep the canonical catalog under its
// size ratchet: /rollback (file checkpoints) and /terminal (host shell).

import type { CommandSpec } from "./command-registry";

export function devCommandSpecs(V: string): CommandSpec[] {
const ROLLBACK: CommandSpec = {
  id: "code.rollback",
  name: "rollback",
  aliases: ["checkpoints"],
  summary: "Undo the agent's recent file changes.",
  description:
    "List the file snapshots Eclipse took, show what changed, and restore one. " +
    "Restores the named paths by default; `--all` restores every tracked change. " +
    "A pre-restore snapshot is always taken, so a restore is itself undoable. " +
    "Operator-gated; never runs an agent turn.",
  category: "dev",
  tags: ["dev", "safety", "files"],
  version: V,
  status: "available",
  args: [
    { name: "checkpointId", description: "The snapshot id; omit to list recent snapshots.", required: false },
  ],
  flags: [
    { name: "all", description: "Restore every tracked change in the snapshot.", type: "boolean" },
    { name: "paths", description: "Comma-separated paths to restore.", type: "string" },
    { name: "confirm", description: "Single-use confirmation token from the first invocation.", type: "string" },
  ],
  handler: { type: "native", target: "code.rollback" },
  permissions: { approval: "operator" },
  risk: "high",
  executionMode: "sync",
  timeoutMs: 120_000,
  output: { type: "response", summary: "Snapshots, a diff, or the restored paths." },
  examples: ["/rollback", "/rollback cp_20261112T190000Z_ab12cd34", "/rollback cp_... --all"],
};

const TERMINAL: CommandSpec = {
  id: "runtime.terminal",
  name: "terminal",
  aliases: ["run", "sh"],
  summary: "Run a shell command.",
  description:
    "Execute a shell command through the terminal subsystem (operator-gated, effect-gated) and show its output. Never run untrusted content as a command.",
  category: "dev",
  tags: ["dev", "terminal", "shell"],
  version: V,
  status: "available",
  args: [{ name: "command", description: "The command to run.", variadic: true }],
  flags: [
    {
      name: "shell",
      description: "Which shell to run in. Defaults to the host shell.",
      type: "string",
      values: ["powershell", "cmd", "wsl", "bash"],
    },
    {
      name: "cwd",
      description: "Working directory, relative to the workspace root.",
      type: "string",
    },
    {
      name: "confirm",
      description: "Single-use confirmation token from the first invocation.",
      type: "string",
    },
  ],
  handler: { type: "native", target: "runtime.terminal" },
  permissions: { approval: "operator" },
  risk: "high",
  executionMode: "sync",
  timeoutMs: 900_000,
  output: { type: "response", summary: "stdout/stderr, the exit code, the shell and the working directory." },
  examples: [
    "/terminal ls -la",
    "/run git status",
    "/terminal --shell cmd dir /s",
    "/terminal --shell powershell --cwd src npm run test",
  ],
};

  return [ROLLBACK, TERMINAL];
}
