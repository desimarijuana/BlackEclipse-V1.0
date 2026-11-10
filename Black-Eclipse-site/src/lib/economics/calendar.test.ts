import { describe, expect, it } from "vitest";
import { filterUpcoming, mergeOfficialEvents, type CalendarEvent } from "./calendar";

function mirror(overrides: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    id: "mirror-fomc",
    date: "2026-01-27T19:00:00.000Z",
    country: "US",
    title: "FOMC Interest Rate Decision",
    importance: "high",
    actual: null,
    forecast: "4.25%",
    previous: "4.50%",
    confirmed: true,
    source: "mirror",
    url: null,
    ...overrides,
  };
}

function official(overrides: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    id: "fomc-2026-01-28",
    date: "2026-01-28",
    time: "14:00 ET",
    country: "US",
    title: "FOMC Interest Rate Decision",
    importance: "high",
    actual: null,
    forecast: null,
    previous: null,
    confirmed: true,
    source: "official",
    url: "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    ...overrides,
  };
}

describe("filterUpcoming", () => {
  const now = Date.parse("2026-11-09T12:00:00Z");
  const event = (date: string): CalendarEvent => ({
    id: date,
    date,
    country: "US",
    title: "Release",
    importance: "high",
    actual: null,
    forecast: null,
    previous: null,
  });

  it("drops past events beyond the overnight grace window", () => {
    const events = [event("2026-11-08T00:00:00Z"), event("2026-11-09T12:00:00Z")];
    const out = filterUpcoming(events, { now, days: 30 });
    expect(out.map((e) => e.date)).toEqual(["2026-11-09T12:00:00Z"]);
  });

  it("keeps a release from the last 12 hours", () => {
    const out = filterUpcoming([event("2026-11-09T02:00:00Z")], { now, days: 30 });
    expect(out).toHaveLength(1);
  });

  it("applies the horizon and sorts ascending", () => {
    const events = [
      event("2026-12-01T00:00:00Z"),
      event("2026-11-12T00:00:00Z"),
      event("2026-11-20T00:00:00Z"),
    ];
    const week = filterUpcoming(events, { now, days: 7 });
    expect(week.map((e) => e.date)).toEqual(["2026-11-12T00:00:00Z"]);
  });

  it("days=null removes the upper bound", () => {
    const events = [event("2027-06-01T00:00:00Z")];
    expect(filterUpcoming(events, { now, days: null })).toHaveLength(1);
  });

  it("past mode returns the lookback window newest-first", () => {
    const events = [
      event("2026-11-02T00:00:00Z"),
      event("2026-11-08T00:00:00Z"),
      event("2026-11-09T12:00:00Z"),
      event("2026-11-10T00:00:00Z"),
    ];
    const released = filterUpcoming(events, { now, days: 3, past: true });
    expect(released.map((e) => e.date)).toEqual([
      "2026-11-09T12:00:00Z",
      "2026-11-08T00:00:00Z",
    ]);
  });
});

describe("mergeOfficialEvents", () => {
  it("upgrades the date to the official one but keeps mirror values", () => {
    const [merged] = mergeOfficialEvents([mirror()], [official()]);
    expect(merged.date).toBe("2026-01-28");
    expect(merged.forecast).toBe("4.25%");
    expect(merged.previous).toBe("4.50%");
    expect(merged.source).toBe("official");
    expect(merged.time).toBe("14:00 ET");
  });

  it("adds an official event the mirror does not cover", () => {
    const merged = mergeOfficialEvents([], [official()]);
    expect(merged).toHaveLength(1);
    expect(merged[0].id).toBe("fomc-2026-01-28");
  });

  it("does not merge unrelated releases on nearby dates", () => {
    const merged = mergeOfficialEvents(
      [mirror({ title: "US CPI (YoY)", id: "cpi" })],
      [official()],
    );
    expect(merged).toHaveLength(2);
  });

  it("carries the tentative flag through", () => {
    const [merged] = mergeOfficialEvents([mirror()], [official({ confirmed: false })]);
    expect(merged.confirmed).toBe(false);
  });

  it("matches release families whose titles differ between providers", () => {
    const [merged] = mergeOfficialEvents(
      [mirror({ id: "cpi", title: "Consumer Price Index (CPI)", forecast: "3.1%" })],
      [official({ id: "official-cpi", title: "US Consumer Price Index (CPI)" })],
    );
    expect(merged.date).toBe("2026-01-28");
    expect(merged.forecast).toBe("3.1%");
    expect(merged.source).toBe("official");
  });
});
