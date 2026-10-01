import { describe, it, expect, vi, beforeEach } from "vitest";

// Harness closeout Phase 2.5 — the bounded cross-market probe. One attempt per
// (market × implemented capability), recorded into the SAME ledger under the
// SAME canonical key. A fixture probe is labelled and never presented as live.

const upsert = vi.fn();
const fetchYahooBatchRaw = vi.fn();

vi.mock("@/lib/db", () => ({
  prisma: { sourceHealth: { upsert: (...a: unknown[]) => upsert(...a) } },
}));
vi.mock("@/lib/scraper/fetchers/yfinance", () => ({
  fetchYahooBatchRaw: (...a: unknown[]) => fetchYahooBatchRaw(...a),
}));

import { runRouteHealthProbe, scheduledProbeEnabled } from "./route-probe";

beforeEach(() => {
  vi.clearAllMocks();
  upsert.mockResolvedValue({});
  fetchYahooBatchRaw.mockResolvedValue({ quotes: { AAPL: { price: 100 } }, history: {} });
});

describe("route-health probe", () => {
  it("records one attempt per (market × capability) under a canonical live key", async () => {
    const result = await runRouteHealthProbe({ markets: ["US"], kind: "live" });
    // US has 2 declared capabilities (live_quote, price_history).
    expect(result.probed).toBe(2);
    expect(result.markets).toEqual(["US"]);
    const calls = upsert.mock.calls.map((c) => c[0]);
    expect(calls).toHaveLength(2);
    for (const c of calls) {
      expect(c.create.source).toBe("LIVE_STRUCTURED");
      expect(c.create.market).toBe("US");
      expect(
        c.create.symbol.includes("#live_quote") || c.create.symbol.includes("#price_history"),
      ).toBe(true);
    }
  });

  it("labels a fixture probe as fixture (never live)", async () => {
    const result = await runRouteHealthProbe({ markets: ["US"], kind: "fixture" });
    expect(result.kind).toBe("fixture");
    // A fixture probe performs NO network call.
    expect(fetchYahooBatchRaw).not.toHaveBeenCalled();
    const calls = upsert.mock.calls.map((c) => c[0]);
    expect(calls.every((c) => c.create.symbol.includes("!fixture"))).toBe(true);
  });

  it("records a real upstream miss as a failure, not a silent skip", async () => {
    fetchYahooBatchRaw.mockResolvedValue({ quotes: {}, history: {} });
    const result = await runRouteHealthProbe({ markets: ["US"], kind: "live" });
    expect(result.failed).toBe(2);
    const calls = upsert.mock.calls.map((c) => c[0]);
    expect(calls.every((c) => c.create.failCount === 1)).toBe(true);
  });

  it("never fabricates an attempt for a market with no declared sample", async () => {
    const result = await runRouteHealthProbe({ markets: ["NOPE"], kind: "live" });
    expect(result.probed).toBe(0);
    expect(result.skipped).toBe(1);
    expect(upsert).not.toHaveBeenCalled();
  });

  it("the recurring schedule is OFF unless the operator flag is set", () => {
    const original = process.env.HARNESS_ROUTE_PROBE_ENABLED;
    delete process.env.HARNESS_ROUTE_PROBE_ENABLED;
    expect(scheduledProbeEnabled()).toBe(false);
    process.env.HARNESS_ROUTE_PROBE_ENABLED = "1";
    expect(scheduledProbeEnabled()).toBe(true);
    if (original === undefined) delete process.env.HARNESS_ROUTE_PROBE_ENABLED;
    else process.env.HARNESS_ROUTE_PROBE_ENABLED = original;
  });
});
