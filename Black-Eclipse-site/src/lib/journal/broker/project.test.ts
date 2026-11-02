import { describe, it, expect } from "vitest";
import {
  mapSymbol,
  matchAttribution,
  normalizeEntry,
  projectBrokerTrades,
  type BrokerDeal,
  type BrokerOpenPosition,
} from "./project";

const T0 = Date.UTC(2026, 8, 1, 9, 30);
const HOUR = 3_600_000;

function deal(overrides: Partial<BrokerDeal> = {}): BrokerDeal {
  return {
    dealTicket: 1,
    orderTicket: 10,
    positionTicket: 100,
    symbol: "XAUUSD",
    side: "buy",
    entry: "in",
    volume: 1,
    price: 2650,
    commission: 0,
    swap: 0,
    profit: 0,
    magic: 0,
    comment: null,
    dealtAt: T0,
    ...overrides,
  };
}

describe("projectBrokerTrades", () => {
  it("projects a single closed long with broker costs", () => {
    const result = projectBrokerTrades(
      [
        deal({ dealTicket: 1, entry: "in", price: 2650, dealtAt: T0 }),
        deal({
          dealTicket: 2,
          entry: "out",
          side: "sell",
          price: 2662,
          commission: -2,
          swap: -1,
          profit: 120,
          dealtAt: T0 + 2 * HOUR,
        }),
      ],
      [],
      { connectionId: "conn-1" },
    );

    expect(result.warnings).toEqual([]);
    expect(result.trades).toHaveLength(1);
    const trade = result.trades[0];
    expect(trade.externalId).toBe("broker:conn-1:100");
    expect(trade.direction).toBe("LONG");
    expect(trade.entry).toBe(2650);
    expect(trade.exit).toBe(2662);
    expect(trade.quantity).toBe(1);
    expect(trade.status).toBe("closed");
    expect(trade.grossPnl).toBe(120);
    expect(trade.commission).toBe(2);
    expect(trade.fee).toBe(1);
    expect(trade.netPnl).toBe(117); // 120 - 2 - 1
    expect(trade.fillCount).toBe(2);
    expect(trade.exitTime).toBe(new Date(T0 + 2 * HOUR).toISOString());
  });

  it("averages scale-ins and a multi-fill exit", () => {
    const result = projectBrokerTrades(
      [
        deal({ dealTicket: 1, entry: "in", volume: 1, price: 100, dealtAt: T0 }),
        deal({ dealTicket: 2, entry: "in", volume: 1, price: 102, dealtAt: T0 + HOUR }),
        deal({
          dealTicket: 3,
          entry: "out",
          side: "sell",
          volume: 2,
          price: 110,
          profit: 18,
          commission: -4,
          dealtAt: T0 + 2 * HOUR,
        }),
      ],
      [],
      { connectionId: "c" },
    );

    const trade = result.trades[0];
    expect(trade.entry).toBe(101); // (100 + 102) / 2
    expect(trade.exit).toBe(110);
    expect(trade.quantity).toBe(2);
    expect(trade.status).toBe("closed");
    expect(trade.netPnl).toBe(14);
  });

  it("keeps a partially closed position open", () => {
    const result = projectBrokerTrades(
      [
        deal({ dealTicket: 1, entry: "in", volume: 2, price: 100, dealtAt: T0 }),
        deal({
          dealTicket: 2,
          entry: "out",
          side: "sell",
          volume: 1,
          price: 110,
          profit: 10,
          dealtAt: T0 + HOUR,
        }),
      ],
      [],
      { connectionId: "c" },
    );

    const trade = result.trades[0];
    expect(trade.status).toBe("open");
    expect(trade.exit).toBeNull();
    expect(trade.exitTime).toBeNull();
    expect(trade.quantity).toBe(2);
    expect(trade.netPnl).toBe(10); // realized half is still real
  });

  it("projects an open position with no deals in the window", () => {
    const position: BrokerOpenPosition = {
      ticket: 200,
      symbol: "EURUSD.a",
      side: "sell",
      volume: 0.5,
      openPrice: 1.1,
      currentPrice: 1.09,
      stopLoss: 1.105,
      takeProfit: 1.08,
      profit: 50,
      swap: -2,
      magic: 77,
      comment: "Breakout",
      openedAt: T0,
    };
    const result = projectBrokerTrades([], [position], {
      connectionId: "c",
      symbolMap: { "EURUSD.a": "EURUSD" },
    });

    expect(result.trades).toHaveLength(1);
    const trade = result.trades[0];
    expect(trade.symbol).toBe("EURUSD");
    expect(trade.direction).toBe("SHORT");
    expect(trade.entry).toBe(1.1);
    expect(trade.quantity).toBe(0.5);
    expect(trade.status).toBe("open");
    expect(trade.stopLoss).toBe(1.105);
    expect(trade.takeProfit).toBe(1.08);
    expect(trade.magic).toBe(77);
  });

  it("infers direction from a closing-only deal", () => {
    const result = projectBrokerTrades(
      [
        deal({
          dealTicket: 9,
          entry: "out",
          side: "buy",
          volume: 1,
          price: 95,
          profit: 5,
          dealtAt: T0,
        }),
      ],
      [],
      { connectionId: "c" },
    );
    expect(result.trades[0].direction).toBe("SHORT");
    expect(result.trades[0].status).toBe("closed");
  });

  it("is deterministic — the same deals project identically", () => {
    const deals = [
      deal({ dealTicket: 1, entry: "in", price: 100 }),
      deal({ dealTicket: 2, entry: "out", side: "sell", price: 105, profit: 5, dealtAt: T0 + HOUR }),
    ];
    const a = projectBrokerTrades(deals, [], { connectionId: "c" });
    const b = projectBrokerTrades(deals, [], { connectionId: "c" });
    expect(a).toEqual(b);
  });

  it("skips deals with no position ticket and reports why", () => {
    const result = projectBrokerTrades(
      [
        deal({ dealTicket: 1, positionTicket: null }),
        deal({ dealTicket: 2, positionTicket: 101, price: 0 }),
        deal({ dealTicket: 3, positionTicket: 102 }),
      ],
      [],
      { connectionId: "c" },
    );
    expect(result.skippedDeals).toBe(2);
    expect(result.warnings).toHaveLength(2);
    expect(result.trades).toHaveLength(1);
  });
});

describe("normalizeEntry", () => {
  it("normalizes MT5 entry tags", () => {
    expect(normalizeEntry("in")).toBe("in");
    expect(normalizeEntry("IN_OUT")).toBe("inout");
    expect(normalizeEntry("out by")).toBe("out_by");
    expect(normalizeEntry(null)).toBe("unknown");
  });
});

describe("mapSymbol", () => {
  it("maps exact and case-insensitive keys", () => {
    expect(mapSymbol("EURUSD.a", { "EURUSD.a": "EURUSD" })).toBe("EURUSD");
    expect(mapSymbol("eurusd.a", { "EURUSD.a": "EURUSD" })).toBe("EURUSD");
    expect(mapSymbol("XAUUSD", { "EURUSD.a": "EURUSD" })).toBe("XAUUSD");
  });
});

describe("matchAttribution", () => {
  const rules = [
    {
      id: "symbol",
      symbolMatch: "XAU*",
      tagNames: ["gold"],
      priority: 1,
    },
    {
      id: "magic",
      magic: 42,
      strategyId: "strat-1",
      setupId: "setup-1",
      tagNames: ["breakout"],
      priority: 5,
    },
    {
      id: "comment",
      commentMatch: "london",
      tagNames: ["london"],
      priority: 2,
    },
  ];

  it("picks the highest-priority match", () => {
    const rule = matchAttribution(
      { magic: 42, comment: "London breakout", symbol: "XAUUSD" },
      rules,
    );
    expect(rule?.id).toBe("magic");
    expect(rule?.strategyId).toBe("strat-1");
  });

  it("falls back to comment and symbol matches", () => {
    expect(
      matchAttribution({ magic: 0, comment: "London open", symbol: "EURUSD" }, rules)?.id,
    ).toBe("comment");
    expect(
      matchAttribution({ magic: 0, comment: null, symbol: "XAUUSD" }, rules)?.id,
    ).toBe("symbol");
  });

  it("returns null when nothing matches", () => {
    expect(matchAttribution({ magic: 0, comment: null, symbol: "BTCUSD" }, rules)).toBeNull();
  });
});
