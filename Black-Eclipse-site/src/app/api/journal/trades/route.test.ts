import { describe, it, expect, vi, beforeEach } from "vitest";

// Front-door contract for POST /api/journal/trades. It creates a persisted trade
// for the profile, so it must be operator-gated and map a failure honestly.

const createTrade = vi.fn();

vi.mock("@/lib/journal/data", () => ({
  getOrCreateProfile: vi.fn(async () => "profile_1"),
  createTrade: (...a: unknown[]) => createTrade(...a),
  loadTrades: vi.fn(async () => []),
}));

import { GET, POST } from "@/app/api/journal/trades/route";

function req(body: unknown, origin = "http://localhost:3000"): Request {
  return new Request("http://localhost:3000/api/journal/trades", {
    method: "POST",
    headers: { "content-type": "application/json", ...(origin ? { origin } : {}) },
    body: JSON.stringify(body),
  });
}

describe("GET /api/journal/trades", () => {
  it("lists trades for the profile", async () => {
    const res = await GET();
    expect(res.status).toBe(200);
    expect((await res.json()).trades).toEqual([]);
  });
});

describe("POST /api/journal/trades", () => {
  beforeEach(() => createTrade.mockReset());

  it("refuses a cross-origin create before writing", async () => {
    const res = await POST(req({ symbol: "AAPL" }, "http://evil.example"));
    expect(res.status).toBe(403);
    expect(createTrade).not.toHaveBeenCalled();
  });

  it("creates a trade for an operator", async () => {
    createTrade.mockResolvedValueOnce({ id: "t1", symbol: "AAPL" });
    const res = await POST(req({ symbol: "AAPL" }));
    expect(res.status).toBe(200);
    expect((await res.json()).trade.id).toBe("t1");
  });

  it("maps a data-layer failure to 500, never a fabricated success", async () => {
    createTrade.mockRejectedValueOnce(new Error("db down"));
    const res = await POST(req({ symbol: "AAPL" }));
    expect(res.status).toBe(500);
    expect((await res.json()).success).toBeUndefined();
  });
});
