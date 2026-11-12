import { describe, it, expect } from "vitest";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import {
  appendCommandAudit,
  commandAuditPath,
  readCommandAudit,
  summarizeCommandAudit,
} from "./command-audit";
import type { CommandAuditEvent } from "./command-router";

function event(overrides: Partial<CommandAuditEvent>): CommandAuditEvent {
  return {
    commandId: "runtime.status",
    command: "status",
    actor: "user",
    operator: true,
    status: "completed",
    handlerTarget: "runtime.status",
    at: "2026-11-09T10:00:00.000Z",
    durationMs: 10,
    risk: "none",
    approval: "none",
    ...overrides,
  };
}

describe("command audit summary", () => {
  it("counts statuses, risk and per-command percentiles", () => {
    const summary = summarizeCommandAudit([
      event({ command: "terminal", commandId: "runtime.terminal", status: "completed", durationMs: 10, risk: "high" }),
      event({ command: "terminal", commandId: "runtime.terminal", status: "failed", durationMs: 40, risk: "high" }),
      event({ command: "terminal", commandId: "runtime.terminal", status: "completed", durationMs: 20, risk: "high" }),
      event({ command: "status", status: "denied", durationMs: 1 }),
    ]);

    expect(summary.total).toBe(4);
    expect(summary.byStatus).toEqual({ completed: 2, failed: 1, denied: 1 });
    expect(summary.highRisk).toBe(3);
    expect(summary.byCommand[0]).toMatchObject({
      command: "terminal",
      runs: 3,
      completed: 2,
      failed: 1,
      p50Ms: 20,
      p95Ms: 40,
    });
  });

  it("returns an empty summary for an empty audit", () => {
    expect(summarizeCommandAudit([])).toEqual({
      total: 0,
      byStatus: {},
      byCommand: [],
      highRisk: 0,
    });
  });

  it("handles a single duration without inventing a percentile", () => {
    const summary = summarizeCommandAudit([event({ durationMs: 7 })]);
    expect(summary.byCommand[0]).toMatchObject({ p50Ms: 7, p95Ms: 7 });
  });

  it("writes and reads JSONL newest-first, skipping corrupt lines", async () => {
    const root = await fs.mkdtemp(path.join(os.tmpdir(), "be-command-audit-"));
    try {
      await appendCommandAudit(event({ command: "status", at: "2026-11-09T10:00:00.000Z" }), root);
      await appendCommandAudit(event({ command: "terminal", at: "2026-11-09T10:01:00.000Z" }), root);
      await fs.appendFile(commandAuditPath(root), "{not json}\n", "utf8");

      const rows = await readCommandAudit(10, root);
      expect(rows.map((row) => row.command)).toEqual(["terminal", "status"]);
      expect(await readCommandAudit(1, root)).toHaveLength(1);
    } finally {
      await fs.rm(root, { recursive: true, force: true });
    }
  });
});
