import { describe, expect, it } from "vitest";
import { mergeOfficialEvents, type CalendarEvent } from "./calendar";

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
});
