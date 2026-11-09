// ── Data-source enforcement ─────────────────────────────────────────────────
// The setup toggles are real because the fetch layer asks here before using a
// source. The read is cached in-process for 30 s (the settings/vault pattern),
// and it fails OPEN to the legacy behavior: if the DB read fails, the app keeps
// working exactly as it did before setup existed rather than going dark.
//
// A disabled source must produce an honest "unavailable"/skip result. It must
// never silently fall through to another source the user disabled.

import type { SourceId } from "@/lib/setup/types";
import { effectiveSourcePreferences } from "@/lib/setup/state";

const TTL_MS = 30_000;

let cache: { t: number; sources: Record<string, boolean> } | null = null;

export async function getSourcePreferenceMap(): Promise<Record<string, boolean>> {
  if (cache && Date.now() - cache.t < TTL_MS) return cache.sources;
  try {
    const sources = await effectiveSourcePreferences();
    cache = { t: Date.now(), sources };
    return sources;
  } catch {
    return cache?.sources ?? {};
  }
}

export async function isDataSourceEnabled(id: SourceId): Promise<boolean> {
  const sources = await getSourcePreferenceMap();
  // An absent pref keeps legacy behavior (enabled). Setup writes explicit
  // booleans for every catalog source on completion.
  return sources[id] !== false;
}

export function invalidateSourcePreferenceCache(): void {
  cache = null;
}
