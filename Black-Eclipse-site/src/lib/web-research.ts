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
}

const FETCH_TIMEOUT_MS = 8_000;
const MAX_HTML_BYTES = 512 * 1024;
const MAX_PDF_BYTES = 8 * 1024 * 1024;
const MAX_TEXT_CHARS = 20_000;

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
export async function fetchWebPageDetailed(url: string): Promise<FetchOutcome> {
  const base = { capability: "web_fetch" as const, provider: "safe-get", tier: "unknown" as const };
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
    res = await safeGet({
      url,
      timeoutMs: FETCH_TIMEOUT_MS,
      maxBytes: MAX_PDF_BYTES,
      headers: {
        "user-agent": UA,
        accept: "text/html,application/xhtml+xml,application/json,application/xml,application/pdf,text/plain;q=0.9,*/*;q=0.5",
      },
    });
  } catch (err) {
    const code = err instanceof OutboundError ? err.code : "";
    const category =
      code === "timeout"
        ? "timeout"
        : code === "blocked_host" || code === "blocked_protocol" || code === "blocked_credentials"
          ? "blocked"
          : "transport_error";
    const timedOut = category === "timeout";
    return {
      page: null,
      diagnostic: failedDiagnostic(
        base,
        category,
        timedOut ? `page request timed out after ${FETCH_TIMEOUT_MS} ms` : `page request failed (${code || "transport"})`,
        { latencyMs: Date.now() - started, timedOut }
      ),
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
      return {
        page: null,
        diagnostic: failedDiagnostic(base, "parse_failure", "the source body was empty", {
          latencyMs,
          httpStatus,
          bytes,
          parseOutcome: "empty",
        }),
      };
    }
    return {
      page: { url, title: null, text, bytes, extraction: isJson ? "json" : isXml ? "xml" : "text" },
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
  $("script, style, noscript, nav, header, footer, aside, form, svg").remove();
  const title =
    ($('meta[property="og:title"]').attr("content") || $("title").first().text() || "").trim() || null;
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
    page: { url, title, text, bytes: res.bytes, extraction: "html", language },
    diagnostic: okDiagnostic(base, { latencyMs, httpStatus, bytes, parseOutcome: "parsed" }),
  };
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
