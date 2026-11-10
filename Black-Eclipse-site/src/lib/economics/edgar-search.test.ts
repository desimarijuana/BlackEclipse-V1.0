import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("@/lib/fundamentals/providers/sec-edgar", () => ({
  SEC_USER_AGENT: "BlackEclipse/test (contact@example.test)",
}));

import {
  parseDisplayName,
  parseEdgarSearch,
  searchEdgarFilings,
  __resetEdgarSearchCache,
} from "./edgar-search";

const PAYLOAD = {
  hits: {
    total: { value: 2248, relation: "gte" },
    hits: [
      {
        _id: "0001683168-20-000837:radnet_8k-ex9901.htm",
        _source: {
          ciks: ["0000790526"],
          display_names: ["RadNet, Inc.  (RDNT)  (CIK 0000790526)"],
          form: "8-K",
          file_date: "2020-03-16",
          items: ["8.01", "9.01"],
          file_type: "EX-99.1",
        },
      },
      {
        _id: "bad-id-without-filename",
        _source: { ciks: ["0000000001"], form: "8-K", display_names: ["X (X) (CIK 0000000001)"] },
      },
    ],
  },
};

describe("parseDisplayName", () => {
  it("splits company, ticker and CIK", () => {
    expect(parseDisplayName("Apple Inc.  (AAPL)  (CIK 0000320193)")).toEqual({
      company: "Apple Inc.",
      ticker: "AAPL",
      cik: "0000320193",
    });
  });

  it("falls back to the raw display name", () => {
    expect(parseDisplayName("Some Trust")).toEqual({ company: "Some Trust", ticker: null, cik: null });
  });
});

describe("parseEdgarSearch", () => {
  it("normalizes hits and constructs the official document URL", () => {
    const { filings, total } = parseEdgarSearch(PAYLOAD);
    expect(total).toBe(2248);
    expect(filings).toHaveLength(1);
    expect(filings[0]).toMatchObject({
      company: "RadNet, Inc.",
      ticker: "RDNT",
      cik: "0000790526",
      form: "8-K",
      filed: "2020-03-16",
      accession: "0001683168-20-000837",
      url: "https://www.sec.gov/Archives/edgar/data/790526/000168316820000837/radnet_8k-ex9901.htm",
    });
    expect(filings[0].items).toEqual(["8.01", "9.01"]);
  });

  it("drops hits it cannot resolve to a document", () => {
    expect(parseEdgarSearch(PAYLOAD).filings.map((f) => f.id)).not.toContain("bad-id-without-filename");
  });

  it("returns empty on a malformed payload", () => {
    expect(parseEdgarSearch({})).toEqual({ filings: [], total: 0 });
  });
});

describe("searchEdgarFilings", () => {
  beforeEach(() => __resetEdgarSearchCache());

  it("sends the query, forms and date window, then caches", async () => {
    const get = vi.fn().mockResolvedValue({
      status: 200,
      text: JSON.stringify(PAYLOAD),
      headers: {},
      url: "x",
      contentType: "application/json",
      bytes: 10,
    });
    const first = await searchEdgarFilings(
      { query: "inflation", forms: "8-K,10-K", start: "2026-09-01", end: "2026-11-09", limit: 10 },
      { get: get as never, now: () => 1000 },
    );
    expect(first.filings).toHaveLength(1);
    expect(first.cached).toBe(false);
    const url = get.mock.calls[0][0].url as string;
    expect(url).toContain("q=inflation");
    expect(url).toContain("forms=8-K%2C10-K");
    expect(url).toContain("dateRange=custom");
    expect(url).toContain("startdt=2026-09-01");

    const second = await searchEdgarFilings(
      { query: "inflation", forms: "8-K,10-K", start: "2026-09-01", end: "2026-11-09", limit: 10 },
      { get: get as never, now: () => 2000 },
    );
    expect(second.cached).toBe(true);
    expect(get).toHaveBeenCalledTimes(1);
  });

  it("rejects short queries and bad dates before any network call", async () => {
    const get = vi.fn();
    await expect(searchEdgarFilings({ query: "a" }, { get: get as never })).rejects.toThrow(/at least 2/);
    await expect(
      searchEdgarFilings({ query: "inflation", start: "09/01/2026", end: "2026-11-09" }, { get: get as never }),
    ).rejects.toThrow(/YYYY-MM-DD/);
    expect(get).not.toHaveBeenCalled();
  });
});
