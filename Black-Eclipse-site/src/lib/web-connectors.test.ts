import { describe, expect, it, vi, beforeEach } from "vitest";

// The structured connectors (OpenAlex/Crossref/GDELT/Openverse/Commons) are
// keyless and reached through the shared SSRF transport. These tests stub the
// transport and pin the normalization + honest empty/failure behavior.

const safeGet = vi.fn();
const validateOutboundUrl = vi.fn();

vi.mock("@/lib/connectors/security", () => ({
  safeGet: (...a: unknown[]) => safeGet(...a),
  validateOutboundUrl: (...a: unknown[]) => validateOutboundUrl(...a),
  OutboundError: class OutboundError extends Error {
    code: string;
    constructor(code: string, message: string) {
      super(message);
      this.code = code;
    }
  },
}));

import {
  runConnectors, openAlexSearch, semanticScholarSearch, crossrefSearch,
  gdeltSearch, openverseSearch, commonsSearch,
} from "./web-connectors";

function jsonResponse(payload: unknown, status = 200) {
  return { status, bytes: JSON.stringify(payload).length, text: JSON.stringify(payload), contentType: "application/json", headers: {} };
}

beforeEach(() => {
  safeGet.mockReset();
  validateOutboundUrl.mockReset();
  validateOutboundUrl.mockReturnValue({ safe: true });
});

describe("OpenAlex academic connector", () => {
  it("reconstructs abstract + DOI URL", async () => {
    safeGet.mockResolvedValue(
      jsonResponse({
        results: [
          {
            doi: "https://doi.org/10.1/abc",
            display_name: "A Study of Markets",
            publication_date: "2024-03-01",
            abstract_inverted_index: { Markets: [1], Study: [0] },
          },
        ],
      })
    );
    const outcome = await openAlexSearch("markets", 5);
    expect(outcome.results).toHaveLength(1);
    expect(outcome.results[0].url).toBe("https://doi.org/10.1/abc");
    expect(outcome.results[0].snippet).toContain("Study Markets");
    expect(outcome.results[0].publishedAt).toBe("2024-03-01");
  });

  it("returns zero_results honestly for an empty index", async () => {
    safeGet.mockResolvedValue(jsonResponse({ results: [] }));
    const outcome = await openAlexSearch("nothing", 5);
    expect(outcome.results).toEqual([]);
    expect(outcome.diagnostic.category).toBe("zero_results");
  });
});

describe("Semantic Scholar connector", () => {
  it("normalizes DOI, abstract and year", async () => {
    safeGet.mockResolvedValue(
      jsonResponse({
        data: [{
          title: "Volatility Forecasts",
          abstract: "A study of variance.",
          year: 2023,
          externalIds: { DOI: "10.3/vol" },
        }],
      })
    );
    const outcome = await semanticScholarSearch("volatility", 5);
    expect(outcome.results[0].url).toBe("https://doi.org/10.3/vol");
    expect(outcome.results[0].snippet).toContain("variance");
    expect(outcome.results[0].publishedAt).toBe("2023");
  });
});

describe("academic fan-out", () => {
  it("merges providers and deduplicates a DOI", async () => {
    safeGet
      .mockResolvedValueOnce(jsonResponse({ results: [
        { doi: "https://doi.org/10.4/same", display_name: "Same Paper" },
      ] }))
      .mockResolvedValueOnce(jsonResponse({ data: [
        { title: "Same Paper", externalIds: { DOI: "10.4/same" } },
        { title: "Second Paper", externalIds: { DOI: "10.4/second" } },
      ] }))
      .mockResolvedValueOnce(jsonResponse({ message: { items: [] } }));
    const result = await runConnectors("academic", "papers", 5);
    expect(result.results).toHaveLength(2);
    expect(result.provider).toContain("openalex");
    expect(result.provider).toContain("semantic-scholar");
  });
});

describe("Crossref connector", () => {
  it("normalizes DOI title/URL", async () => {
    safeGet.mockResolvedValue(
      jsonResponse({ message: { items: [{ DOI: "10.2/xyz", title: ["Another Work"], URL: "https://doi.org/10.2/xyz" }] } })
    );
    const outcome = await crossrefSearch("work", 5);
    expect(outcome.results[0].title).toBe("Another Work");
    expect(outcome.results[0].url).toBe("https://doi.org/10.2/xyz");
  });
});

describe("GDELT news connector", () => {
  it("normalizes article date and URL", async () => {
    safeGet.mockResolvedValue(
      jsonResponse({ articles: [{ url: "https://news.example/a", title: "Big News", seendate: "20260102T120000Z", domain: "news.example" }] })
    );
    const outcome = await gdeltSearch("news", 5);
    expect(outcome.results[0].url).toBe("https://news.example/a");
    expect(outcome.results[0].publishedAt).toBe("2026-01-02");
  });
});

describe("media connectors", () => {
  it("maps Openverse images", async () => {
    safeGet.mockResolvedValue(
      jsonResponse({ results: [{ title: "A cat", foreign_landing_url: "https://img.example/cat", creator: "Jane", license: "cc0" }] })
    );
    const outcome = await openverseSearch("cat", 5);
    expect(outcome.results[0].url).toBe("https://img.example/cat");
    expect(outcome.results[0].snippet).toContain("Jane");
  });

  it("maps Wikimedia Commons files", async () => {
    safeGet.mockResolvedValue(
      jsonResponse({ query: { search: [{ title: "File:Diagram.png" }] } })
    );
    const outcome = await commonsSearch("diagram", 5, "image");
    expect(outcome.results[0].url).toContain("File%3ADiagram.png");
  });
});

describe("runConnectors dispatch + failure honesty", () => {
  it("keeps the academic fan-out when one connector fails", async () => {
    safeGet
      .mockRejectedValueOnce(Object.assign(new Error("boom"), { name: "OutboundError", code: "transport_error" }))
      .mockResolvedValueOnce(jsonResponse({ data: [] }))
      .mockResolvedValueOnce(jsonResponse({ message: { items: [{ DOI: "10.3/z", title: ["Fallback"], URL: "https://doi.org/10.3/z" }] } }));
    const outcome = await runConnectors("academic", "q", 5);
    expect(outcome.provider).toContain("crossref");
    expect(outcome.results).toHaveLength(1);
    expect(outcome.diagnostics.some((d) => d.normalizedStatus === "failed")).toBe(true);
  });

  it("reports an all-failed chain without fabricating results", async () => {
    safeGet.mockResolvedValue(jsonResponse({}, 503));
    const outcome = await runConnectors("academic", "q", 5);
    expect(outcome.results).toEqual([]);
    expect(outcome.provider).toBeNull();
    expect(outcome.diagnostics.every((d) => d.normalizedStatus === "failed")).toBe(true);
  });

  it("rejects an unsafe URL without fetching", async () => {
    validateOutboundUrl.mockReturnValue({ safe: false, reason: "blocked" });
    const outcome = await runConnectors("academic", "q", 5);
    expect(safeGet).not.toHaveBeenCalled();
    expect(outcome.diagnostics.every((d) => d.category === "blocked")).toBe(true);
  });
});
