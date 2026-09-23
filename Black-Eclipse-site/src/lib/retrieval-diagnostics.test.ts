import { describe, it, expect } from "vitest";
import {
  failedDiagnostic,
  okDiagnostic,
  zeroResultDiagnostic,
  allFailed,
} from "./retrieval-diagnostics";
import { DuckDuckGoHtmlProvider, CustomJsonSearchProvider } from "./web-search";

describe("retrieval diagnostics", () => {
  it("marks a zero-result search as OK, distinct from a failure", () => {
    const d = zeroResultDiagnostic({ capability: "web_search", provider: "x", tier: "secondary" });
    expect(d.normalizedStatus).toBe("ok");
    expect(d.category).toBe("zero_results");
    expect(d.resultCount).toBe(0);
  });

  it("defaults retryability by category", () => {
    expect(failedDiagnostic({ capability: "web_fetch", provider: "x", tier: "unknown" }, "timeout", "t").retryable).toBe(true);
    expect(failedDiagnostic({ capability: "web_fetch", provider: "x", tier: "unknown" }, "blocked", "b").retryable).toBe(false);
    expect(
      failedDiagnostic({ capability: "web_search", provider: "x", tier: "secondary" }, "http_error", "5xx", { httpStatus: 503 }).retryable
    ).toBe(true);
    expect(
      failedDiagnostic({ capability: "web_search", provider: "x", tier: "secondary" }, "http_error", "4xx", { httpStatus: 404 }).retryable
    ).toBe(false);
  });

  it("allFailed is true only when every diagnostic failed", () => {
    const fail = failedDiagnostic({ capability: "web_search", provider: "x", tier: "secondary" }, "blocked", "b");
    const ok = okDiagnostic({ capability: "web_search", provider: "y", tier: "secondary" });
    expect(allFailed([fail])).toBe(true);
    expect(allFailed([fail, ok])).toBe(false);
    expect(allFailed([])).toBe(false);
  });
});

describe("DuckDuckGo provider diagnostics", () => {
  it("reports an invalid request for an empty query", async () => {
    const attempt = await new DuckDuckGoHtmlProvider().search("   ", 5);
    expect(attempt.results).toEqual([]);
    expect(attempt.diagnostic.category).toBe("invalid_request");
  });
});

describe("CustomJsonSearchProvider", () => {
  it("is unconfigured without a URL", async () => {
    const provider = new CustomJsonSearchProvider({
      url: "", apiKey: null, authKind: "query", authParam: "key",
      resultsPath: "results", titlePath: "title", urlPath: "url", snippetPath: "snippet",
    });
    expect(provider.configured()).toBe(false);
    const attempt = await provider.search("q", 5);
    expect(attempt.diagnostic.category).toBe("not_configured");
  });

  it("rejects a non-https / unsafe URL as blocked without fetching", async () => {
    const provider = new CustomJsonSearchProvider({
      url: "http://127.0.0.1/search?q={query}", apiKey: null, authKind: "query", authParam: "key",
      resultsPath: "results", titlePath: "title", urlPath: "url", snippetPath: "snippet",
    });
    const attempt = await provider.search("q", 5);
    expect(attempt.diagnostic.category).toBe("blocked");
    expect(attempt.diagnostic.retryable).toBe(false);
  });

  it("appends a query-auth key to the request URL", () => {
    const provider = new CustomJsonSearchProvider({
      url: "https://api.example.com/search?q={query}", apiKey: "sekret", authKind: "query", authParam: "api_key",
      resultsPath: "results", titlePath: "title", urlPath: "url", snippetPath: "snippet",
    });
    expect(provider.withQueryAuth("https://api.example.com/search?q=x")).toContain("api_key=sekret");
  });

  it("does not append a query key when auth is bearer", () => {
    const provider = new CustomJsonSearchProvider({
      url: "https://api.example.com/search?q={query}", apiKey: "sekret", authKind: "bearer", authParam: "key",
      resultsPath: "results", titlePath: "title", urlPath: "url", snippetPath: "snippet",
    });
    expect(provider.withQueryAuth("https://api.example.com/search?q=x")).not.toContain("sekret");
  });
});
