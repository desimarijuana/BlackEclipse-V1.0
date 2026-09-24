import { describe, it, expect, vi } from "vitest";
import { fetchWebPageDetailed, extractPdfText } from "./web-research";
import { OutboundError, type SafeGetResult } from "./connectors/security";
import { failedDiagnostic } from "./retrieval-diagnostics";

// Deterministic offline document fixtures (WS5). No network is contacted: the
// transport is injected. Each fixture exercises one document-handling branch so
// the categories stay mutually distinct.

function okResult(over: Partial<SafeGetResult>): SafeGetResult {
  return {
    status: 200,
    contentType: "text/html",
    text: "",
    bytes: 10,
    url: "https://example.test/x",
    ...over,
  };
}

function fetcher(result?: SafeGetResult | (() => Promise<SafeGetResult>)) {
  return {
    get: vi.fn(async () =>
      typeof result === "function" ? await result() : (result as SafeGetResult)
    ),
  };
}

describe("document acquisition & extraction (WS5 fixtures)", () => {
  it("reads a text PDF and reports extraction=pdf", async () => {
    const pdf =
      "%PDF-1.4\n1 0 obj\n<<>>\nstream\n(Consolidated revenue from operations 83,855 crore) Tj\nendstream\nendobj\n%%EOF";
    const outcome = await fetchWebPageDetailed("https://example.test/report.pdf", {
      ...fetcher(okResult({ contentType: "application/pdf", text: pdf })),
    });
    expect(outcome.page?.extraction).toBe("pdf");
    expect(outcome.page?.text).toContain("83,855 crore");
  });

  it("reports a scanned/image PDF as unsupported_document (no OCR)", async () => {
    const scanned = "%PDF-1.4\n1 0 obj\n<< /Subtype /Image >>\nstream\nBINARYDATA\nendstream\nendobj\n%%EOF";
    const outcome = await fetchWebPageDetailed("https://example.test/scan.pdf", {
      ...fetcher(okResult({ contentType: "application/pdf", text: scanned })),
    });
    expect(outcome.page).toBeNull();
    expect(outcome.diagnostic.category).toBe("unsupported_document");
  });

  it("reads a JSON/XBRL filing and preserves a document id", async () => {
    const json = JSON.stringify({ cik: 1, facts: { Revenue: { val: 130497000000 } } });
    const outcome = await fetchWebPageDetailed(
      "https://data.sec.gov/api/xbrl/companyconcept/CIK0001045810/0001193125-25-123456.json",
      { ...fetcher(okResult({ contentType: "application/json", text: json })) }
    );
    expect(outcome.page?.extraction).toBe("json");
    expect(outcome.page?.documentId).toBe("0001193125-25-123456");
    expect(outcome.page?.retrievedAt).toBeTruthy();
  });

  it("rejects a value-less XBRL taxonomy as parse_failure, not evidence", async () => {
    const xbrl = `<?xml version="1.0"?><xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"><context id="c1"/></xbrli:xbrl>`;
    const outcome = await fetchWebPageDetailed("https://example.test/taxonomy.xml", {
      ...fetcher(okResult({ contentType: "application/xml", text: xbrl })),
    });
    expect(outcome.page).toBeNull();
    expect(outcome.diagnostic.category).toBe("parse_failure");
  });

  it("reports a JavaScript-only shell as javascript_only", async () => {
    const shell = `<html><head><title>App</title></head><body><div id="root"></div><script src="/app.js"></script>`;
    const outcome = await fetchWebPageDetailed("https://example.test/app", {
      ...fetcher(okResult({ contentType: "text/html", text: shell })),
    });
    expect(outcome.page).toBeNull();
    expect(outcome.diagnostic.category).toBe("javascript_only");
  });

  it("reports an empty body as empty_response (distinct from parse failure)", async () => {
    const outcome = await fetchWebPageDetailed("https://example.test/empty.json", {
      ...fetcher(okResult({ contentType: "application/json", text: "   " })),
    });
    expect(outcome.page).toBeNull();
    expect(outcome.diagnostic.category).toBe("empty_response");
  });

  it("distinguishes a 403 blocked response from a 404", async () => {
    const forbidden = await fetchWebPageDetailed("https://example.test/a", {
      ...fetcher(okResult({ status: 403, text: "" })),
    });
    expect(forbidden.page).toBeNull();
    expect(forbidden.diagnostic.category).toBe("http_error");
    expect(forbidden.diagnostic.httpStatus).toBe(403);

    const missing = await fetchWebPageDetailed("https://example.test/b", {
      ...fetcher(okResult({ status: 404, text: "" })),
    });
    expect(missing.diagnostic.category).toBe("http_error");
    expect(missing.diagnostic.httpStatus).toBe(404);
  });

  it("reports an oversized document as too_large, not a parse failure", async () => {
    const outcome = await fetchWebPageDetailed("https://example.test/huge.pdf", {
      ...fetcher(async () => {
        throw new OutboundError("too_large", "Response exceeded 16777216 bytes");
      }),
    });
    expect(outcome.page).toBeNull();
    expect(outcome.diagnostic.category).toBe("too_large");
  });

  it("blocks an unsafe URL before any transport call", async () => {
    const spy = fetcher(okResult({}));
    const outcome = await fetchWebPageDetailed("http://127.0.0.1/secret", spy);
    expect(outcome.page).toBeNull();
    expect(outcome.diagnostic.category).toBe("blocked");
    expect(spy.get).not.toHaveBeenCalled();
  });

  it("preserves HTML title + publication date for citations", async () => {
    const html = `<html lang="en"><head><title>Systems Limited Annual Report</title><meta property="article:published_time" content="2026-04-07T09:37:00Z"/></head><body><h1>Revenue 44,230,607,495</h1></body></html>`;
    const outcome = await fetchWebPageDetailed("https://example.test/ar", {
      ...fetcher(okResult({ contentType: "text/html", text: html })),
    });
    expect(outcome.page?.title).toBe("Systems Limited Annual Report");
    expect(outcome.page?.publishedAt).toBe("2026-04-07T09:37:00Z");
    expect(outcome.page?.language).toBe("en");
  });

  it("never treats a search snippet as a fetched page (fixture boundary)", () => {
    // `failedDiagnostic` is the only shape a non-retrieved result takes; a page
    // is present only when the document was genuinely fetched.
    const d = failedDiagnostic({ capability: "web_fetch", provider: "safe-get", tier: "unknown" }, "blocked", "x");
    expect(d.normalizedStatus).toBe("failed");
  });
});

describe("extractPdfText (bounded, no OCR)", () => {
  it("returns text for a text-layer PDF", () => {
    const r = extractPdfText("%PDF-1.4\nstream\n(Revenue 1,075,675 crore) Tj\nendstream\n%%EOF");
    expect(r.ok).toBe(true);
    expect(r.text).toContain("1,075,675");
  });

  it("reports no text layer for an image PDF", () => {
    const r = extractPdfText("%PDF-1.4\n<< /Subtype /Image >>\nstream\nXYZ\nendstream\n%%EOF");
    expect(r.ok).toBe(false);
    expect(r.note).toMatch(/OCR|scanned|no extractable/i);
  });
});
