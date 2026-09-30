import { describe, it, expect, vi, beforeEach } from "vitest";

// Front-door contract for POST /api/alerts. It creates a persisted watch and
// starts a monitor, so it must be operator-gated and validate required fields.

const create = vi.fn();

vi.mock("@/lib/db", () => ({
  prisma: { priceAlert: { findMany: vi.fn(async () => []), create: (...a: unknown[]) => create(...a) } },
}));
vi.mock("@/lib/alerts/alertMonitor", () => ({
  startWatch: vi.fn(),
  runningWatchCount: vi.fn(() => 0),
}));

import { POST } from "@/app/api/alerts/route";

function req(body: unknown, origin = "http://localhost:3000"): Request {
  return new Request("http://localhost:3000/api/alerts", {
    method: "POST",
    headers: { "content-type": "application/json", ...(origin ? { origin } : {}) },
    body: JSON.stringify(body),
  });
}

describe("POST /api/alerts", () => {
  beforeEach(() => create.mockReset());

  it("refuses a cross-origin create before writing", async () => {
    const res = await POST(req({ name: "x", symbols: ["AAPL"], conditions: [] }, "http://evil.example"));
    expect(res.status).toBe(403);
    expect(create).not.toHaveBeenCalled();
  });

  it("returns 400 when required fields are missing", async () => {
    const res = await POST(req({ name: "x" }));
    expect(res.status).toBe(400);
    expect(create).not.toHaveBeenCalled();
  });

  it("creates a watch and returns 201", async () => {
    create.mockResolvedValueOnce({
      id: "a1", name: "x", symbols: '["AAPL"]', market: "US", universe: "CUSTOM",
      conditions: "[]", logic: "AND", timeframe: "1d", dataSource: "Auto", mode: "poll",
      intervalSec: 60, cooldownMin: 15, actions: "{}", active: true, status: "idle",
      statusMsg: null, lastEvalAt: null, lastFiredAt: null,
    });
    const res = await POST(req({ name: "x", symbols: ["AAPL"], conditions: [] }));
    expect(res.status).toBe(201);
    expect((await res.json()).alert.id).toBe("a1");
  });
});
