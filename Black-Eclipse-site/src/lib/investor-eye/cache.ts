// ── Investor Eye — server cache ──────────────────────────────────────────────
// In-memory SWR cache for the assembled world state, plus a persisted
// last-known snapshot in `SystemConfig` so a cold start (or a total source
// outage) can still answer "last known: HH:MM UTC" instead of a blank map.
//
// No Redis: the app is a single-node, zero-config install, and the existing
// routes already use this exact pattern (see /api/indices).

import { prisma } from '@/lib/db';
import type { InvestorEyeState } from './types';

export const CACHE_TTL_MS = 3 * 60 * 1000; // assembled state stays fresh for 3 min
const PERSIST_KEY = 'api_cache:investor-eye:state';

let cache: { t: number; data: InvestorEyeState } | null = null;

export function getCachedState(): InvestorEyeState | null {
  return cache?.data ?? null;
}

export function isCacheFresh(): boolean {
  return Boolean(cache && Date.now() - cache.t < CACHE_TTL_MS);
}

export function setCachedState(data: InvestorEyeState): void {
  cache = { t: Date.now(), data };
}

/** Test seam. */
export function clearCache(): void {
  cache = null;
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
