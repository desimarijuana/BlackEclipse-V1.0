// ─── Uniform failure contract ───────────────────────────────────────────────
// Every tool and every source reports failure the same way. Before this, each
// tool invented its own wording ("No news found", "symbol not in universe",
// "bridge failure"), which conflated three materially different states — and in
// a financial tool a false "no news" reads as "nothing happened".
//
// The taxonomy is the single source of truth for *why* a call returned nothing.
// Message text is DERIVED from the class, never hand-written per tool.

export type FailureClass =
  // ── Identity ──────────────────────────────────────────────────────────────
  /** The ticker does not identify one instrument; candidates returned. */
  | "ambiguous"
  /** The market/venue qualifier is not one the system can honor. */
  | "market_unknown"
  /** The qualifier resolved, but the ticker is not in that market's universe. */
  | "not_found"
  /** The identity resolved to a different currency than the provider answered. */
  | "currency_mismatch"
  /** The identity resolved to a different venue than requested/answered. */
  | "venue_mismatch"
  /** A derivative/security type whose contract terms are required but absent. */
  | "terms_missing"
  // ── Coverage & availability (B2) ──────────────────────────────────────────
  /** No source exists for this market/asset class. Distinct from "empty". */
  | "not_covered"
  /** Source reachable, genuinely nothing stored/matched. */
  | "no_data"
  /** The source errored, timed out, or was unreachable. NOT an absence. */
  | "source_failure"
  /** Data or its parse was incomplete; never present a partial number. */
  | "incomplete"
  /** Multiple sources disagree beyond tolerance. */
  | "conflict"
  /** Bad or missing request parameters. */
  | "invalid_request";

/** A structured failure. `code` is stable; `message` is user-safe. */
export interface Failure {
  failureClass: FailureClass;
  message: string;
  /** Candidate markets when the class is `ambiguous`. */
  candidates?: string[];
}

const MESSAGES: Record<FailureClass, string> = {
  ambiguous: "The ticker matches more than one instrument; a market is required.",
  market_unknown: "The requested market/venue is not recognised.",
  not_found: "The instrument is not in the stored universe for that market.",
  currency_mismatch: "The source answered for a different currency than the instrument.",
  venue_mismatch: "The source answered for a different venue than requested.",
  terms_missing: "Contract terms (expiry/strike/right or maturity/coupon) are required and absent.",
  not_covered: "No data source covers this market or asset class.",
  no_data: "The source has no matching data.",
  source_failure: "The data source failed or was unreachable.",
  incomplete: "The data was incomplete and is withheld rather than shown partially.",
  conflict: "Sources disagree on this value.",
  invalid_request: "The request was invalid.",
};

export function failureMessage(cls: FailureClass): string {
  return MESSAGES[cls];
}

/**
 * The next route when a data source cannot answer.
 *
 * A refusal must TEACH its correction. The vault does not hold everything, so
 * the route after a failed data call is a SCRAPER for the page that has it -
 * named here, where the agent reads the failure, instead of leaving it to
 * guess (or to stop).
 */
const NEXT_ROUTE =
  ' Next route: a scraper can collect this from the page that has it - call ' +
  '`scraper_run` with the source URL (the operator approves the site once) and ' +
  'label the rows SCRAPER-sourced.';

export function makeFailure(cls: FailureClass, detail?: string, candidates?: string[]): Failure {
  const base = detail ? `${MESSAGES[cls]} ${detail}`.trim() : MESSAGES[cls];
  // An ambiguity is a question for the user, not a missing source.
  const message = cls === "ambiguous" ? base : `${base}${NEXT_ROUTE}`;
  return {
    failureClass: cls,
    message,
    ...(candidates && candidates.length ? { candidates } : {}),
  };
}

/**
 * Map a `FailureClass` to the coarse bridge `status` the Python layer already
 * understands. ONLY `ambiguous` is `AMBIGUOUS` (the caller must disambiguate);
 * everything else — including an unknown venue, which is a coverage gap, not an
 * ambiguity — is `UNAVAILABLE` with a typed class.
 */
export function statusForFailure(cls: FailureClass): "AMBIGUOUS" | "UNAVAILABLE" {
  return cls === "ambiguous" ? "AMBIGUOUS" : "UNAVAILABLE";
}

/** True when the class means "we cannot even name the instrument". */
export function isIdentityFailure(cls: FailureClass): boolean {
  return (
    cls === "ambiguous" ||
    cls === "market_unknown" ||
    cls === "not_found" ||
    cls === "currency_mismatch" ||
    cls === "venue_mismatch" ||
    cls === "terms_missing"
  );
}
