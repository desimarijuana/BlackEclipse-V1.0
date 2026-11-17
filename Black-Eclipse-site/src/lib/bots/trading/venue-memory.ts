"use client";

// ── Last-used venue memory ──────────────────────────────────────────────────
// The operator picks the same demo account every time; making them choose it
// again is friction, not safety. This remembers the last venue they authorized
// (or selected) and offers it as the default. It NEVER changes a connection that
// is already configured on the bot, and it is only a preselection — the server
// still validates mode, arm state and the mandate.

export const VENUE_STORAGE_KEY = "eclipse.bots.lastVenue.v1";

export interface RememberedVenue {
  id: string;
  mode: string;
}

export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

function safeStorage(): StorageLike | null {
  if (typeof window === "undefined") return null;
  try {
    const probe = "__eclipse_venue_probe__";
    window.localStorage.setItem(probe, "1");
    window.localStorage.removeItem(probe);
    return window.localStorage;
  } catch {
    return null;
  }
}

export function loadLastVenue(storage: StorageLike | null = safeStorage()): RememberedVenue | null {
  if (!storage) return null;
  try {
    const raw = storage.getItem(VENUE_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { id?: unknown; mode?: unknown };
    if (typeof parsed.id !== "string" || !parsed.id.trim()) return null;
    return { id: parsed.id, mode: typeof parsed.mode === "string" ? parsed.mode : "" };
  } catch {
    return null;
  }
}

export function rememberVenue(
  venue: RememberedVenue,
  storage: StorageLike | null = safeStorage(),
): void {
  if (!storage || !venue.id) return;
  try {
    storage.setItem(VENUE_STORAGE_KEY, JSON.stringify({ id: venue.id, mode: venue.mode }));
  } catch {
    // A full/blocked storage must never break the form.
  }
}

/**
 * The venue to preselect. Rules, in order:
 *   1. an explicit current choice wins (never overwrite the bot's config);
 *   2. otherwise the remembered venue, but only if it matches the requested mode
 *      and still exists in the connection list;
 *   3. otherwise nothing.
 */
export function pickInitialVenue(input: {
  currentId?: string;
  mode: string;
  remembered: RememberedVenue | null;
  available: ReadonlyArray<{ id: string; mode: string }>;
}): string {
  if (input.currentId) return input.currentId;
  if (input.mode === "shadow" || !input.remembered) return "";
  const remembered = input.remembered;
  const match = input.available.find(
    (item) => item.id === remembered.id && item.mode === input.mode,
  );
  return match?.id ?? "";
}
