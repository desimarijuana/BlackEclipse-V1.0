"use client";

// ── Settings snapshot cache (tiny, dependency-free) ──────────────────────────
// The Settings modal is a lazily-loaded chunk that used to block on
// GET /api/settings behind a full skeleton on every cold page load. This module
// stays eager (no heavy imports) so the shell can:
//   * prefetch the payload at idle and on gear hover,
//   * paint the modal instantly from the last-known snapshot,
//   * revalidate quietly and correct anything stale.
//
// The API never returns secrets: the LLM key is masked to `hasApiKey`, so the
// snapshot is safe to keep in localStorage.

const STORAGE_KEY = "eclipse_settings_snapshot_v1";

export type SettingsSnapshotData = Record<string, unknown>;

let memory: SettingsSnapshotData | null = null;
let hydrated = false;

function readStorage(): SettingsSnapshotData | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? (parsed as SettingsSnapshotData) : null;
  } catch {
    return null;
  }
}

/** Last-known settings payload: memory first, then the persisted snapshot. */
export function getSettingsSnapshot(): SettingsSnapshotData | null {
  if (!hydrated) {
    memory = readStorage();
    hydrated = true;
  }
  return memory;
}

/** Merge and persist a partial settings payload (never a secret). */
export function saveSettingsSnapshot(patch: SettingsSnapshotData): void {
  const next = { ...(memory ?? readStorage() ?? {}), ...patch };
  memory = next;
  hydrated = true;
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    /* quota / private mode — the in-memory snapshot still works */
  }
}

let inFlight: Promise<SettingsSnapshotData | null> | null = null;

/** Fetch and cache the settings payload. Safe to call repeatedly. */
export function prefetchSettingsData(): Promise<SettingsSnapshotData | null> {
  if (typeof window === "undefined") return Promise.resolve(null);
  if (inFlight) return inFlight;
  inFlight = fetch("/api/settings", { cache: "no-store" })
    .then(async (res) => {
      if (!res.ok) return null;
      const data = (await res.json().catch(() => null)) as SettingsSnapshotData | null;
      if (!data || typeof data !== "object") return null;
      // Only cache a real payload — an error body must never replace good data.
      if (!("llm" in data) && !("preferences" in data)) return null;
      saveSettingsSnapshot(data);
      return data;
    })
    .catch(() => null)
    .finally(() => {
      inFlight = null;
    });
  return inFlight;
}
