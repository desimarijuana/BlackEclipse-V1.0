// ── Shared web research transport ───────────────────────────────────────────
// The ONE web page-retrieval implementation for the whole application, plus a
// diagnostic-carrying facade over the independent search providers in
// `web-search.ts`. It exists so the Phase-2 retrieval layer (`/api/harness/data`)
// and the legacy agent tool (`src/lib/agent/tools.ts`) do not each grow their own
// copy — a second web-search system is explicitly forbidden.
//
// Search: the ordered providers from `web-search.ts` (keyless DuckDuckGo HTML by
// default, plus an operator-configured JSON API when present). Page fetch: the
// SSRF-hardened `safeGet` transport. Extraction: cheerio (already a dep).
//
// Every attempt returns a `RetrievalDiagnostic` so a caller can distinguish a
// zero-result search from a transport/timeout/block/HTTP/parse failure. Nothing
// is fabricated: an unparseable page yields no page and a diagnostic.

import * as cheerio from "cheerio";
import { inflateSync } from "node:zlib";
import { safeGet, validateOutboundUrl, OutboundError } from "@/lib/connectors/security";
import {
  failedDiagnostic,
  okDiagnostic,
  type RetrievalDiagnostic,
  type RetrievalFailureCategory,
} from "@/lib/retrieval-diagnostics";
import {
  DuckDuckGoHtmlProvider,
  type SearchProvider,
  type WebSearchResult,
} from "@/lib/web-search";

export type { WebSearchResult } from "@/lib/web-search";

export interface WebPage {
  url: string;
  title: string | null;
  text: string;
  bytes: number;
  /** How the text was obtained, so a caller knows what it is reading. */
  extraction?: "html" | "json" | "xml" | "text" | "pdf";
  /** Original document language, when a `lang` attribute is present. */
  language?: string | null;
  /** Document-identity metadata preserved for citations/receipts (all optional). */
  documentId?: string | null;
  publishedAt?: string | null;
  retrievedAt?: string | null;
}

const FETCH_TIMEOUT_MS = 8_000;
// Bounded download caps. Large reports stream up to MAX_REPORT_BYTES so an
// oversized PDF/annual report can still be read; the cap is enforced by the
// streamed reader (never `res.text()`), so memory stays bounded.
const MAX_DOC_BYTES = 16 * 1024 * 1024;
const MAX_TEXT_CHARS = 40_000;

/**
 * The outbound User-Agent. A DECLARED, contact-bearing identity — verified to
 * receive 200 from SEC, `www.sec.gov`, `data.sec.gov`, TSMC IR and `pr.tsmc.com`,
 * where a spoofed browser UA receives 403. Sites that offer a crawl policy expect
 * an honest identifier; SEC's fair-access policy requires an EMAIL-shaped contact
 * (a bare repo URL is rejected with 403, verified), so the email form is used.
 */
const UA = "BlackEclipse/1.0 (open-source financial research; contact@blackeclipse.local)";

/** The declared identity exposed for hosts that publish a crawl policy. */
export const OUTBOUND_USER_AGENT = UA;

export interface SearchOutcome {
  results: WebSearchResult[];
  /** One diagnostic per provider attempted (never empty). */
  diagnostics: RetrievalDiagnostic[];
  /** Which provider supplied the results, when one did. */
  provider: string | null;
}

/**
 * Search across the ordered, independent providers. The first provider that
 * returns results wins; a provider that FAILS (not merely "no results") causes a
 * fall-through to the next, so one provider's outage does not blank the search.
 * Every attempt is recorded.
 *
 * `providers` defaults to the keyless provider — callers that can resolve the
 * operator-configured provider pass the full ordered list.
 */
export async function searchWeb(
  query: string,
  limit = 8,
  providers?: SearchProvider[]
): Promise<SearchOutcome> {
  const list = providers && providers.length > 0 ? providers : [new DuckDuckGoHtmlProvider()];
  const diagnostics: RetrievalDiagnostic[] = [];
  for (const provider of list) {
    try {
      if (!(await Promise.resolve(provider.configured()))) continue;
    } catch {
      continue;
    }
    const attempt = await provider.search(query, limit);
    diagnostics.push(attempt.diagnostic);
    if (attempt.results.length > 0) {
      return { results: attempt.results, diagnostics, provider: provider.id };
    }
    // A genuine zero-result answer is authoritative — try no further provider.
    if (attempt.diagnostic.category === "zero_results") {
      return { results: [], diagnostics, provider: provider.id };
    }
    // Otherwise this provider failed; continue to the next independent route.
  }
  return { results: [], diagnostics, provider: null };
}

/**
 * Back-compatible wrapper: ranked results only. Prefer `searchWeb` when the
 * failure reason matters.
 */
export async function webSearch(query: string, limit = 8): Promise<WebSearchResult[]> {
  const outcome = await searchWeb(query, limit);
  return outcome.results;
}

export interface FetchOutcome {
  page: WebPage | null;
  diagnostic: RetrievalDiagnostic;
}

/**
 * Retrieve a page through the SSRF-hardened transport and extract readable text,
 * recording WHY a failure happened. Handles HTML, JSON/XML/XBRL, plain text and
 * (text-based) PDFs. A document type we cannot read (e.g. a scanned/image PDF
 * with no text layer) is reported as `unsupported_document`, never returned as
 * garbage.
 */
export async function fetchWebPageDetailed(
  url: string,
  // Injectable transport for deterministic offline tests. Production always uses
  // the SSRF-hardened `safeGet`; a test supplies a stub that returns fixture
  // bytes so document-handling branches can be exercised without the network.
  deps?: { get?: typeof safeGet }
): Promise<FetchOutcome> {
  const base = { capability: "web_fetch" as const, provider: "safe-get", tier: "unknown" as const };
  const get = deps?.get ?? safeGet;
  const check = validateOutboundUrl(url);
  if (!check.safe) {
    return {
      page: null,
      diagnostic: failedDiagnostic(base, "blocked", `URL rejected: ${check.reason ?? "unsafe"}`, {
        retryable: false,
      }),
    };
  }

  const started = Date.now();
  let res;
  try {
    res = await get({
      url,
      timeoutMs: FETCH_TIMEOUT_MS,
      // Stream with a bounded document cap: large official reports are readable
      // up to MAX_DOC_BYTES, and a stream beyond it is stopped (not buffered).
      maxBytes: MAX_DOC_BYTES,
      // Official regulator/exchange hosts commonly 301/302 (Taiwan MOPS, Canada
      // SEDAR, company IR sites). Follow a bounded number, each hop re-validated
      // by the same SSRF gate (https-only, DNS-pinned).
      maxRedirects: 4,
      headers: {
        "user-agent": UA,
        accept: "text/html,application/xhtml+xml,application/json,application/xml,application/pdf,text/plain;q=0.9,*/*;q=0.5",
      },
    });
  } catch (err) {
    const code = err instanceof OutboundError ? err.code : "";
    const category: RetrievalFailureCategory =
      code === "timeout"
        ? "timeout"
        : code === "too_large"
          ? "too_large"
          : code === "blocked_host" || code === "blocked_protocol" || code === "blocked_credentials"
            ? "blocked"
            : "transport_error";
    const timedOut = category === "timeout";
    const detail =
      category === "too_large"
        ? `document exceeded the ${MAX_DOC_BYTES} byte cap`
        : timedOut
          ? `page request timed out after ${FETCH_TIMEOUT_MS} ms`
          : `page request failed (${code || "transport"})`;
    return {
      page: null,
      diagnostic: failedDiagnostic(base, category, detail, {
        latencyMs: Date.now() - started,
        timedOut,
      }),
    };
  }

  const latencyMs = Date.now() - started;
  const httpStatus = res.status;
  const bytes = res.bytes;
  if (httpStatus < 200 || httpStatus >= 300) {
    return {
      page: null,
      diagnostic: failedDiagnostic(base, "http_error", `the source returned HTTP ${httpStatus}`, {
        latencyMs,
        httpStatus,
        bytes,
      }),
    };
  }

  const type = (res.contentType ?? "").toLowerCase();
  const isPdf = type.includes("pdf");
  const isJson = type.includes("json");
  const isXml = type.includes("xml");
  const isHtml = type.includes("html");
  const isPlainText = type.includes("text") && !isHtml;

  // ── PDF: bounded text-layer extraction; scanned/image PDFs are reported. ──
  if (isPdf) {
    const extracted = extractPdfText(res.text);
    if (!extracted.ok) {
      return {
        page: null,
        diagnostic: failedDiagnostic(
          base,
          "unsupported_document",
          extracted.note ?? "PDF has no extractable text layer (likely scanned/image-only)",
          { latencyMs, httpStatus, bytes, parseOutcome: "not_attempted", retryable: false }
        ),
      };
    }
    return {
      page: { url, title: null, text: extracted.text!, bytes, extraction: "pdf" },
      diagnostic: okDiagnostic(base, { latencyMs, httpStatus, bytes, parseOutcome: "parsed" }),
    };
  }

  if (type && !isJson && !isXml && !isHtml && !isPlainText) {
    return {
      page: null,
      diagnostic: failedDiagnostic(base, "content_type_rejected", `unsupported content type "${res.contentType}"`, {
        latencyMs,
        httpStatus,
        bytes,
        retryable: false,
      }),
    };
  }

  // A JSON/XML/XBRL source document is returned as raw text so it can be handed
  // to the research layer; it is not chewed through the HTML extractor. This is
  // how a SEC company-concept or an exchange data feed becomes usable evidence.
  if (isJson || isXml || isPlainText) {
    const text = res.text.slice(0, MAX_TEXT_CHARS);
    if (!text.trim()) {
      // A valid content type with a genuinely empty body is its own category —
      // "empty response", not a parse failure and not evidence.
      return {
        page: null,
        diagnostic: failedDiagnostic(base, "empty_response", "the source returned an empty body", {
          latencyMs,
          httpStatus,
          bytes,
          parseOutcome: "empty",
        }),
      };
    }
    // An XBRL taxonomy with no values is not evidence: if the document looks
    // like XBRL but carries no numeric facts, report it as such rather than
    // handing a value-less taxonomy to the extractor.
    if (isXml && _looksLikeValueLessXbrl(text)) {
      return {
        page: null,
        diagnostic: failedDiagnostic(
          base,
          "parse_failure",
          "the XBRL document is a taxonomy/context with no numeric facts",
          { latencyMs, httpStatus, bytes, parseOutcome: "empty" }
        ),
      };
    }
    const retrievedAt = new Date().toISOString();
    return {
      page: {
        url,
        title: null,
        text,
        bytes,
        extraction: isJson ? "json" : isXml ? "xml" : "text",
        documentId: _documentIdFromUrl(url),
        retrievedAt,
      },
      diagnostic: okDiagnostic(base, { latencyMs, httpStatus, bytes, parseOutcome: "parsed" }),
    };
  }

  let $;
  try {
    $ = cheerio.load(res.text);
  } catch {
    return {
      page: null,
      diagnostic: failedDiagnostic(base, "parse_failure", "the page HTML could not be parsed", {
        latencyMs,
        httpStatus,
        bytes,
        parseOutcome: "failed",
      }),
    };
  }
  const language = $("html").attr("lang")?.trim() || null;
  const title =
    ($('meta[property="og:title"]').attr("content") || $("title").first().text() || "").trim() || null;
  const publishedAt =
    ($('meta[property="article:published_time"]').attr("content") ||
      $('meta[name="date"]').attr("content") ||
      $("time[datetime]").first().attr("datetime") ||
      "").trim() || null;
  const documentId = _documentIdFromUrl(url);
  $("script, style, noscript, nav, header, footer, aside, form, svg").remove();
  const text = $("body").text().replace(/\s+/g, " ").trim().slice(0, MAX_TEXT_CHARS);
  if (!text) {
    // A page with no body text is usually a JavaScript-only shell that must be
    // rendered in a browser; report that distinctly so the caller can escalate
    // to a JS-capable route rather than calling it "not found".
    const jsShell = /<script\b/i.test(res.text) && !/<\/body>/i.test(res.text.slice(0, 4000));
    return {
      page: null,
      diagnostic: failedDiagnostic(
        base,
        jsShell ? "javascript_only" : "parse_failure",
        jsShell
          ? "the page returned a JavaScript-only shell with no server-rendered text"
          : "the page had no readable text after extraction",
        { latencyMs, httpStatus, bytes, parseOutcome: "empty", retryable: false }
      ),
    };
  }
  return {
    page: {
      url,
      title,
      text,
      bytes: res.bytes,
      extraction: "html",
      language,
      documentId,
      publishedAt,
      retrievedAt: new Date().toISOString(),
    },
    diagnostic: okDiagnostic(base, { latencyMs, httpStatus, bytes, parseOutcome: "parsed" }),
  };
}

/**
 * A stable document id derived ONLY from the real URL (never fabricated). For a
 * known filing host this is the accession/recall number; otherwise the path
 * basename. Returned as an audit hint, not a claim about the document's content.
 */
function _documentIdFromUrl(url: string): string | null {
  try {
    const u = new URL(url);
    // SEC EDGAR accession numbers look like 0001193125-25-123456.
    const accession = u.pathname.match(/\d{10}-\d{2}-\d{6}/);
    if (accession) return accession[0];
    // DART receipt numbers are 14 digits.
    const dart = u.searchParams.get("rcpNo");
    if (dart) return dart;
    const base = u.pathname.split("/").filter(Boolean).pop();
    return base || null;
  } catch {
    return null;
  }
}

/**
 * Heuristic: an XBRL instance that declares contexts/taxonomy but contains no
 * numeric fact value is not evidence. This deliberately errs toward "no values"
 * (returning the document as unusable) rather than handing a taxonomy to the
 * extractor as if it carried facts.
 */
function _looksLikeValueLessXbrl(text: string): boolean {
  const lower = text.toLowerCase();
  const looksXbrl = lower.includes("xbrl") || lower.includes("<context") || lower.includes("xsd");
  if (!looksXbrl) return false;
  // A numeric fact appears as a non-empty element body with digits.
  const hasNumericFact = />\s*-?[\d,]{3,}(\.\d+)?\s*</.test(text);
  return !hasNumericFact;
}

// ── Bounded PDF text extraction ──────────────────────────────────────────────
// Text-layer PDFs only (uncompressed or Flate-compressed `Tj`/`TJ` operators).
// This reuses the same technique as `src/lib/chat/extract.ts` and adds no
// dependency (node:zlib is built in). A scanned/image-only PDF yields no text
// and is reported as `unsupported_document`; OCR is out of scope.

const _PDF_SHOW_RE = /\((?:\\.|[^\\()])*\)/g;
const _PDF_OP_RE = /(?:\[[^\]]*\]|\((?:\\.|[^\\()])*\))\s*T[Jj]/g;

function _decodePdfLiteral(literal: string): string {
  return literal
    .slice(1, -1)
    .replace(/\\([nrtbf])/g, (_m, c: string) =>
      c === "n" ? "\n" : c === "r" ? "\r" : c === "t" ? "\t" : c === "b" ? "\b" : "\f"
    )
    .replace(/\\([()\\])/g, "$1")
    .replace(/\\(\d{1,3})/g, (_m, oct: string) => String.fromCharCode(parseInt(oct, 8)));
}

function _pdfChunks(raw: string, out: string[]): void {
  for (const opMatch of raw.matchAll(_PDF_OP_RE)) {
    const parts: string[] = [];
    for (const litMatch of opMatch[0].matchAll(_PDF_SHOW_RE)) parts.push(_decodePdfLiteral(litMatch[0]));
    if (parts.length) out.push(parts.join(""));
  }
}

export function extractPdfText(raw: string): { ok: boolean; text?: string; note?: string } {
  const chunks: string[] = [];
  try {
    _pdfChunks(raw, chunks);
    const streamRe = /stream\r?\n([\s\S]*?)\r?\nendstream/g;
    for (const streamMatch of raw.matchAll(streamRe)) {
      const body = Buffer.from(streamMatch[1], "latin1");
      try {
        _pdfChunks(inflateSync(body).toString("latin1"), chunks);
      } catch {
        /* not a Flate stream — skip */
      }
    }
  } catch {
    /* the uncompressed pass above still ran */
  }
  const text = chunks.join("\n").replace(/\n{3,}/g, "\n\n").trim();
  if (!text) {
    return { ok: false, note: "PDF has no extractable text layer (scanned or image-only; OCR unavailable)" };
  }
  return { ok: true, text: text.slice(0, MAX_TEXT_CHARS) };
}

/**
 * Back-compatible wrapper returning the page or null. Prefer
 * `fetchWebPageDetailed` when the failure reason matters.
 */
export async function fetchWebPage(url: string): Promise<WebPage | null> {
  const outcome = await fetchWebPageDetailed(url);
  return outcome.page;
}

export { validateOutboundUrl };
