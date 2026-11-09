import { describe, expect, it, vi } from "vitest";
import {
  extractMetricFromText,
  enrichMetricFromWeb,
  isOfficialEconHost,
  type WebMetricSpec,
} from "./enrichment";

const spec: WebMetricSpec = {
  query: "US CPI latest",
  pattern: /consumer price index[^.]{0,120}?(\d{1,2}\.\d)\s*(?:percent|%)/i,
  min: -5,
  max: 30,
};

describe("isOfficialEconHost", () => {
  it("accepts official statistical hosts and subdomains", () => {
    expect(isOfficialEconHost("https://www.bls.gov/news.release/cpi.htm")).toBe(true);
    expect(isOfficialEconHost("https://data.bls.gov/timeseries")).toBe(true);
    expect(isOfficialEconHost("https://www.federalreserve.gov/monetarypolicy.htm")).toBe(true);
  });

  it("rejects aggregators and lookalike hosts", () => {
    expect(isOfficialEconHost("https://tradingeconomics.com/united-states/inflation-cpi")).toBe(false);
    expect(isOfficialEconHost("https://notbls.gov.example.com/cpi")).toBe(false);
  });
});

describe("extractMetricFromText", () => {
  it("extracts a labelled, in-range value and its month/year", () => {
    const text =
      "The Consumer Price Index for All Urban Consumers rose 2.9 percent in September 2026, seasonally adjusted.";
    const result = extractMetricFromText(text, spec);
    expect(result?.value).toBe(2.9);
    expect(result?.asOf).toBe("2026-09");
  });

  it("rejects an out-of-range number instead of attaching it to the label", () => {
    const text = "The Consumer Price Index table shows 99.9 percent of respondents.";
    expect(extractMetricFromText(text, spec)).toBeNull();
  });

  it("rejects text without the label", () => {
    expect(extractMetricFromText("Inflation was 2.9 percent.", spec)).toBeNull();
  });
});

describe("enrichMetricFromWeb", () => {
  it("returns a result only from an official page", async () => {
    const search = vi.fn().mockResolvedValue({
      results: [
        { title: "CPI", url: "https://tradingeconomics.com/cpi", snippet: "" },
        { title: "CPI", url: "https://www.bls.gov/news.release/cpi.htm", snippet: "" },
      ],
      diagnostics: [],
      provider: "test",
    });
    const fetchPage = vi.fn().mockResolvedValue({
      page: { url: "https://www.bls.gov/news.release/cpi.htm", title: "CPI", text: "Consumer Price Index rose 2.9 percent in September 2026.", bytes: 10 },
      diagnostic: { capability: "web_fetch", provider: "test", tier: "unknown", category: "ok", message: "" },
    });
    const result = await enrichMetricFromWeb(spec, { search: search as never, fetchPage: fetchPage as never, now: () => 0 });
    expect(result).toMatchObject({
      value: 2.9,
      asOf: "2026-09",
      provider: "bls.gov",
    });
    expect(fetchPage).toHaveBeenCalledTimes(1);
    expect(fetchPage).toHaveBeenCalledWith("https://www.bls.gov/news.release/cpi.htm");
  });

  it("returns null when no official result exists", async () => {
    const search = vi.fn().mockResolvedValue({
      results: [{ title: "CPI", url: "https://example.com/cpi", snippet: "" }],
      diagnostics: [],
      provider: "test",
    });
    const fetchPage = vi.fn();
    const result = await enrichMetricFromWeb(spec, { search: search as never, fetchPage: fetchPage as never });
    expect(result).toBeNull();
    expect(fetchPage).not.toHaveBeenCalled();
  });
});
