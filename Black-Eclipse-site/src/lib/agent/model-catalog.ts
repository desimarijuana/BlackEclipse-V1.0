"use client";

// ── Declared model catalog (client) ─────────────────────────────────────────
// The Python runtime owns the model catalog (`/api/harness/models` → the
// `/models` runtime route). This hook fetches it once and exposes the declared
// model ids per provider id for the Settings › AI / LLM model picker.
//
// It is a CONVENIENCE list, never an allowlist: the operator may always type a
// model id the catalog does not know. When the runtime is unavailable the hook
// degrades to an empty map and the UI falls back to the free-text field, so the
// picker never blocks configuring a model.

import { useEffect, useState } from "react";

export interface CatalogProvider {
  id: string;
  label?: string;
  defaultBaseUrl?: string | null;
  defaultModel?: string;
  contextWindow?: number | null;
  models?: string[];
  /** Declared model id → resolved context window (null when unknown). */
  modelWindows?: Record<string, number | null>;
  /** True when the provider can only enumerate its models at runtime (Ollama,
   * LM Studio, a router). The UI offers a live discovery probe for these. */
  dynamicDiscovery?: boolean;
}

export type ModelCatalog = Record<string, CatalogProvider>;

let cached: Promise<ModelCatalog> | null = null;

async function loadCatalog(): Promise<ModelCatalog> {
  const res = await fetch("/api/harness/models");
  if (!res.ok) throw new Error(`catalog HTTP ${res.status}`);
  const body = (await res.json()) as { providers?: CatalogProvider[] };
  const map: ModelCatalog = {};
  for (const provider of body.providers ?? []) {
    if (provider?.id) map[provider.id] = provider;
  }
  return map;
}

/** Fetch the runtime's declared model catalog once per page load. */
export function loadModelCatalog(force = false): Promise<ModelCatalog> {
  if (!cached || force) {
    cached = loadCatalog().catch(() => {
      // A failed probe must NOT be memoised for the whole page: the Python
      // runtime is often still starting when Settings first mounts, and the
      // empty promise used to stick until a full reload — the model picker then
      // showed no models and no Discover action. Clearing it lets the next
      // caller retry.
      cached = null;
      return {};
    });
  }
  return cached;
}

/** Retry cadence while the runtime is still starting (catalog comes back empty). */
const CATALOG_RETRY_MS = 1500;
const CATALOG_MAX_ATTEMPTS = 3;

export function useModelCatalog(): ModelCatalog {
  const [catalog, setCatalog] = useState<ModelCatalog>({});
  useEffect(() => {
    let live = true;
    const timers: ReturnType<typeof setTimeout>[] = [];
    // The Python runtime cold-starts behind the Next front door, so the first fetch of
    // a session can legitimately come back empty. Retry a few times instead of
    // leaving the model picker blank until the operator reloads the app, and never
    // replace an already-loaded catalog with an empty one.
    const load = (attempt: number) => {
      void loadModelCatalog(attempt > 0).then((next) => {
        if (!live) return;
        if (Object.keys(next).length > 0) {
          setCatalog(next);
          return;
        }
        if (attempt + 1 < CATALOG_MAX_ATTEMPTS) {
          timers.push(setTimeout(() => load(attempt + 1), CATALOG_RETRY_MS));
        }
      });
    };
    load(0);
    return () => {
      live = false;
      for (const t of timers) clearTimeout(t);
    };
  }, []);
  return catalog;
}

/** The declared model ids for a provider id (empty when unknown). */
export function modelsForProvider(catalog: ModelCatalog, providerId: string | undefined): string[] {
  if (!providerId) return [];
  return catalog[providerId]?.models ?? [];
}
