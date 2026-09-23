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
}

const FETCH_TIMEOUT_MS = 8_000;
const MAX_HTML_BYTES = 512 * 1024;
const MAX_TEXT_CHARS = 20_000;

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36";

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
 * recording WHY a failure happened. A JSON body (e.g. a SEC XBRL endpoint) is
 * accepted and returned as raw text rather than rejected as "not HTML" — the
 * previous behaviour silently discarded valid machine-readable source documents.
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
      maxBytes: MAX_HTML_BYTES,
      headers: { "user-agent": UA, accept: "text/html,application/xhtml+xml,application/json,text/plain;q=0.9,*/*;q=0.5" },
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
  const isJson = type.includes("json");
  const isTextual = type.includes("html") || type.includes("xml") || type.includes("text");
  if (type && !isTextual && !isJson) {
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

  // A JSON source document is returned as raw text so it can be handed to the
  // research layer; it is not chewed through the HTML extractor.
  if (isJson) {
    const text = res.text.slice(0, MAX_TEXT_CHARS);
    if (!text.trim()) {
      return {
        page: null,
        diagnostic: failedDiagnostic(base, "parse_failure", "the JSON source body was empty", {
          latencyMs,
          httpStatus,
          bytes,
          parseOutcome: "empty",
        }),
      };
    }
    return {
      page: { url, title: null, text, bytes },
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
  $("script, style, noscript, nav, header, footer, aside, form, svg").remove();
  const title =
    ($('meta[property="og:title"]').attr("content") || $("title").first().text() || "").trim() || null;
  const text = $("body").text().replace(/\s+/g, " ").trim().slice(0, MAX_TEXT_CHARS);
  if (!text) {
    return {
      page: null,
      diagnostic: failedDiagnostic(base, "parse_failure", "the page had no readable text after extraction", {
        latencyMs,
        httpStatus,
        bytes,
        parseOutcome: "empty",
      }),
    };
  }
  return {
    page: { url, title, text, bytes: res.bytes },
    diagnostic: okDiagnostic(base, { latencyMs, httpStatus, bytes, parseOutcome: "parsed" }),
  };
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
