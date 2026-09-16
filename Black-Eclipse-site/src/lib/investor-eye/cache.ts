// ── Investor Eye — server cache ──────────────────────────────────────────────
// In-memory SWR cache for the assembled world state, plus a persisted
// last-known snapshot in `SystemConfig` so a cold start (or a total source
// outage) can still answer "last known: HH:MM UTC" instead of a blank map.
//
// No Redis: the app is a single-node, zero-config install.
//
// ANCHORED ON `globalThis` (like `lib/db.ts` and `connectors/registry.ts`).
// Next.js evaluates each route handler in its own module instance, so a plain
// module-level `let` would give every endpoint a SEPARATE cache — `/state`,
// `/risk`, `/markets`, `/layers` … would each cold-assemble the full source
// ingestion independently (GDELT alone can take ~10s per query). Sharing one
// cache and one in-flight guard across route bundles is what keeps every
// endpoint fast and stops them from stampeding the public sources.

import { prisma } from '@/lib/db';
import type { InvestorEyeState } from './types';

export const CACHE_TTL_MS = 3 * 60 * 1000; // assembled state stays fresh for 3 min
const PERSIST_KEY = 'api_cache:investor-eye:state';

interface CacheState {
  /**
   * Assembled states keyed by window (`hours`). Windows must not share one
   * slot: `/risk?hours=24` and `/state?hours=168` are different payloads, and a
   * single slot would have them overwrite each other.
   */
  cache: Map<string, { t: number; data: InvestorEyeState }>;
  /**
   * In-flight assemblies keyed by window. Callers await the SAME promise, so a
   * cold `/state` and `/risk` fan-out triggers exactly ONE source ingestion
   * instead of one per route (GDELT alone can take ~10s per query).
   */
  inflight: Map<string, Promise<InvestorEyeState>>;
}

const globalForCache = globalThis as unknown as {
  investorEyeCache: CacheState | undefined;
};

const state: CacheState =
  globalForCache.investorEyeCache ?? { cache: new Map(), inflight: new Map() };
globalForCache.investorEyeCache = state;

/** Stable cache key for a window (defaults to the standard 24h window). */
export function windowKey(hours?: number): string {
  return String(hours ?? 24);
}

export function getCachedState(hours?: number): InvestorEyeState | null {
  return state.cache.get(windowKey(hours))?.data ?? null;
}

export function isCacheFresh(hours?: number): boolean {
  const entry = state.cache.get(windowKey(hours));
  return Boolean(entry && Date.now() - entry.t < CACHE_TTL_MS);
}

export function setCachedState(data: InvestorEyeState, hours?: number): void {
  state.cache.set(windowKey(hours ?? data.windowHours), { t: Date.now(), data });
}

/** The in-flight assembly for a window, if one is running. */
export function getInflight(hours?: number): Promise<InvestorEyeState> | undefined {
  return state.inflight.get(windowKey(hours));
}

export function setInflight(hours: number, promise: Promise<InvestorEyeState>): void {
  state.inflight.set(windowKey(hours), promise);
}

export function clearInflight(hours: number): void {
  state.inflight.delete(windowKey(hours));
}

/** True while ANY assembly is running (used by the route's status field). */
export function isAssembling(): boolean {
  return state.inflight.size > 0;
}

/** Test seam. */
export function clearCache(): void {
  state.cache.clear();
  state.inflight.clear();
}

/** Persist the last good assembled state (best-effort). */
export async function persistState(data: InvestorEyeState): Promise<void> {
  try {
    await prisma.systemConfig.upsert({
      where: { key: PERSIST_KEY },
      update: { value: JSON.stringify(data) },
      create: { key: PERSIST_KEY, value: JSON.stringify(data) },
    });
  } catch {
    /* persistence is best-effort — never break a live response */
  }
}

/** Load the last persisted state (cold start), if any. */
export async function loadPersistedState(): Promise<InvestorEyeState | null> {
  try {
    const row = await prisma.systemConfig.findUnique({ where: { key: PERSIST_KEY } });
    if (!row?.value) return null;
    const parsed = JSON.parse(row.value) as InvestorEyeState;
    if (parsed && Array.isArray(parsed.events)) return parsed;
  } catch {
    /* fall through */
  }
  return null;
}
