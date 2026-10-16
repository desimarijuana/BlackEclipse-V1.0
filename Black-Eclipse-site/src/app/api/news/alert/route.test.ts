import { describe, it, expect, vi, beforeEach } from "vitest";

// POST /api/news/alert — one-click watch from a news card. Operator-gated;
// validates the ticker; creates a CHANGE_PCT watch and starts its monitor.

const create = vi.fn();
const startWatch = vi.fn();
vi.mock("@/lib/db", () => ({
  prisma: {
    asset: { findFirst: vi.fn(async () => ({ marketId: "US" })) },
    priceAlert: { create: (...a: unknown[]) => create(...a) },
  },
}));
vi.mock("@/lib/alerts/alertMonitor", () => ({ startWatch: (...a: unknown[]) => startWatch(...a) }));

import { POST } from "@/app/api/news/alert/route";

function req(body: unknown, origin = "http://localhost:3000"): Request {
  return new Request("http://localhost:3000/api/news/alert", {
    method: "POST",
    headers: { "content-type": "application/json", ...(origin ? { origin } : {}) },
    body: JSON.stringify(body),
  });
}

describe("POST /api/news/alert", () => {
  beforeEach(() => {
    create.mockReset();
    startWatch.mockReset();
  });

  it("refuses a cross-origin create", async () => {
    const res = await POST(req({ ticker: "AAPL" }, "http://evil.example"));
    expect(res.status).toBe(403);
    expect(create).not.toHaveBeenCalled();
  });

  it("rejects a missing ticker", async () => {
    const res = await POST(req({}));
    expect(res.status).toBe(400);
    expect(create).not.toHaveBeenCalled();
  });

  it("creates a watch and starts its monitor", async () => {
    create.mockResolvedValueOnce({ id: "a1", name: "AAPL rally ≥ 2% (from news)" });
    const res = await POST(req({ ticker: "aapl", direction: "up", movePct: 2 }));
    expect(res.status).toBe(201);
    expect(startWatch).toHaveBeenCalledWith("a1");
    const data = create.mock.calls[0]![0] as { data: { symbols: string; market: string } };
    expect(data.data.symbols).toBe('["AAPL"]');
    expect(data.data.market).toBe("US");
  });
});
