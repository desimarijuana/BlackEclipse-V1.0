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
    cached = loadCatalog().catch(() => ({}));
  }
  return cached;
}

export function useModelCatalog(): ModelCatalog {
  const [catalog, setCatalog] = useState<ModelCatalog>({});
  useEffect(() => {
    let live = true;
    void loadModelCatalog().then((c) => {
      if (live) setCatalog(c);
    });
    return () => {
      live = false;
    };
  }, []);
  return catalog;
}

/** The declared model ids for a provider id (empty when unknown). */
export function modelsForProvider(catalog: ModelCatalog, providerId: string | undefined): string[] {
  if (!providerId) return [];
  return catalog[providerId]?.models ?? [];
}
