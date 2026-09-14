// ── Market Workspace — persistence ───────────────────────────────────────────
// localStorage-backed, keyed per workspace profile. Corrupt data is NEVER
// overwritten: a failed parse/validation returns the fallback and leaves the
// stored payload untouched so a future fixed reader can still recover it.

import { normalizeLayout } from './ops';
import type { MarketWorkspaceLayout } from './types';

export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

function defaultStorage(): StorageLike | null {
  try {
    if (typeof window !== 'undefined' && window.localStorage) return window.localStorage;
  } catch { /* storage unavailable (private mode etc.) */ }
  return null;
}

export function saveWorkspace(key: string, layout: MarketWorkspaceLayout, storage?: StorageLike): void {
  const s = storage ?? defaultStorage();
  if (!s) return;
  try { s.setItem(key, JSON.stringify(layout)); } catch { /* quota — best effort */ }
}

export function clearWorkspace(key: string, storage?: StorageLike): void {
  const s = storage ?? defaultStorage();
  if (!s) return;
  try { s.removeItem(key); } catch { /* ignore */ }
}

export interface LoadResult {
  layout: MarketWorkspaceLayout;
  /** True when stored data existed but could not be parsed/validated. */
  corrupt: boolean;
}

export function loadWorkspace(
  key: string,
  fallback: MarketWorkspaceLayout,
  storage?: StorageLike,
): LoadResult {
  const s = storage ?? defaultStorage();
  if (!s) return { layout: fallback, corrupt: false };
  let raw: string | null = null;
  try { raw = s.getItem(key); } catch { return { layout: fallback, corrupt: false }; }
  if (!raw) return { layout: fallback, corrupt: false };

  let parsed: unknown;
  try { parsed = JSON.parse(raw); } catch {
    return { layout: fallback, corrupt: true };
  }
  const normalized = normalizeLayout(parsed);
  if (!normalized) return { layout: fallback, corrupt: true };
  return { layout: normalized, corrupt: false };
}
