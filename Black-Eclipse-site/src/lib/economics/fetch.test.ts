import { describe, it, expect } from "vitest";

// A provider's HTML error page must never become an observation.
//
// REGRESSION (silent corruption): FRED's graph endpoint answered a site-wide
// maintenance page with HTTP 200. The source split the page into lines and
// emitted them as `{ date, value }` rows, so the normaliser produced
// observations out of an error document - `value: 400`,
// `dataTimestamp: "<link href=..."` - and stamped them `quality: valid`.
//
// The rule: an HTML body is a TRANSPORT FAILURE, and a row whose date does not
// look like a date is not an observation.

import { isHtmlPayload, looksLikeDate, normalizeEconomicSeries } from "./fetch";

const MAINTENANCE_PAGE = `<!DOCTYPE html>
<html><head><title>We'll be back soon!</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css?family=Open+Sans:300">
</head><body>
400, something
</body></html>`;

describe("isHtmlPayload", () => {
  it("recognises a maintenance page", () => {
    expect(isHtmlPayload(MAINTENANCE_PAGE)).toBe(true);
    expect(isHtmlPayload("<html><body>down</body></html>")).toBe(true);
    expect(isHtmlPayload("  <!DOCTYPE html><html></html>")).toBe(true);
  });

  it("does not claim a CSV", () => {
    expect(isHtmlPayload("observation_date,DFII10\n2026-09-01,2.74")).toBe(false);
    expect(isHtmlPayload("2026-09-01,2.74")).toBe(false);
  });
});

describe("looksLikeDate", () => {
  it("accepts the date shapes a provider sends", () => {
    expect(looksLikeDate("2026-09-01")).toBe(true);
    expect(looksLikeDate("2026-09")).toBe(true);
    expect(looksLikeDate("2026")).toBe(true);
    expect(looksLikeDate("2026-Q1")).toBe(true);
  });

  it("rejects the fragments of an error page", () => {
    expect(looksLikeDate("<link href=\"https://fonts.googleapis.com\"")).toBe(false);
    expect(looksLikeDate("</html>")).toBe(false);
    expect(looksLikeDate("400")).toBe(false);
  });
});

describe("normalizeEconomicSeries", () => {
  it("drops rows whose date is not a date", () => {
    const rows = normalizeEconomicSeries(
      [
        { date: "400", value: 2.74 },
        { date: "<link href=\"https://fonts.googleapis.com\"", value: 3.5 },
        { date: "2026-09-01", value: 2.74 },
      ],
      "fred-analytics",
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].date).toBe("2026-09-01");
    expect(rows[0].value).toBe(2.74);
  });

  it("keeps a real series intact", () => {
    const rows = normalizeEconomicSeries(
      [
        { date: "2026-08-01", value: 2.5 },
        { date: "2026-09-01", value: 2.74 },
      ],
      "fred-analytics",
    );
    expect(rows).toHaveLength(2);
  });
});
