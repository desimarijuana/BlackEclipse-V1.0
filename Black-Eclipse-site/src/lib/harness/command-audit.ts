// ─── Durable command audit (server-only) ───────────────────────────────────────
// One JSONL row per command execution, beside the other `.black-eclipse` state.
// The event is already redacted by the router: command id/name, actor, status,
// risk/approval, duration, skill/run id and an error CODE — never output,
// arguments or secrets. This is the record `/history` and `/usage --commands`
// read; it is intentionally not the chat transcript.

import fs from "node:fs/promises";
import path from "node:path";
import type { CommandAuditEvent } from "./command-router";

const MAX_BYTES = 2 * 1024 * 1024;
const MAX_READ = 2_000;

export function commandAuditPath(root = process.cwd()): string {
  return path.join(root, ".black-eclipse", "command-audit.jsonl");
}

function isEvent(value: unknown): value is CommandAuditEvent {
  if (!value || typeof value !== "object") return false;
  const row = value as Record<string, unknown>;
  return (
    typeof row.commandId === "string" &&
    typeof row.command === "string" &&
    typeof row.status === "string" &&
    typeof row.at === "string"
  );
}

/** Append one redacted audit event. Never throws to the caller. */
export async function appendCommandAudit(event: CommandAuditEvent, root = process.cwd()): Promise<void> {
  const file = commandAuditPath(root);
  await fs.mkdir(path.dirname(file), { recursive: true });
  try {
    const stat = await fs.stat(file);
    if (stat.size > MAX_BYTES) {
      // Windows refuses rename onto an existing target; replace the old roll.
      await fs.rm(`${file}.1`, { force: true });
      await fs.rename(file, `${file}.1`);
    }
  } catch {
    /* no file yet */
  }
  await fs.appendFile(file, `${JSON.stringify(event)}\n`, "utf8");
}

/** Read the newest events first. A missing/corrupt file is an empty audit. */
export async function readCommandAudit(limit = 50, root = process.cwd()): Promise<CommandAuditEvent[]> {
  const max = Math.max(1, Math.min(MAX_READ, Math.floor(limit) || 50));
  try {
    const raw = await fs.readFile(commandAuditPath(root), "utf8");
    const lines = raw.split(/\r?\n/).filter(Boolean);
    const out: CommandAuditEvent[] = [];
    for (let i = lines.length - 1; i >= 0 && out.length < max; i -= 1) {
      try {
        const parsed: unknown = JSON.parse(lines[i]);
        if (isEvent(parsed)) out.push(parsed);
      } catch {
        /* skip a partial/corrupt line */
      }
    }
    return out;
  } catch {
    return [];
  }
}

export interface CommandUsageRow {
  command: string;
  runs: number;
  completed: number;
  failed: number;
  p50Ms: number;
  p95Ms: number;
  lastAt: string;
}

export interface CommandAuditSummary {
  total: number;
  byStatus: Record<string, number>;
  byCommand: CommandUsageRow[];
  highRisk: number;
}

function percentile(values: number[], p: number): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil(p * sorted.length) - 1));
  return sorted[index];
}

/** Aggregate the audit for `/usage --commands`. Pure; newest-first input. */
export function summarizeCommandAudit(events: readonly CommandAuditEvent[]): CommandAuditSummary {
  const byStatus: Record<string, number> = {};
  const groups = new Map<string, { runs: number; completed: number; failed: number; durations: number[]; lastAt: string }>();
  let highRisk = 0;

  for (const event of events) {
    byStatus[event.status] = (byStatus[event.status] ?? 0) + 1;
    if (event.risk === "high" || event.risk === "critical") highRisk += 1;
    const group = groups.get(event.command) ?? {
      runs: 0,
      completed: 0,
      failed: 0,
      durations: [],
      lastAt: event.at,
    };
    group.runs += 1;
    if (event.status === "completed") group.completed += 1;
    if (event.status === "failed") group.failed += 1;
    if (Number.isFinite(event.durationMs)) group.durations.push(event.durationMs);
    if (event.at > group.lastAt) group.lastAt = event.at;
    groups.set(event.command, group);
  }

  const byCommand = [...groups.entries()]
    .map(([command, group]) => ({
      command,
      runs: group.runs,
      completed: group.completed,
      failed: group.failed,
      p50Ms: percentile(group.durations, 0.5),
      p95Ms: percentile(group.durations, 0.95),
      lastAt: group.lastAt,
    }))
    .sort((a, b) => b.runs - a.runs || a.command.localeCompare(b.command));

  return { total: events.length, byStatus, byCommand, highRisk };
}
