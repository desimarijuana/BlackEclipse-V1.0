import { describe, it, expect, vi, beforeEach } from "vitest";

// GET /api/news/alerts — top market-moving stories + upcoming releases.
// Ranking is delegated to the pure scorer (covered separately); this test
// guards the route's filtering, response shape and honesty rules.

const findMany = vi.fn();
vi.mock("@/lib/db", () => ({
  prisma: {
    newsItem: { findMany: (...a: unknown[]) => findMany(...a) },
    cronJob: { findUnique: vi.fn(async () => ({ lastRunAt: new Date() })) },
  },
}));

vi.mock("@/lib/economics/calendar", () => ({
  fetchEconomicCalendar: vi.fn(async () => ({
    source: "fincept",
    events: [
      {
        id: "e1",
        date: new Date(Date.now() + 30 * 60_000).toISOString(),
        country: "US",
        title: "Consumer Price Index (CPI)",
        importance: "high",
        actual: null,
        forecast: "3.1%",
        previous: "3.2%",
      },
    ],
  })),
}));

function row(overrides: Record<string, unknown>) {
  return {
    id: "n1",
    source: "Reuters",
    ticker: null,
    headline: "Fed cuts rates by 50 basis points",
    summary: "",
    sentiment: "bullish",
    timestamp: new Date(Date.now() - 2 * 60_000),
    url: "https://example.com/a",
    category: "CENTRAL BANKS",
    region: "US",
    tier: 1,
    dedupKey: "k1",
    ...overrides,
  };
}

describe("GET /api/news/alerts", () => {
  beforeEach(() => {
    findMany.mockReset();
    // The route caches the calendar at module scope; a fresh module graph per
    // test keeps the two calendar assertions independent.
    vi.resetModules();
  });

  it("returns only high/critical stories and upcoming high-impact events", async () => {
    const { GET } = await import("@/app/api/news/alerts/route");
    findMany.mockResolvedValueOnce([
      row({}),
      row({
        id: "n2",
        headline: "Why 3 stocks could rally next year",
        source: "Blog",
        category: "TECH",
        tier: 4,
        sentiment: "bullish",
        timestamp: new Date(Date.now() - 3 * 60 * 60_000),
      }),
    ]);

    const res = await GET(new Request("http://localhost:3000/api/news/alerts?limit=5&minScore=55"));
    const data = await res.json();

    expect(res.status).toBe(200);
    expect(data.source).toBe("jdds");
    expect(data.alerts).toHaveLength(1);
    expect(data.alerts[0].id).toBe("n1");
    expect(data.alerts[0].alertLevel).toBe("critical");
    expect(data.alerts[0].importanceReasons.length).toBeGreaterThan(0);
    expect(data.upcoming).toHaveLength(1);
    expect(data.upcoming[0].title).toContain("CPI");
    expect(data.calendarSource).toBe("fincept");
  });

  it("does not present the placeholder fallback schedule as confirmed releases", async () => {
    const calendar = await import("@/lib/economics/calendar");
    vi.mocked(calendar.fetchEconomicCalendar).mockResolvedValueOnce({
      source: "schedule-fallback",
      events: [
        {
          id: "fb-cpi",
          date: new Date(Date.now() + 60 * 60_000).toISOString(),
          country: "US",
          title: "Consumer Price Index (CPI)",
          importance: "high",
          actual: null,
          forecast: null,
          previous: null,
        },
      ],
    });
    findMany.mockResolvedValueOnce([row({})]);

    const { GET } = await import("@/app/api/news/alerts/route");
    const res = await GET(new Request("http://localhost:3000/api/news/alerts"));
    const data = await res.json();

    expect(res.status).toBe(200);
    expect(data.calendarSource).toBe("schedule-fallback");
    expect(data.upcoming).toEqual([]);
  });
});
