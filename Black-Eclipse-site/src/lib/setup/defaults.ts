// ── Setup defaults ──────────────────────────────────────────────────────────
// Two different "defaults" matter:
//
//   safeSourceDefaults()   what a NEW user gets. Open data only; no connected
//                          account and no community/scraper source is enabled.
//   legacySourceDefaults() what an EXISTING install keeps when the source-prefs
//                          key does not exist yet. It preserves today's fetcher
//                          chain so an upgrade never silently breaks live data.
//
// Keeping these separate is the whole migration safety story.

import type { SetupMode, SourceId } from "./types";
import { SOURCES } from "./source-catalog";

/** Every source id in the catalog, in stable order. */
export const ALL_SOURCE_IDS: SourceId[] = SOURCES.map((s) => s.id);

/** A new install: open data on, connected/advanced off. */
export function safeSourceDefaults(_mode: SetupMode = "personal"): Record<SourceId, boolean> {
  const out = {} as Record<SourceId, boolean>;
  for (const source of SOURCES) {
    out[source.id] = source.tier === "included" && source.defaultOn;
  }
  return out;
}

/**
 * An existing install: preserve the current fetch behavior when the preference
 * key is absent. The scraper chain, crypto ticker, keyless search and open
 * sources were all active before setup existed.
 */
export function legacySourceDefaults(): Record<SourceId, boolean> {
  const out = {} as Record<SourceId, boolean>;
  for (const source of SOURCES) {
    out[source.id] = true;
  }
  return out;
}

/** Sources that a commercial mode must never enable without acknowledgement. */
export function restrictedSourceIds(): SourceId[] {
  return SOURCES.filter(
    (s) => s.tier === "advanced" || s.commercial === "personal-only",
  ).map((s) => s.id);
}

export function isRestrictedSource(id: string): boolean {
  return restrictedSourceIds().includes(id as SourceId);
}
