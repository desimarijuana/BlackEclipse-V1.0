// ── Structured retrieval diagnostics ────────────────────────────────────────
// Every web search and page fetch records WHY it succeeded or failed in a
// machine-readable shape. Before this, `webSearch` returned `[]` for a zero-result
// search, a DuckDuckGo anti-bot page, a timeout and a DNS failure alike, so a
// research run could not tell "the web had nothing" from "the transport is down".
//
// This is deliberately small and dependency-free: it is the contract between the
// shared web transport, the data bridge, and the Python research layer.

export type RetrievalFailureCategory =
  | "ok"
  | "zero_results"          // the provider answered, genuinely nothing matched
  | "transport_error"       // DNS/TLS/socket failure before or during the request
  | "timeout"               // the request exceeded its time budget
  | "blocked"               // SSRF/robots/anti-bot/host refusal — not retryable
  | "http_error"            // a non-2xx status from the remote
  | "content_type_rejected" // fetched, but the body type is not usable
  | "unsupported_document"  // e.g. a scanned/image PDF with no text layer (no OCR)
  | "javascript_only"       // a JS-rendered shell with no server-rendered text
  | "paywalled"             // a login/subscription wall with no freely-readable body
  | "parse_failure"         // fetched, but nothing parseable was extracted
  | "too_large"             // the document exceeded the bounded size cap
  | "empty_response"        // the remote returned a 2xx with an empty body
  | "not_configured"        // the provider has no credentials/base URL
  | "invalid_request";      // bad input (empty query, bad URL)

export interface RetrievalDiagnostic {
  /** Which capability produced this diagnostic. */
  capability: "web_search" | "web_fetch";
  /** The provider/transport id, e.g. "duckduckgo-html", "custom-search", "safe-get". */
  provider: string;
  /** Source trust tier where meaningful (search engines are secondary). */
  tier: "primary" | "official" | "secondary" | "unknown";
  /** Coarse outcome: an `ok` diagnostic with category `zero_results` still means OK. */
  normalizedStatus: "ok" | "failed";
  category: RetrievalFailureCategory;
  httpStatus: number | null;
  latencyMs: number;
  timedOut: boolean;
  /** Number of results/results parsed, when a count is meaningful. */
  resultCount: number | null;
  /** Response size in bytes, when known. */
  bytes: number | null;
  parseOutcome: "parsed" | "empty" | "not_attempted" | "failed";
  /** Whether a bounded retry could plausibly help (timeouts, 5xx, 429, network). */
  retryable: boolean;
  /** Safe, user-readable detail. Never contains secrets or full response bodies. */
  detail: string;
}

/** Build an `ok` diagnostic for a successful, non-empty retrieval. */
export function okDiagnostic(
  base: Pick<RetrievalDiagnostic, "capability" | "provider" | "tier">,
  over: Partial<RetrievalDiagnostic> = {}
): RetrievalDiagnostic {
  return {
    capability: base.capability,
    provider: base.provider,
    tier: base.tier,
    normalizedStatus: "ok",
    category: "ok",
    httpStatus: null,
    latencyMs: 0,
    timedOut: false,
    resultCount: null,
    bytes: null,
    parseOutcome: "parsed",
    retryable: false,
    detail: "",
    ...over,
  };
}

/** Build a `failed` diagnostic. `retryable` defaults by category. */
export function failedDiagnostic(
  base: Pick<RetrievalDiagnostic, "capability" | "provider" | "tier">,
  category: RetrievalFailureCategory,
  detail: string,
  over: Partial<RetrievalDiagnostic> = {}
): RetrievalDiagnostic {
  const retryable =
    over.retryable ??
    (category === "timeout" ||
      category === "transport_error" ||
      (category === "http_error" && (over.httpStatus === 429 || (over.httpStatus ?? 0) >= 500)));
  return {
    capability: base.capability,
    provider: base.provider,
    tier: base.tier,
    normalizedStatus: "failed",
    category,
    httpStatus: null,
    latencyMs: 0,
    timedOut: false,
    resultCount: null,
    bytes: null,
    parseOutcome: "not_attempted",
    retryable,
    detail,
    ...over,
  };
}

/** A diagnostic that is OK but explicitly represents "answered, nothing found". */
export function zeroResultDiagnostic(
  base: Pick<RetrievalDiagnostic, "capability" | "provider" | "tier">,
  detail = "the provider answered but returned no matches",
  over: Partial<RetrievalDiagnostic> = {}
): RetrievalDiagnostic {
  return okDiagnostic(base, {
    category: "zero_results",
    resultCount: 0,
    parseOutcome: "empty",
    detail,
    ...over,
  });
}

/** True when every diagnostic records a genuine transport/provider failure. */
export function allFailed(diagnostics: RetrievalDiagnostic[]): boolean {
  return diagnostics.length > 0 && diagnostics.every((d) => d.normalizedStatus === "failed");
}
