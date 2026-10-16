import { describe, it, expect, vi, beforeEach } from "vitest";

// GET /api/alerts/:id is "recent events for ONE watch" — it must filter by the
// watch id, not return every watch's history.

const findMany = vi.fn(async (..._a: unknown[]) => [] as unknown[]);
vi.mock("@/lib/db", () => ({
  prisma: {
    priceAlert: {
      findUnique: vi.fn(async () => ({
        id: "a1", name: "x", symbols: '["AAPL"]', conditions: "[]", actions: "{}",
      })),
    },
    priceAlertEvent: { findMany: (...a: unknown[]) => findMany(...a) },
  },
}));
vi.mock("@/lib/alerts/alertMonitor", () => ({ startWatch: vi.fn(), stopWatch: vi.fn() }));
vi.mock("@/lib/alerts/notifier", () => ({ dispatchAlert: vi.fn(async () => ({ delivered: [], failed: [] })) }));

import { GET } from "@/app/api/alerts/[id]/route";

describe("GET /api/alerts/:id", () => {
  beforeEach(() => findMany.mockClear());

  it("filters events to the requested watch", async () => {
    const res = await GET(new Request("http://localhost:3000/api/alerts/a1"), {
      params: Promise.resolve({ id: "a1" }),
    });
    expect(res.status).toBe(200);
    expect(findMany).toHaveBeenCalledTimes(1);
    expect(findMany.mock.calls[0][0]).toMatchObject({ where: { alertId: "a1" } });
  });
});
