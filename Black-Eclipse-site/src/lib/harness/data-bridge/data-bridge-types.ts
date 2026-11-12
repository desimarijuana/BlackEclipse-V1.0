// Shared result type for the JDdS data bridge and the route-health ledger.
// Kept in its own module so `health-ledger.ts` (the ledger writer/readers) and
// `data-bridge.ts` (the capability dispatcher) can both import it without a
// circular dependency.

export interface DataBridgeResult {
  /**
   * `AMBIGUOUS` is a first-class outcome: the instrument identity could not be
   * pinned to a single instrument (unknown venue, ticker shared across markets,
   * or a provider answer for a different currency). It is NOT a failure to be
   * smoothed over — the caller must ask the user to disambiguate, never receive
   * a guessed instrument.
   */
  status: "OK" | "UNAVAILABLE" | "AMBIGUOUS";
  [key: string]: unknown;
}
