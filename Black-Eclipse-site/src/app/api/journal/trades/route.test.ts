import { describe, it, expect, vi, beforeEach } from "vitest";

// Front-door contract for POST /api/journal/trades. It creates a persisted trade
// for the profile, so it must be operator-gated and map a failure honestly.

const createTrade = vi.fn();
const loadTrades = vi.fn(async (..._a: unknown[]) => [] as unknown[]);

vi.mock("@/lib/journal/data", () => ({
  getOrCreateProfile: vi.fn(async () => "profile_1"),
  createTrade: (...a: unknown[]) => createTrade(...a),
  loadTrades: (...a: unknown[]) => loadTrades(...a),
}));

import { GET, POST } from "@/app/api/journal/trades/route";

function req(body: unknown, origin = "http://localhost:3000"): Request {
  return new Request("http://localhost:3000/api/journal/trades", {
    method: "POST",
    headers: { "content-type": "application/json", ...(origin ? { origin } : {}) },
    body: JSON.stringify(body),
  });
}

function getReq(query = ""): Request {
  return new Request(`http://localhost:3000/api/journal/trades${query}`, { method: "GET" });
}

describe("GET /api/journal/trades", () => {
  const trades = [
    { id: "t1", symbol: "AAPL", status: "open" },
    { id: "t2", symbol: "MSFT", status: "closed" },
    { id: "t3", symbol: "AAPL", status: "closed" },
  ];

  beforeEach(() => {
    loadTrades.mockReset();
    loadTrades.mockResolvedValue(trades);
  });

  it("lists trades for the profile", async () => {
    const res = await GET(getReq());
    expect(res.status).toBe(200);
    expect((await res.json()).trades).toEqual(trades);
  });

  it("honours limit and the take alias", async () => {
    const limited = await (await GET(getReq("?limit=1"))).json();
    expect(limited.trades).toHaveLength(1);
    const taken = await (await GET(getReq("?take=2"))).json();
    expect(taken.trades).toHaveLength(2);
  });

  it("filters by status before applying the limit", async () => {
    const body = await (await GET(getReq("?status=open&limit=5"))).json();
    expect(body.trades).toHaveLength(1);
    expect(body.trades[0].id).toBe("t1");
    expect(body.total).toBe(3);
  });

  it("filters by symbol", async () => {
    const body = await (await GET(getReq("?symbol=AAPL"))).json();
    expect(body.trades.map((t: { id: string }) => t.id)).toEqual(["t1", "t3"]);
  });

  it("ignores a nonsensical limit instead of returning nothing", async () => {
    const body = await (await GET(getReq("?limit=0"))).json();
    expect(body.trades).toHaveLength(3);
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
