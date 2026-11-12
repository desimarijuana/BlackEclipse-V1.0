// Shared bridge result helpers, kept in a leaf module so the extracted
// capability modules (`data-bridge-health`, `data-bridge-education`) and the
// dispatcher share ONE spelling of an unavailable result without a circular
// import. Split out of `data-bridge.ts` (R3-04 split follow-up).

import { makeFailure, statusForFailure, type FailureClass } from "@/lib/harness/failure";
import type { DataBridgeResult } from "@/lib/harness/data-bridge/data-bridge-types";

export function unavailable(reason?: string): DataBridgeResult {
  return { status: "UNAVAILABLE", ...(reason ? { error: reason } : {}) };
}

/** A typed unavailable result. */
export function unavailableClass(cls: FailureClass, detail?: string): DataBridgeResult {
  const f = makeFailure(cls, detail);
  return { status: statusForFailure(cls), failureClass: cls, error: f.message };
}
