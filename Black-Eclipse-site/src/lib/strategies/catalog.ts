"use client";

// ── Strategy catalog (one client source for both surfaces) ─────────────────
// Strategy Studio's library and the New-bot picker read the same list, including
// the newest backtest/approval/paper evidence. A single store means an agent-made
// strategy appears in both places without a reload.
//
// Refresh policy: on first subscribe, on window focus, when the tab becomes
// visible, after an agent turn completes (`invalidateStrategyCatalog`), and by an
// explicit Refresh button. Requests are coalesced; a stale response never
// overwrites a newer one.

import { useSyncExternalStore } from "react";
import { backtestClient, type StrategySummary } from "@/lib/backtest/backtest-client";

export interface StrategyCatalogState {
  items: StrategySummary[];
  loading: boolean;
  error: string | null;
  includeArchived: boolean;
  updatedAt: number;
}

/**
 * Is this backtest a SUCCESS? The quant engine reports `"OK"` (see
 * `ResearchResult.status`); older callers/tests say `"completed"`. Accept both so
 * a finished run never renders as a warning.
 */
export function isBacktestComplete(status?: string | null): boolean {
  const value = String(status ?? "").trim().toLowerCase();
  return value === "completed" || value === "ok";
}

export type StrategySort = "updated" | "name";

/** Sort the catalog for the library rail (name A→Z or newest first). */
export function sortStrategies(
  items: readonly StrategySummary[],
  sort: StrategySort,
): StrategySummary[] {
  const copy = [...items];
  if (sort === "name") {
    return copy.sort((a, b) =>
      (a.name || a.id).localeCompare(b.name || b.id, undefined, { sensitivity: "base" }),
    );
  }
  return copy.sort((a, b) => (b.updatedAt ?? "").localeCompare(a.updatedAt ?? ""));
}

const initialState: StrategyCatalogState = {
  items: [],
  loading: true,
  error: null,
  includeArchived: false,
  updatedAt: 0,
};

let state: StrategyCatalogState = initialState;
let listeners = new Set<() => void>();
let inflight: Promise<void> | null = null;
let requestSeq = 0;

function emit(patch: Partial<StrategyCatalogState>): void {
  state = { ...state, ...patch };
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  if (listeners.size === 1) {
    // First surface mounted: make sure it has data.
    if (!state.updatedAt || Date.now() - state.updatedAt > 30_000) {
      void refreshStrategyCatalog();
    }
  }
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): StrategyCatalogState {
  return state;
}

export async function refreshStrategyCatalog(
  options: { includeArchived?: boolean } = {},
): Promise<void> {
  const includeArchived = options.includeArchived ?? state.includeArchived;
  if (inflight) {
    await inflight;
    // A second caller with a different archive scope needs its own read.
    if (includeArchived === state.includeArchived) return;
  }
  const seq = ++requestSeq;
  emit({ loading: true, error: null, includeArchived });
  inflight = (async () => {
    try {
      const items = await backtestClient.listStrategyCatalog(includeArchived);
      if (seq !== requestSeq) return;
      emit({ items, loading: false, error: null, updatedAt: Date.now() });
    } catch (err) {
      if (seq !== requestSeq) return;
      emit({
        loading: false,
        error: err instanceof Error ? err.message : "could not read the strategy library",
      });
    } finally {
      inflight = null;
    }
  })();
  await inflight;
}

/**
 * Mark the catalog stale. With a mounted surface it refreshes immediately (an
 * agent turn just finished); otherwise the next subscriber refreshes.
 */
export function invalidateStrategyCatalog(): void {
  emit({ updatedAt: 0 });
  if (listeners.size > 0) void refreshStrategyCatalog();
}

export function setCatalogArchiveScope(includeArchived: boolean): void {
  void refreshStrategyCatalog({ includeArchived });
}

export function useStrategyCatalog(): StrategyCatalogState & {
  refresh: () => void;
  setIncludeArchived: (value: boolean) => void;
} {
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  return {
    ...snapshot,
    refresh: () => void refreshStrategyCatalog(),
    setIncludeArchived: setCatalogArchiveScope,
  };
}

// Keep the list fresh when the operator comes back to the app. Registered once.
if (typeof window !== "undefined") {
  window.addEventListener("focus", () => {
    if (listeners.size > 0) void refreshStrategyCatalog();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && listeners.size > 0) {
      void refreshStrategyCatalog();
    }
  });
}

/** Test-only: reset the module store between cases. */
export function __resetStrategyCatalog(): void {
  state = initialState;
  listeners = new Set();
  inflight = null;
  requestSeq = 0;
}

/** Test-only: read the current snapshot without React. */
export function __getStrategyCatalogState(): StrategyCatalogState {
  return state;
}

/** Test-only: simulate a mounted surface (starts the first refresh). */
export function __subscribeStrategyCatalog(listener: () => void): () => void {
  return subscribe(listener);
}
