import { describe, expect, it } from "vitest";
import {
  busiestQueues,
  formatDuration,
  isTerminalStatus,
  jobProgressLabel,
  priorityLabel,
  statusTone,
  summarizeQueues,
  type FabricQueueStat,
} from "./fabric-types";

function q(partial: Partial<FabricQueueStat>): FabricQueueStat {
  return {
    queue: "agent", waiting: 0, active: 0, delayed: 0, completed: 0, failed: 0, dlq: 0, total: 0,
    ...partial,
  };
}

describe("fabric view helpers", () => {
  it("knows terminal states", () => {
    expect(isTerminalStatus("SUCCEEDED")).toBe(true);
    expect(isTerminalStatus("DEAD_LETTER")).toBe(true);
    expect(isTerminalStatus("RUNNING")).toBe(false);
  });

  it("maps status to a tone", () => {
    expect(statusTone("SUCCEEDED")).toContain("emerald");
    expect(statusTone("FAILED")).toContain("red");
    expect(statusTone("RUNNING")).toContain("sky");
  });

  it("formats durations honestly", () => {
    expect(formatDuration(0)).toBe("—");
    expect(formatDuration(250)).toBe("250ms");
    expect(formatDuration(1500)).toBe("1.5s");
    expect(formatDuration(65_000)).toBe("1m 5s");
  });

  it("labels progress by state", () => {
    expect(jobProgressLabel({ status: "RUNNING", progress: 0.62, attempts: 1, maxAttempts: 3 }))
      .toBe("62% · attempt 1/3");
    expect(jobProgressLabel({ status: "QUEUED", progress: 0, attempts: 0, maxAttempts: 1 })).toBe("QUEUED");
    expect(jobProgressLabel({ status: "DEAD_LETTER", progress: 1, attempts: 3, maxAttempts: 3 }))
      .toBe("attempt 3/3");
  });

  it("summarizes queue totals", () => {
    const total = summarizeQueues([
      q({ queue: "a", waiting: 2, active: 1, completed: 5, total: 8 }),
      q({ queue: "b", failed: 3, dlq: 1, total: 4 }),
    ]);
    expect(total).toMatchObject({ waiting: 2, active: 1, completed: 5, failed: 3, dlq: 1, total: 12 });
  });

  it("orders busiest queues and drops empty ones", () => {
    const rows = busiestQueues([
      q({ queue: "idle", total: 0 }),
      q({ queue: "busy", waiting: 5, total: 5 }),
      q({ queue: "some", active: 1, total: 1 }),
    ]);
    expect(rows.map((r) => r.queue)).toEqual(["busy", "some"]);
  });

  it("labels priorities", () => {
    expect(priorityLabel(1000)).toBe("USER_REQUEST");
    expect(priorityLabel(500)).toBe("RESEARCH");
    expect(priorityLabel(240)).toBe("INGESTION");
  });
});
