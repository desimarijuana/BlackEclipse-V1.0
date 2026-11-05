import { describe, it, expect, vi } from "vitest";

// The history endpoint unions the durable notification archive with the price
// engine's fire log, dedupes by producer id and returns newest-first.

const appRows = [
  { id: "n1", tab: "news", kind: "alert", title: "CPI surprise", body: "inflation hotter", at: new Date("2026-11-05T10:00:00Z"), read: false },
  { id: "e1", tab: "alerts", kind: "alert", title: "AAPL", body: "crossed 200", at: new Date("2026-11-05T09:00:00Z"), read: true },
  { id: "t1", tab: "tasks", kind: "task", title: "Research done", body: "finished", at: new Date("2026-11-05T08:00:00Z"), read: false },
];
const priceRows = [
  { id: "e1", alertId: "a1", symbol: "AAPL", detail: "crossed 200", firedAt: new Date("2026-11-05T09:00:00Z") },
  { id: "e2", alertId: "a1", symbol: "MSFT", detail: "crossed 400", firedAt: new Date("2026-11-04T09:00:00Z") },
];

const appFind = vi.fn(async (..._a: unknown[]) => appRows);
const priceFind = vi.fn(async (..._a: unknown[]) => priceRows);

vi.mock("@/lib/db", () => ({
  prisma: {
    appNotification: { findMany: (...a: unknown[]) => appFind(...a) },
    priceAlertEvent: { findMany: (...a: unknown[]) => priceFind(...a) },
  },
}));

import { GET } from "@/app/api/alerts/history/route";

describe("GET /api/alerts/history", () => {
  it("unions both sources, dedupes shared ids and sorts newest first", async () => {
    const res = await GET(new Request("http://localhost:3000/api/alerts/history?range=all&limit=100"));
    const data = await res.json();
    expect(res.status).toBe(200);
    expect(data.alerts.map((a: { id: string }) => a.id)).toEqual(["n1", "e1", "t1", "e2"]);
    // e1 exists in both tables and must appear once.
    expect(data.alerts.filter((a: { id: string }) => a.id === "e1")).toHaveLength(1);
    expect(data.total).toBe(4);
  });

  it("skips the price log when the scope is not price/alerts", async () => {
    priceFind.mockClear();
    appFind.mockClear();
    const res = await GET(new Request("http://localhost:3000/api/alerts/history?range=all&tab=news"));
    await res.json();
    expect(priceFind).not.toHaveBeenCalled();
    const where = appFind.mock.calls[0][0] as { where: Record<string, unknown> };
    expect(where.where.tab).toBe("news");
  });

  it("maps the kind and search filters into the archive query", async () => {
    appFind.mockClear();
    await GET(new Request("http://localhost:3000/api/alerts/history?range=all&kind=task&q=research"));
    const where = appFind.mock.calls[0][0] as { where: Record<string, unknown> };
    expect(where.where.kind).toBe("task");
    expect(where.where.OR).toEqual([
      { title: { contains: "research" } },
      { body: { contains: "research" } },
    ]);
  });
});
