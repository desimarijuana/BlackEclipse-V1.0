// ─── Single-use confirmations for high-risk commands (server-only) ────────────
// The first invocation of a high/critical-risk command does not run. It returns
// a bounded, single-use token bound to the command id, its arguments/flags, the
// actor and operator flag. Re-running the same command with `--confirm <token>`
// consumes the token and executes. Tokens live in memory only (a restart
// invalidates them), expire after five minutes, and are never written to disk.

import { createHash, randomUUID } from "node:crypto";
import type { BoundArgs } from "./command-parser";
import type { CommandSpec } from "./command-registry";

const TTL_MS = 5 * 60_000;
const MAX_PENDING = 200;

interface PendingConfirmation {
  commandId: string;
  fingerprint: string;
  actor: "user" | "agent";
  operator: boolean;
  expiresAt: number;
}

const pending = new Map<string, PendingConfirmation>();

function sweep(now: number): void {
  for (const [token, entry] of pending) {
    if (entry.expiresAt <= now) pending.delete(token);
  }
  while (pending.size >= MAX_PENDING) {
    const oldest = pending.keys().next().value;
    if (oldest === undefined) break;
    pending.delete(oldest);
  }
}

function orderedFlags(flags: Record<string, string | boolean>): Array<[string, string | boolean]> {
  return Object.entries(flags)
    .filter(([name]) => name !== "confirm")
    .sort(([a], [b]) => a.localeCompare(b));
}

/** Stable fingerprint of a command invocation (positionals + non-confirm flags). */
export function commandFingerprint(spec: CommandSpec, args: BoundArgs): string {
  const payload = JSON.stringify({
    id: spec.id,
    positional: args.all,
    flags: orderedFlags(args.flags),
  });
  return createHash("sha256").update(payload).digest("hex");
}

export function issueConfirmation(input: {
  commandId: string;
  fingerprint: string;
  actor: "user" | "agent";
  operator: boolean;
  now: number;
}): { token: string; expiresAt: number } {
  sweep(input.now);
  const token = randomUUID();
  const expiresAt = input.now + TTL_MS;
  pending.set(token, {
    commandId: input.commandId,
    fingerprint: input.fingerprint,
    actor: input.actor,
    operator: input.operator,
    expiresAt,
  });
  return { token, expiresAt };
}

/** Consume a token exactly once. Returns false for unknown/expired/mismatched. */
export function consumeConfirmation(
  token: string,
  input: {
    commandId: string;
    fingerprint: string;
    actor: "user" | "agent";
    operator: boolean;
    now: number;
  },
): boolean {
  const entry = pending.get(token);
  if (!entry) return false;
  pending.delete(token);
  return (
    entry.expiresAt > input.now &&
    entry.commandId === input.commandId &&
    entry.fingerprint === input.fingerprint &&
    entry.actor === input.actor &&
    entry.operator === input.operator
  );
}

/** The exact command the user must send to approve (strips any stale --confirm). */
export function buildConfirmationCommand(spec: CommandSpec, rest: string, token: string): string {
  const cleaned = String(rest ?? "")
    .replace(/--confirm(?:=|\s+)\S+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return `/${spec.name}${cleaned ? ` ${cleaned}` : ""} --confirm ${token}`;
}

/** Test-only: clear pending tokens. */
export function resetConfirmationsForTests(): void {
  pending.clear();
}
