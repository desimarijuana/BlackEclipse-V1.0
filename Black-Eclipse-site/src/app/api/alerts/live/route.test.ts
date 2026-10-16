import { describe, it, expect, vi, beforeEach } from "vitest";

// The live feed's notices must be derived from the durable events (not an
// in-process ring) and gated by the Settings "in-app" toggle.

const findEvents = vi.fn(async (..._a: unknown[]) => [
  { id: "e1", alertId: "a1", symbol: "AAPL", detail: "AAPL — CLOSE > 100", firedAt: new Date("2026-10-15T00:00:00Z") },
]);
const getAlertChannels = vi.fn(async (..._a: unknown[]) => ({ inApp: true, channels: {} }));

vi.mock("@/lib/db", () => ({
  prisma: {
    priceAlert: { findMany: vi.fn(async () => []) },
    priceAlertEvent: { findMany: (...a: unknown[]) => findEvents(...a) },
  },
}));
vi.mock("@/lib/alerts/notifier", () => ({ getAlertChannels: (...a: unknown[]) => getAlertChannels(...a) }));

import { GET } from "@/app/api/alerts/live/route";

describe("GET /api/alerts/live", () => {
  beforeEach(() => {
    getAlertChannels.mockReset();
    getAlertChannels.mockResolvedValue({ inApp: true, channels: {} });
  });

  it("derives notices from the durable events", async () => {
    const res = await GET();
    const data = await res.json();
    expect(data.notices).toHaveLength(1);
    expect(data.notices[0]).toMatchObject({ msg: "AAPL — CLOSE > 100" });
    expect(data.events).toHaveLength(1);
  });

  it("returns no notices when the in-app toggle is off", async () => {
    getAlertChannels.mockResolvedValue({ inApp: false, channels: {} });
    const data = await (await GET()).json();
    expect(data.notices).toEqual([]);
    expect(data.events).toHaveLength(1); // history is unaffected
  });
});
