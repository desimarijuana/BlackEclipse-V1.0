import { describe, it, expect, vi, beforeEach } from "vitest";

// Front-door contract for POST/DELETE /api/symbols. It persists a JDDS asset +
// price row, so it must be operator-gated, reject a missing symbol, and map a
// quote failure honestly (never a fabricated success).

const quote = vi.fn();
const assetUpsert = vi.fn();
const priceUpsert = vi.fn();
const assetDeleteMany = vi.fn();

vi.mock("@/lib/scraper/fetchers/yfinance", () => ({
  fetchYahooBatchQuote: (...a: unknown[]) => quote(...a),
}));
vi.mock("@/lib/db", () => ({
  prisma: {
    asset: { upsert: (...a: unknown[]) => assetUpsert(...a), deleteMany: (...a: unknown[]) => assetDeleteMany(...a) },
    price: { upsert: (...a: unknown[]) => priceUpsert(...a) },
  },
}));

import { POST, DELETE } from "@/app/api/symbols/route";

function req(body: unknown, origin = "http://localhost:3000"): Request {
  return new Request("http://localhost:3000/api/symbols", {
    method: "POST",
    headers: { "content-type": "application/json", ...(origin ? { origin } : {}) },
    body: JSON.stringify(body),
  });
}

describe("POST /api/symbols", () => {
  beforeEach(() => { quote.mockReset(); assetUpsert.mockReset(); priceUpsert.mockReset(); });

  it("refuses a cross-origin mutation before touching the database", async () => {
    const res = await POST(req({ symbol: "AAPL" }, "http://evil.example"));
    expect(res.status).toBe(403);
    expect(quote).not.toHaveBeenCalled();
  });

  it("returns 400 for a request with no symbol", async () => {
    const res = await POST(req({ symbols: [] }));
    expect(res.status).toBe(400);
    expect(quote).not.toHaveBeenCalled();
  });

  it("adds a resolved symbol and reports a failed one honestly", async () => {
    quote.mockResolvedValueOnce([
      { status: "ok", quote: { price: 195.2, changePct: 1.1, volume: 100 } },
      { status: "error" },
    ]);
    assetUpsert.mockResolvedValueOnce({ id: "a1", name: "AAPL" });
    priceUpsert.mockResolvedValueOnce({});
    const res = await POST(req({ symbols: ["AAPL", "NOPE"] }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.success).toBe(true);
    expect(body.added.map((a: { symbol: string }) => a.symbol)).toEqual(["AAPL"]);
    expect(body.failed).toEqual(["NOPE"]);
  });
});

describe("DELETE /api/symbols", () => {
  beforeEach(() => assetDeleteMany.mockReset());

  it("refuses a cross-origin delete", async () => {
    const res = await DELETE(req({ symbol: "AAPL" }, "http://evil.example"));
    expect(res.status).toBe(403);
    expect(assetDeleteMany).not.toHaveBeenCalled();
  });

  it("returns 400 when the symbol is missing", async () => {
    const res = await DELETE(req({ market: "US" }));
    expect(res.status).toBe(400);
  });

  it("removes a symbol and reports it", async () => {
    assetDeleteMany.mockResolvedValueOnce({ count: 1 });
    const res = await DELETE(req({ market: "US", symbol: "AAPL" }));
    expect(res.status).toBe(200);
    expect((await res.json()).removed).toBe("AAPL");
  });
});
