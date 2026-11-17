import { describe, expect, it } from "vitest";
import { authorizeBlockReason } from "./authorize";

const NOW = Date.parse("2026-11-17T12:00:00Z");
const armed = new Date(NOW + 600_000).toISOString();

describe("authorize gate", () => {
  it("never blocks shadow mode", () => {
    expect(
      authorizeBlockReason({ mode: "shadow", tier: "l0", connection: null, now: NOW }),
    ).toBeNull();
  });

  it("requires a connection for demo and live", () => {
    expect(authorizeBlockReason({ mode: "demo", tier: "l1", now: NOW })).toBe(
      "Choose the broker connection.",
    );
  });

  it("blocks an unavailable broker with its terminal reason", () => {
    const reason = authorizeBlockReason({
      mode: "demo",
      tier: "l1",
      now: NOW,
      connection: {
        label: "MT5 demo",
        status: "unavailable",
        statusReason: "the MetaTrader 5 terminal is not running",
      },
    });
    expect(reason).toContain("terminal is not running");
  });

  it("blocks live below L2", () => {
    expect(
      authorizeBlockReason({
        mode: "live",
        tier: "l1",
        now: NOW,
        connection: { status: "connected", armedUntil: armed },
      }),
    ).toBe("Live execution needs tier L2 first.");
  });

  it("blocks live when the connection is not armed or the arm expired", () => {
    expect(
      authorizeBlockReason({
        mode: "live",
        tier: "l2",
        now: NOW,
        connection: { status: "connected", armedUntil: null },
      }),
    ).toMatch(/Arm the live connection/);
    expect(
      authorizeBlockReason({
        mode: "live",
        tier: "l2",
        now: NOW,
        connection: {
          status: "connected",
          armedUntil: new Date(NOW - 60_000).toISOString(),
        },
      }),
    ).toMatch(/Arm the live connection/);
  });

  it("allows an available demo and an armed L2 live connection", () => {
    expect(
      authorizeBlockReason({
        mode: "demo",
        tier: "l1",
        now: NOW,
        connection: { status: "connected" },
      }),
    ).toBeNull();
    expect(
      authorizeBlockReason({
        mode: "live",
        tier: "l2",
        now: NOW,
        connection: { status: "connected", armedUntil: armed },
      }),
    ).toBeNull();
  });
});
