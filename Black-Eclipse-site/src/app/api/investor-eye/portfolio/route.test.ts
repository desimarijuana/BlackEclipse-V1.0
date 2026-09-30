import { describe, it, expect, vi, beforeEach } from "vitest";

// Front-door contract for POST /api/investor-eye/portfolio. It refreshes and
// PERSISTS events via assembleState, so it must be operator-gated and must
// never invent exposure for a holding that supplied no country/sector.

const assembleState = vi.fn();

vi.mock("@/lib/investor-eye/state", () => ({
  assembleState: (...a: unknown[]) => assembleState(...a),
}));

import { POST } from "@/app/api/investor-eye/portfolio/route";

function req(body: unknown, origin = "http://localhost:3000"): Request {
  return new Request("http://localhost:3000/api/investor-eye/portfolio", {
    method: "POST",
    headers: { "content-type": "application/json", ...(origin ? { origin } : {}) },
    body: JSON.stringify(body),
  });
}

describe("POST /api/investor-eye/portfolio", () => {
  beforeEach(() => assembleState.mockReset());

  it("refuses a cross-origin request before assembling state", async () => {
    const res = await POST(req({ holdings: [] }, "http://evil.example"));
    expect(res.status).toBe(403);
    expect(assembleState).not.toHaveBeenCalled();
  });

  it("returns 400 for an unparseable body", async () => {
    const bad = new Request("http://localhost:3000/api/investor-eye/portfolio", {
      method: "POST",
      headers: { origin: "http://localhost:3000", "content-type": "application/json" },
      body: "{not json",
    });
    const res = await POST(bad);
    expect(res.status).toBe(400);
    expect((await res.json()).error).toBe("invalid_body");
  });

  it("computes exposure from the supplied holdings only", async () => {
    assembleState.mockResolvedValueOnce({
      events: [],
      windowHours: 168,
      status: { provenance: "ok" },
    });
    const res = await POST(req({ holdings: [{ symbol: "AAPL", weight: 0.5, country: "us" }] }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.exposure.total).toBeCloseTo(0.5);
    expect(body.disclaimer).toMatch(/not investment advice/i);
  });

  it("returns an honest UNAVAILABLE exposure when state assembly throws", async () => {
    assembleState.mockRejectedValueOnce(new Error("provider down"));
    const res = await POST(req({ holdings: [{ symbol: "AAPL", weight: 1 }] }));
    expect(res.status).toBe(200);
    expect((await res.json()).provenance).toBe("UNAVAILABLE");
  });
});
