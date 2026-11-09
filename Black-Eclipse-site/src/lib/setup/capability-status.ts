// ── Capability status (client-safe) ─────────────────────────────────────────
// One derivation shared by the API payload and the review screen, so the status
// the user sees while editing is the same status the server returns after save.

import type { CapabilityDef, CapabilityStatus } from "./types";
import { sourceById } from "./source-catalog";

export function computeCapabilityStatus(
  cap: CapabilityDef,
  sources: Record<string, boolean>,
  keyConfigured: (envVar: string) => boolean,
): CapabilityStatus {
  const includedOn = cap.included.some((id) => sources[id] === true);
  const advancedOn = cap.advanced.some((id) => sources[id] === true);
  const connectedReady = cap.connected.some((id) => {
    const envVar = sourceById(id)?.envVar;
    return Boolean(envVar && keyConfigured(envVar));
  });
  if (includedOn || advancedOn || connectedReady) return "ready";
  if (cap.connected.length > 0) return "needs-key";
  return "off";
}
