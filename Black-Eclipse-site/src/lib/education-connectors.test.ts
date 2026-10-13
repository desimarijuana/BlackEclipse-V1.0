import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

// The education connectors are network adapters over the shared SSRF transport.
// These tests stub the transport and pin: honest not-configured behavior, the
// YouTube id → canonical URL mapping, duration enrichment, and the course
// allowlist enforcement.

const safeGet = vi.fn();
const validateOutboundUrl = vi.fn();
const searchWeb = vi.fn();

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

vi.mock("@/lib/web-research", () => ({
  searchWeb: (...a: unknown[]) => searchWeb(...a),
}));

import { parseIsoDuration, youtubeSearch, youtubeVideoMetadata, githubSearch, courseSearch } from "./education-connectors";

function jsonResponse(payload: unknown, status = 200) {
  return { status, bytes: JSON.stringify(payload).length, text: JSON.stringify(payload), contentType: "application/json", headers: {} };
}

beforeEach(() => {
  safeGet.mockReset();
  validateOutboundUrl.mockReset();
  validateOutboundUrl.mockReturnValue({ safe: true });
  searchWeb.mockReset();
  delete process.env.YOUTUBE_API_KEY;
});

afterEach(() => {
  delete process.env.YOUTUBE_API_KEY;
});

describe("parseIsoDuration", () => {
  it("parses ISO-8601 durations", () => {
    expect(parseIsoDuration("PT1H2M3S")).toBe(3723);
    expect(parseIsoDuration("PT45S")).toBe(45);
    expect(parseIsoDuration("P1DT1H")).toBe(90000);
    expect(parseIsoDuration("nonsense")).toBeNull();
    expect(parseIsoDuration(undefined)).toBeNull();
  });
});

describe("YouTube connector", () => {
  it("reports not_configured without a key (never scrapes)", async () => {
    const outcome = await youtubeSearch("quant trading", 5);
    expect(outcome.results).toEqual([]);
    expect(outcome.diagnostic.category).toBe("not_configured");
    expect(safeGet).not.toHaveBeenCalled();
  });

  it("maps search hits to canonical watch URLs and enriches duration", async () => {
    process.env.YOUTUBE_API_KEY = "test-key";
    safeGet
      .mockResolvedValueOnce(jsonResponse({
        items: [
          {
            id: { videoId: "abc123" },
            snippet: { title: "Quant Trading 101", description: "d", channelTitle: "Chan", channelId: "ch1", publishedAt: "2024-01-01T00:00:00Z", thumbnails: { medium: { url: "https://i.ytimg.com/abc.jpg" } } },
          },
        ],
      }))
      .mockResolvedValueOnce(jsonResponse({
        items: [{ id: "abc123", contentDetails: { duration: "PT1H30M" }, statistics: { viewCount: "12345" } }],
      }));
    const outcome = await youtubeSearch("quant trading", 5, { kind: "video" });
    expect(outcome.results).toHaveLength(1);
    expect(outcome.results[0].url).toBe("https://www.youtube.com/watch?v=abc123");
    expect(outcome.results[0].videoId).toBe("abc123");
    expect(outcome.results[0].durationSeconds).toBe(5400);
    expect(outcome.results[0].viewCount).toBe(12345);
  });

  it("metadata uses the videos endpoint and reports UNAVAILABLE for a missing id", async () => {
    process.env.YOUTUBE_API_KEY = "test-key";
    safeGet.mockResolvedValueOnce(jsonResponse({ items: [] }));
    const res = await youtubeVideoMetadata("nope");
    expect(res.ok).toBe(false);
  });
});

describe("GitHub connector", () => {
  it("normalizes repositories", async () => {
    safeGet.mockResolvedValueOnce(jsonResponse({
      items: [{ full_name: "example/backtrader", html_url: "https://github.com/example/backtrader", description: "backtesting", language: "Python", stargazers_count: 42, created_at: "2015-01-01" }],
    }));
    const outcome = await githubSearch("backtesting", 5);
    expect(outcome.results[0].url).toBe("https://github.com/example/backtrader");
    expect(outcome.results[0].snippet).toContain("42");
  });
});

describe("Course connector (allowlist enforcement)", () => {
  it("drops results not hosted on a known course provider", async () => {
    searchWeb.mockResolvedValue({
      results: [
        { title: "A course", url: "https://www.coursera.org/learn/x", snippet: "" },
        { title: "Spam", url: "https://random-blog.example/x", snippet: "" },
      ],
      diagnostics: [],
      provider: "duckduckgo-html",
    });
    const outcome = await courseSearch("python", 5);
    expect(outcome.results).toHaveLength(1);
    expect(outcome.results[0].url).toContain("coursera.org");
  });

  it("returns zero_results honestly when nothing is on the allowlist", async () => {
    searchWeb.mockResolvedValue({ results: [{ title: "x", url: "https://random.example/x", snippet: "" }], diagnostics: [], provider: "duckduckgo-html" });
    const outcome = await courseSearch("python", 5);
    expect(outcome.results).toEqual([]);
    expect(outcome.diagnostic.category).toBe("zero_results");
  });
});
