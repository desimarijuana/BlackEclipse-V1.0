import { describe, expect, it, vi, beforeEach } from "vitest";

const safeGet = vi.fn();
vi.mock("@/lib/connectors/security", () => ({
  safeGet: (...args: unknown[]) => safeGet(...args),
}));
vi.mock("@/lib/web-research", () => ({
  OUTBOUND_USER_AGENT: "BlackEclipse/test",
}));

import { fetchBlsSchedules, __resetBlsCache } from "./bls";

const TABLE = (date: string) => `
<table class="release-list"><thead><tr><th>Reference Month</th><th>Release Date</th><th>Release Time</th></tr></thead>
<tbody><tr><td>October 2026</td><td>${date}</td><td>08:30 AM</td></tr></tbody></table>`;

function ok(text: string) {
  return { status: 200, text, headers: {}, url: "x", contentType: "text/html", bytes: text.length };
}

describe("fetchBlsSchedules", () => {
  beforeEach(() => {
    safeGet.mockReset();
    __resetBlsCache();
  });

  it("keeps the releases whose pages succeeded when others fail", async () => {
    safeGet.mockImplementation(async ({ url }: { url: string }) => {
      if (url.endsWith("/cpi.htm")) return ok(TABLE("Nov. 10, 2026"));
      if (url.endsWith("/ppi.htm")) return ok(TABLE("Nov. 14, 2026"));
      throw new Error("BLS blocked");
    });
    const events = await fetchBlsSchedules(() => 1000);
    expect(events.map((e) => e.date)).toEqual(["2026-11-10", "2026-11-14"]);
    expect(safeGet).toHaveBeenCalledTimes(8);
  });

  it("throws when every page fails", async () => {
    safeGet.mockImplementation(async () => {
      throw new Error("down");
    });
    await expect(fetchBlsSchedules(() => 1000)).rejects.toThrow(/every BLS/);
  });

  it("caches the successful fan-out", async () => {
    safeGet.mockImplementation(async ({ url }: { url: string }) => {
      if (url.endsWith("/cpi.htm")) return ok(TABLE("Nov. 10, 2026"));
      throw new Error("blocked");
    });
    await fetchBlsSchedules(() => 1000);
    const calls = safeGet.mock.calls.length;
    await fetchBlsSchedules(() => 2000);
    expect(safeGet.mock.calls.length).toBe(calls);
  });
});
