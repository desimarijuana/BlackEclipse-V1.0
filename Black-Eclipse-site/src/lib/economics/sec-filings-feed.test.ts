import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("@/lib/fundamentals/providers/sec-edgar", () => ({
  SEC_USER_AGENT: "BlackEclipse/test (contact@example.test)",
}));

import {
  isPlausibleForm,
  parseEdgarFeed,
  fetchLatestFilings,
  __resetFilingsFeedCache,
} from "./sec-filings-feed";

const XML = `<?xml version="1.0" encoding="ISO-8859-1" ?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Latest Filings</title>
  <entry>
    <title>8-K - Ribbon Acquisition Corp. (0002035016) (Filer)</title>
    <link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/2035016/000121390026117482/0001213900-26-117482-index.htm"/>
    <summary type="html">
 &lt;b&gt;Filed:&lt;/b&gt; 2026-11-09 &lt;b&gt;AccNo:&lt;/b&gt; 0001213900-26-117482 &lt;b&gt;Size:&lt;/b&gt; 260 KB
&lt;br&gt;Item 8.01: Other Events
&lt;br&gt;Item 9.01: Financial Statements and Exhibits
    </summary>
    <updated>2026-11-09T14:57:19-05:00</updated>
    <category scheme="https://www.sec.gov/" label="form type" term="8-K"/>
    <id>urn:tag:sec.gov,2008:accession-number=0001213900-26-117482</id>
  </entry>
  <entry>
    <title>10-Q - Apple Inc. (0000320193) (Filer)</title>
    <link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/320193/000032019326000001/aapl-20260927-index.htm"/>
    <summary type="html">
 &lt;b&gt;Filed:&lt;/b&gt; 2026-11-08 &lt;b&gt;AccNo:&lt;/b&gt; 0000320193-26-000001 &lt;b&gt;Size:&lt;/b&gt; 2 MB
    </summary>
    <updated>2026-11-08T16:30:00-05:00</updated>
    <category scheme="https://www.sec.gov/" label="form type" term="10-Q"/>
    <id>urn:tag:sec.gov,2008:accession-number=0000320193-26-000001</id>
  </entry>
</feed>`;

describe("parseEdgarFeed", () => {
  it("extracts company, CIK, form, filed date, items and index URL", () => {
    const filings = parseEdgarFeed(XML);
    expect(filings).toHaveLength(2);
    expect(filings[0]).toMatchObject({
      company: "Ribbon Acquisition Corp.",
      cik: "0002035016",
      form: "8-K",
      filed: "2026-11-09",
      accession: "0001213900-26-117482",
      url: "https://www.sec.gov/Archives/edgar/data/2035016/000121390026117482/0001213900-26-117482-index.htm",
    });
    expect(filings[0].items).toEqual([
      "Other Events",
      "Financial Statements and Exhibits",
    ]);
    expect(filings[1]).toMatchObject({ company: "Apple Inc.", form: "10-Q", filed: "2026-11-08" });
  });

  it("drops entries without a link or form", () => {
    const filings = parseEdgarFeed(`<feed><entry><title>x</title></entry></feed>`);
    expect(filings).toEqual([]);
  });
});

describe("isPlausibleForm", () => {
  it("accepts SEC form spellings", () => {
    expect(isPlausibleForm("8-K")).toBe(true);
    expect(isPlausibleForm("SC 13G/A")).toBe(true);
    expect(isPlausibleForm("4")).toBe(true);
  });

  it("rejects injection-shaped values", () => {
    expect(isPlausibleForm("<script>")).toBe(false);
    expect(isPlausibleForm("8-K&count=999")).toBe(false);
  });
});

describe("fetchLatestFilings", () => {
  beforeEach(() => __resetFilingsFeedCache());

  it("requests the form-filtered EDGAR feed and caches the answer", async () => {
    const get = vi.fn().mockResolvedValue({ status: 200, text: XML, headers: {}, url: "x", contentType: "application/atom+xml", bytes: XML.length });
    const first = await fetchLatestFilings({ form: "8-K", limit: 2 }, { get: get as never, now: () => 1000 });
    expect(first.filings).toHaveLength(2);
    expect(first.cached).toBe(false);
    expect(get.mock.calls[0][0].url).toContain("type=8-K");
    expect(get.mock.calls[0][0].url).toContain("count=2");

    const second = await fetchLatestFilings({ form: "8-K", limit: 2 }, { get: get as never, now: () => 2000 });
    expect(second.cached).toBe(true);
    expect(get).toHaveBeenCalledTimes(1);
  });

  it("surfaces a provider failure instead of an empty success", async () => {
    const get = vi.fn().mockResolvedValue({ status: 503, text: "", headers: {}, url: "x", contentType: null, bytes: 0 });
    await expect(fetchLatestFilings({}, { get: get as never })).rejects.toThrow(/HTTP 503/);
  });
});
