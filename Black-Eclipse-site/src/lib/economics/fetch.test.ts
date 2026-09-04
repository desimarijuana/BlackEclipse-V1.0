import { describe, it, expect } from "vitest";
import { normalizeEconomicSeries, sortByDate, computeStats, padYear, type EconPoint } from "./fetch";

describe("padYear", () => {
  it("zero-pads bare years so 999 sorts before 1999", () => {
    expect(padYear("999")).toBe("0999");
    expect(padYear("99")).toBe("0099");
    expect(padYear("2023")).toBe("2023");
  });

  it("pads the year part of partial dates", () => {
    expect(padYear("999-01")).toBe("0999-01");
  });
});

describe("normalizeEconomicSeries", () => {
  it("flattens date/value spellings", () => {
    const rows = normalizeEconomicSeries(
      [
        { TIME_PERIOD: "2023-01", OBS_VALUE: "42.5" },
        { date: "2023-02", value: 43.1 },
        { record_date: "2023-03", amount: 44 },
      ],
      "test"
    );
    expect(rows.map((r) => r.date)).toEqual(["2023-01", "2023-02", "2023-03"]);
    expect(rows.map((r) => r.value)).toEqual([42.5, 43.1, 44]);
  });

  it("handles year keys with zero-padding", () => {
    const rows = normalizeEconomicSeries(
      [{ Year: "999", Value: 5 }, { Year: "1999", Value: 6 }],
      "test"
    );
    expect(rows.map((r) => r.date)).toEqual(["0999", "1999"]);
    const sorted = sortByDate(rows);
    expect(sorted[0].value).toBe(5);
    expect(sorted[1].value).toBe(6);
  });

  it("returns null for gaps, never a silent 0", () => {
    const rows = normalizeEconomicSeries(
      [{ date: "2023-01", value: ".." }, { date: "2023-02", value: null }, { date: "2023-03", value: "1,234.5" }],
      "test"
    );
    expect(rows[0].value).toBeNull();
    expect(rows[1].value).toBeNull();
    expect(rows[2].value).toBe(1234.5);
  });

  it("unwraps provider wrappers (World Bank arrays, records keys)", () => {
    const wb = normalizeEconomicSeries(
      [["meta"], [{ country: "US", date: "2022", value: 100 }, { country: "US", date: "2021", value: 90 }]],
      "worldbank"
    );
    expect(wb.length).toBe(2);
    expect(wb[0].date).toBe("2022");

    const wrapped = normalizeEconomicSeries(
      { observations: [{ date: "2020-05", value: 3 }] },
      "ecb"
    );
    expect(wrapped).toEqual([{ date: "2020-05", value: 3 }]);
  });
});

describe("sortByDate", () => {
  it("sorts oldest-first regardless of input order", () => {
    const pts: EconPoint[] = [
      { date: "2023-03", value: 3 },
      { date: "2023-01", value: 1 },
      { date: "2022", value: 0 },
      { date: "2023-02", value: 2 },
    ];
    const sorted = sortByDate(pts);
    expect(sorted.map((p) => p.date)).toEqual(["2022", "2023-01", "2023-02", "2023-03"]);
  });
});

describe("computeStats", () => {
  it("computes latest/change/min/max/avg from chronological sort (newest-first input)", () => {
    // Newest-first input — stats must still be correct.
    const stats = computeStats([
      { date: "2023-05", value: 105 },
      { date: "2023-04", value: 100 },
      { date: "2023-03", value: 110 },
    ]);
    expect(stats.latest).toBe(105);
    expect(stats.change).toBeCloseTo(0.05); // (105-100)/|100|
    expect(stats.min).toBe(100);
    expect(stats.max).toBe(110);
    expect(stats.avg).toBeCloseTo(105);
    expect(stats.points).toBe(3);
    expect(stats.isTimeSeries).toBe(true);
    expect(stats.asOf).toBe("2023-05");
  });

  it("handles oldest-first input identically", () => {
    const stats = computeStats([
      { date: "2023-03", value: 110 },
      { date: "2023-04", value: 100 },
      { date: "2023-05", value: 105 },
    ]);
    expect(stats.latest).toBe(105);
    expect(stats.change).toBeCloseTo(0.05);
  });

  it("detects cross-sections (multiple rows, one date) and hides change", () => {
    const stats = computeStats([
      { date: "2023", value: 10, country: "US" },
      { date: "2023", value: 20, country: "DE" },
      { date: "2023", value: 30, country: "JP" },
    ]);
    expect(stats.isTimeSeries).toBe(false);
    expect(stats.change).toBeNull();
  });

  it("ignores null gaps in stats but counts them as points", () => {
    const stats = computeStats([
      { date: "2023-01", value: 10 },
      { date: "2023-02", value: null },
      { date: "2023-03", value: 20 },
    ]);
    expect(stats.points).toBe(3);
    expect(stats.min).toBe(10);
    expect(stats.max).toBe(20);
    expect(stats.latest).toBe(20);
    expect(stats.change).toBe(1); // (20-10)/10
  });
});