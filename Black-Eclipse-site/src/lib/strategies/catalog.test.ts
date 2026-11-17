import { beforeEach, describe, expect, it, vi } from "vitest";

const { listStrategyCatalog } = vi.hoisted(() => ({ listStrategyCatalog: vi.fn() }));

vi.mock("@/lib/backtest/backtest-client", () => ({
  backtestClient: { listStrategyCatalog },
}));

import {
  __getStrategyCatalogState,
  __resetStrategyCatalog,
  __subscribeStrategyCatalog,
  invalidateStrategyCatalog,
  refreshStrategyCatalog,
  setCatalogArchiveScope,
  sortStrategies,
} from "./catalog";

function row(id: string, archived = false) {
  return {
    id,
    name: id,
    latestVersion: "1.0.0",
    archived,
    updatedAt: "2026-11-17T10:00:00Z",
    latestBacktest: { id: "exp_1", status: "completed", createdAt: "2026-11-17T09:00:00Z" },
    approval: null,
    lastPaperRun: null,
  };
}

beforeEach(() => {
  __resetStrategyCatalog();
  listStrategyCatalog.mockReset();
});

describe("strategy catalog", () => {
  it("loads the list with evidence and clears the loading state", async () => {
    listStrategyCatalog.mockResolvedValue([row("eurusd_m1_ema_rsi")]);
    await refreshStrategyCatalog();
    const state = __getStrategyCatalogState();
    expect(state.loading).toBe(false);
    expect(state.error).toBeNull();
    expect(state.items.map((item) => item.id)).toEqual(["eurusd_m1_ema_rsi"]);
    expect(state.items[0].latestBacktest?.status).toBe("completed");
    expect(state.updatedAt).toBeGreaterThan(0);
  });

  it("reports an error instead of pretending the list is empty", async () => {
    listStrategyCatalog.mockRejectedValue(new Error("runtime unavailable"));
    await refreshStrategyCatalog();
    const state = __getStrategyCatalogState();
    expect(state.loading).toBe(false);
    expect(state.error).toBe("runtime unavailable");
  });

  it("refetches with the archive scope the operator chose", async () => {
    listStrategyCatalog.mockResolvedValue([row("archived_one", true)]);
    await setCatalogArchiveScope(true);
    expect(listStrategyCatalog).toHaveBeenCalledWith(true);
    expect(__getStrategyCatalogState().includeArchived).toBe(true);
    expect(__getStrategyCatalogState().items[0].archived).toBe(true);
  });

  it("coalesces concurrent refreshes into one request", async () => {
    listStrategyCatalog.mockResolvedValue([row("a")]);
    await Promise.all([refreshStrategyCatalog(), refreshStrategyCatalog()]);
    expect(listStrategyCatalog).toHaveBeenCalledTimes(1);
  });

  it("does not fetch on invalidate when no surface is mounted", () => {
    invalidateStrategyCatalog();
    expect(listStrategyCatalog).not.toHaveBeenCalled();
    expect(__getStrategyCatalogState().updatedAt).toBe(0);
  });

  it("refreshes on invalidate when a surface is mounted (agent turn finished)", async () => {
    listStrategyCatalog.mockResolvedValue([row("fresh")]);
    const unsubscribe = __subscribeStrategyCatalog(() => undefined);
    // First subscribe kicks off the initial read.
    await Promise.resolve();
    await Promise.resolve();
    const callsAfterMount = listStrategyCatalog.mock.calls.length;
    invalidateStrategyCatalog();
    await Promise.resolve();
    await Promise.resolve();
    expect(listStrategyCatalog.mock.calls.length).toBeGreaterThan(callsAfterMount);
    unsubscribe();
  });
});

describe("catalog sorting", () => {
  const items = [
    { id: "zeta", name: "Zeta", latestVersion: "1", archived: false, updatedAt: "2026-03-01" },
    { id: "alpha", name: "Alpha", latestVersion: "1", archived: false, updatedAt: "2026-01-01" },
    { id: "beta", name: "beta", latestVersion: "1", archived: false, updatedAt: "2026-02-01" },
  ];

  it("sorts newest first by default", () => {
    expect(sortStrategies(items, "updated").map((item) => item.id)).toEqual([
      "zeta",
      "beta",
      "alpha",
    ]);
  });

  it("sorts by name case-insensitively", () => {
    expect(sortStrategies(items, "name").map((item) => item.id)).toEqual([
      "alpha",
      "beta",
      "zeta",
    ]);
  });
});
