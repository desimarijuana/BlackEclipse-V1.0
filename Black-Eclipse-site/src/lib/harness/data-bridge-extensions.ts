// ─── Extended bridge dispatch (Phase 16 remainder) ──────────────────────────
// Capability modules that landed after `data-bridge.ts` hit its size ratchet
// (1400 lines; may only shrink) are dispatched HERE, from the dispatcher's
// default branch, so adding the NEXT capability costs `data-bridge.ts` zero
// lines. Same contract as its inline cases: resolve the implementation lazily
// and return its result, or `null` when this extension point does not own the
// capability (the caller then reports it unknown — never a silent pass).

import type { DataBridgeResult } from "./data-bridge-types";

export async function dispatchExtendedCapability(
  capability: string,
  params: Record<string, unknown>,
): Promise<DataBridgeResult | null> {
  switch (capability) {
    case "sec_filing_list":
      return (await import("./data-bridge-filings")).secFilingListCapability(params);
    case "custom_dataset_records":
      return (await import("./data-bridge-datasets")).customDatasetRecordsCapability(params);
    default:
      return null;
  }
}
