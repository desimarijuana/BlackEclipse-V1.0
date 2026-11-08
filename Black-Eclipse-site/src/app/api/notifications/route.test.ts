import { describe, it, expect, vi, beforeEach } from "vitest";

const upsert = vi.fn(async (..._a: unknown[]) => ({}));

vi.mock("@/lib/db", () => ({
  prisma: { appNotification: { upsert: (...a: unknown[]) => upsert(...a) } },
}));
vi.mock("@/lib/api-guard", () => ({
  checkMutationAllowed: () => ({ allowed: true }),
}));

import { POST } from "@/app/api/notifications/route";

function post(body: unknown): Request {
  return new Request("http://localhost:3000/api/notifications", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /api/notifications", () => {
  beforeEach(() => upsert.mockClear());

  it("upserts valid items by their producer id (idempotent)", async () => {
    const res = await POST(post({
      items: [
        { id: "news:1", tab: "news", kind: "alert", title: "CPI", body: "hot", at: 1700000000000 },
        { id: "task:1", tab: "tasks", kind: "task", title: "Done", body: "" },
      ],
    }));
    const data = await res.json();
    expect(data.saved).toBe(2);
    expect(upsert).toHaveBeenCalledTimes(2);
    expect(upsert.mock.calls[0][0]).toMatchObject({ where: { id: "news:1" }, update: {} });
  });

  it("skips malformed rows and unknown kinds default to alert", async () => {
    const res = await POST(post({
      items: [
        { id: "", title: "no id" },
        { id: "x", title: "ok", kind: "bogus" },
      ],
    }));
    const data = await res.json();
    expect(data.saved).toBe(1);
    expect(upsert.mock.calls[0][0]).toMatchObject({
      create: { id: "x", kind: "alert" },
    });
  });

  it("rejects unparseable JSON", async () => {
    const req = new Request("http://localhost:3000/api/notifications", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{not json",
    });
    const res = await POST(req);
    expect(res.status).toBe(400);
  });
});
