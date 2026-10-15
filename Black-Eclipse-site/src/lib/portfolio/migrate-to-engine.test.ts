import { describe, expect, it, vi } from "vitest";
import {
  PORTFOLIO_FUND_MAP_KEY,
  PORTFOLIO_MIGRATION_FLAG,
  mapTransactionToPosition,
  migrateFundsToEngine,
} from "./migrate-to-engine";
import type { Fund, Transaction } from "./types";

function makeStorage(seed: Record<string, string> = {}) {
  const data = new Map(Object.entries(seed));
  return {
    getItem: (k: string) => (data.has(k) ? data.get(k)! : null),
    setItem: (k: string, v: string) => void data.set(k, v),
    _data: data,
  };
}

const tx = (over: Partial<Transaction> = {}): Transaction => ({
  id: "tx-1", type: "BUY", symbol: "aapl", quantity: 10, price: 100, fee: 1, date: "2024-01-01", ...over,
});

const fund = (id: string, transactions: Transaction[]): Fund => ({
  id, name: `Fund ${id}`, icon: "i", accent: "a", createdAt: "t", transactions,
});

describe("mapTransactionToPosition", () => {
  it("maps a BUY/SELL to the engine payload", () => {
    const out = mapTransactionToPosition(tx({ symbol: "nvda", quantity: 5, price: 2, fee: 0 }));
    expect(out).toMatchObject({ symbol: "NVDA", quantity: "5", price: "2", type: "BUY" });
  });
  it("skips cash-only transactions", () => {
    expect(mapTransactionToPosition(tx({ type: "DEPOSIT" }))).toBeNull();
    expect(mapTransactionToPosition(tx({ type: "WITHDRAWAL" }))).toBeNull();
    expect(mapTransactionToPosition(tx({ type: "DIVIDEND" }))).toBeNull();
  });
});

describe("migrateFundsToEngine", () => {
  it("creates a portfolio + positions and records the flag and map", async () => {
    const calls: string[] = [];
    const fetchImpl = vi.fn(async (path: string) => {
      calls.push(path);
      if (path.endsWith("/create")) {
        return new Response(JSON.stringify({ id: "pf_1" }), { status: 200 });
      }
      return new Response(JSON.stringify({ status: "SUCCESS" }), { status: 200 });
    }) as unknown as (p: string, i?: RequestInit) => Promise<Response>;
    const storage = makeStorage();

    const summary = await migrateFundsToEngine(
      [fund("fund-1", [tx(), tx({ id: "tx-2", type: "DIVIDEND" })])],
      { fetchImpl, storage },
    );

    expect(summary.migrated).toBe(true);
    expect(summary.funds).toBe(1);
    expect(summary.positions).toBe(1);       // the DIVIDEND is skipped
    expect(summary.skippedTransactions).toBe(1);
    expect(storage.getItem(PORTFOLIO_MIGRATION_FLAG)).toBe("1");
    expect(JSON.parse(storage.getItem(PORTFOLIO_FUND_MAP_KEY)!)).toEqual({ "fund-1": "pf_1" });
    expect(calls).toContain("/api/portfolio/create");
    expect(calls.some((c) => c.includes("/pf_1/position"))).toBe(true);
  });

  it("is idempotent — a second run is a no-op", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ id: "pf_1" }), { status: 200 })) as unknown as (
      p: string, i?: RequestInit
    ) => Promise<Response>;
    const storage = makeStorage({ [PORTFOLIO_MIGRATION_FLAG]: "1" });
    const summary = await migrateFundsToEngine([fund("fund-1", [tx()])], { fetchImpl, storage });
    expect(summary.migrated).toBe(false);
    expect((fetchImpl as unknown as { mock: { calls: unknown[] } }).mock.calls.length).toBe(0);
  });

  it("leaves the flag UNSET on failure so it retries, keeping the legacy store", async () => {
    const fetchImpl = vi.fn(async () => new Response("nope", { status: 500 })) as unknown as (
      p: string, i?: RequestInit
    ) => Promise<Response>;
    const storage = makeStorage();
    const summary = await migrateFundsToEngine([fund("fund-1", [tx()])], { fetchImpl, storage });
    expect(summary.migrated).toBe(false);
    expect(summary.errors.length).toBe(1);
    expect(storage.getItem(PORTFOLIO_MIGRATION_FLAG)).toBeNull();
  });
});
