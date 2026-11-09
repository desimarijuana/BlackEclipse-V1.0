// ── Settings route cache (server-only) ──────────────────────────────────────
// The GET /api/settings snapshot lives here, not inside the route module, so
// other server code (setup completion, reset scopes) can invalidate it without
// importing a route file (Next route modules must only export HTTP handlers).

export interface CachedSettingsSnapshot {
  t: number;
  data: unknown;
}

let cache: CachedSettingsSnapshot | null = null;
let rebuildInFlight = false;

export function getSettingsCache(): CachedSettingsSnapshot | null {
  return cache;
}

export function setSettingsCache(data: unknown): void {
  cache = { t: Date.now(), data };
}

export function invalidateSettingsCache(): void {
  cache = null;
}

export function isSettingsRebuildInFlight(): boolean {
  return rebuildInFlight;
}

export function setSettingsRebuildInFlight(value: boolean): void {
  rebuildInFlight = value;
}
