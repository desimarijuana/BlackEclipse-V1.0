import { describe, it, expect, vi, beforeEach } from "vitest";

// Integration coverage for the alert poll→evaluate→gate→dispatch path. The
// Prisma client, data feeds and dispatcher are faked so the test drives the
// REAL evaluator + monitor gating (edge / one-shot / warmup / error), which had
// no coverage before — only the pure evaluator and the create route were tested.

interface Row {
  id: string;
  name: string;
  symbols: string;
  conditions: string;
  logic: string;
  timeframe: string;
  market: string;
  cooldownMin: number;
  intervalSec: number;
  active: boolean;
  lastFiredAt: Date | null;
  status?: string;
  statusMsg?: string | null;
}

const state: { rows: Map<string, Row>; updates: Array<Record<string, unknown>> } = {
  rows: new Map(),
  updates: [],
};

vi.mock("@/lib/db", () => ({
  prisma: {
    priceAlert: {
      findUnique: vi.fn(async ({ where }: { where: { id: string } }) => state.rows.get(where.id) ?? null),
      update: vi.fn(async ({ where, data }: { where: { id: string }; data: Record<string, unknown> }) => {
        state.updates.push(data);
        const row = state.rows.get(where.id);
        if (row) Object.assign(row, data);
        return row;
      }),
      findMany: vi.fn(async () => [...state.rows.values()]),
    },
  },
}));

const dispatchAlert = vi.fn(async (..._a: unknown[]) => ({ delivered: [] as string[], failed: [] as string[] }));
vi.mock("@/lib/alerts/notifier", () => ({ dispatchAlert: (...a: unknown[]) => dispatchAlert(...a) }));

const fetchSnapshots = vi.fn(async (..._a: unknown[]) => new Map<string, { symbol: string; close: number }>());
vi.mock("@/lib/alerts/dataFeeds", () => ({
  MIN_INTERVAL_SEC: 30,
  fetchSnapshots: (...a: unknown[]) => fetchSnapshots(...a),
  snapshotWindow: () => new Map([["CLOSE()", [150]]]),
  updateCandleCache: vi.fn(async () => 0),
  indicatorWindow: vi.fn(async () => new Map()),
  hasWarmupBars: vi.fn(async () => true),
  referencedIndicators: vi.fn(() => []),
}));

import { evaluateOnce } from "@/lib/alerts/alertMonitor";

function row(partial: Partial<Row> & { id: string }): Row {
  return {
    name: "Watch",
    symbols: '["AAPL"]',
    conditions: JSON.stringify([
      { indicator: "CLOSE", operator: ">", compareMode: "value", value: 100 },
    ]),
    logic: "AND",
    timeframe: "1d",
    market: "US",
    cooldownMin: 15,
    intervalSec: 60,
    active: true,
    lastFiredAt: null,
    status: "idle",
    statusMsg: null,
    ...partial,
  };
}

function runtime() {
  return { timer: null, running: false, armed: new Map<string, boolean>(), removed: false };
}

describe("alertMonitor.evaluateOnce", () => {
  beforeEach(() => {
    state.rows.clear();
    state.updates = [];
    dispatchAlert.mockClear();
    fetchSnapshots.mockReset();
    fetchSnapshots.mockResolvedValue(new Map([["AAPL", { symbol: "AAPL", close: 150 }]]));
  });

  it("fires a true condition once, dispatches, and deactivates (one-shot)", async () => {
    state.rows.set("a1", row({ id: "a1" }));
    await evaluateOnce("a1");
    expect(dispatchAlert).toHaveBeenCalledTimes(1);
    expect(dispatchAlert.mock.calls[0][0]).toMatchObject({
      alertId: "a1",
      symbols: ["AAPL"],
    });
    // one-shot: the alert is deactivated and marked triggered
    const alert = state.rows.get("a1")!;
    expect(alert.active).toBe(false);
    expect(alert.status).toBe("triggered");
  });

  it("does not fire when the condition is false", async () => {
    state.rows.set("a2", row({
      id: "a2",
      conditions: JSON.stringify([{ indicator: "CLOSE", operator: ">", compareMode: "value", value: 200 }]),
    }));
    await evaluateOnce("a2");
    expect(dispatchAlert).not.toHaveBeenCalled();
    expect(state.rows.get("a2")!.status).toBe("watching");
  });

  it("honors the edge gate: false then true fires once", async () => {
    state.rows.set("a3", row({ id: "a3" }));
    const rt = runtime();
    // false first (CLOSE 150 > 200 is false)
    state.rows.set("a3", row({
      id: "a3",
      conditions: JSON.stringify([{ indicator: "CLOSE", operator: ">", compareMode: "value", value: 200 }]),
    }));
    await evaluateOnce("a3", rt as never);
    expect(dispatchAlert).not.toHaveBeenCalled();
    // true now
    state.rows.set("a3", row({ id: "a3" }));
    await evaluateOnce("a3", rt as never);
    expect(dispatchAlert).toHaveBeenCalledTimes(1);
  });

  it("reports an honest error when no snapshot data is available", async () => {
    fetchSnapshots.mockResolvedValue(new Map());
    state.rows.set("a4", row({ id: "a4" }));
    await evaluateOnce("a4");
    expect(dispatchAlert).not.toHaveBeenCalled();
    expect(state.rows.get("a4")!.status).toBe("error");
    expect(state.rows.get("a4")!.statusMsg).toContain("no snapshot");
  });
});
