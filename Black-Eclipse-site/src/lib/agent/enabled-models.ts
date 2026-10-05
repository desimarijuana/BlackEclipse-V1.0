// ── Enabled-models selection store ───────────────────────────────────────────
// A provider (OpenRouter, Ollama, …) can enumerate hundreds or thousands of
// models. Dumping them all into the pickers is unusable, so — like the way
// opencode (and editors) manage language models — discovery pulls the full
// live catalog into a Manage dialog, and the operator ENABLES the handful they
// actually want. Only enabled models appear in the compact dropdowns.
//
// This is a client-side filter, NOT a hard allowlist: the runtime still accepts
// any model id, and the free-text "Custom model id…" entry is always available.
// State is persisted per provider in localStorage and shared across surfaces
// (Settings › AI and the chat composer) via one zustand store.

'use client';

import { useEffect } from 'react';
import { create } from 'zustand';

export const ENABLED_MODELS_KEY = 'be_enabled_models_v1';

/** How many models a provider may show before we prompt to curate the list. */
export const MODEL_LIST_SOFT_LIMIT = 40;

interface Persisted {
  /** provider id → enabled model ids. A provider absent here is "all enabled". */
  providers: Record<string, string[]>;
}

function load(): Persisted {
  if (typeof window === 'undefined') return { providers: {} };
  try {
    const raw = window.localStorage.getItem(ENABLED_MODELS_KEY);
    if (!raw) return { providers: {} };
    const parsed = JSON.parse(raw) as Partial<Persisted>;
    const providers: Record<string, string[]> = {};
    for (const [id, ids] of Object.entries(parsed.providers ?? {})) {
      if (Array.isArray(ids)) providers[id] = ids.filter((m): m is string => typeof m === 'string');
    }
    return { providers };
  } catch {
    return { providers: {} };
  }
}

function save(p: Persisted) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(ENABLED_MODELS_KEY, JSON.stringify(p));
  } catch {
    // Quota / private mode — the choice applies for this session only.
  }
}

interface EnabledModelsStore {
  /** provider id → enabled ids. Absent provider means "no explicit selection". */
  providers: Record<string, string[]>;
  hydrated: boolean;
  hydrate: () => void;
  /** The enabled ids for a provider (empty array when none are curated). */
  enabledFor: (providerId: string) => string[];
  /** True when the operator has curated this provider at all. */
  isCurated: (providerId: string) => boolean;
  /** Replace the full enabled set for a provider (from the Manage dialog). */
  setEnabled: (providerId: string, ids: string[]) => void;
  /** Add one model to a provider's enabled set (e.g. a custom id). */
  enable: (providerId: string, id: string) => void;
  toggle: (providerId: string, id: string) => void;
  /** Forget a provider's curation, so it falls back to the declared list. */
  resetProvider: (providerId: string) => void;
}

export const useEnabledModelsStore = create<EnabledModelsStore>((set, get) => ({
  providers: {},
  hydrated: false,

  hydrate: () => {
    set({ providers: load().providers, hydrated: true });
  },

  enabledFor: (providerId) => get().providers[providerId] ?? [],
  isCurated: (providerId) => Array.isArray(get().providers[providerId]),

  setEnabled: (providerId, ids) =>
    set((s) => {
      const providers = { ...s.providers, [providerId]: Array.from(new Set(ids)) };
      save({ providers });
      return { providers };
    }),

  enable: (providerId, id) =>
    set((s) => {
      const current = s.providers[providerId] ?? [];
      if (current.includes(id)) return {};
      const providers = { ...s.providers, [providerId]: [...current, id] };
      save({ providers });
      return { providers };
    }),

  toggle: (providerId, id) =>
    set((s) => {
      const current = s.providers[providerId] ?? [];
      const next = current.includes(id) ? current.filter((m) => m !== id) : [...current, id];
      const providers = { ...s.providers, [providerId]: next };
      save({ providers });
      return { providers };
    }),

  resetProvider: (providerId) =>
    set((s) => {
      const providers = { ...s.providers };
      delete providers[providerId];
      save({ providers });
      return { providers };
    }),
}));

/** Hydrate the enabled-models selection from localStorage once, on the client. */
export function useHydrateEnabledModels() {
  const hydrate = useEnabledModelsStore((s) => s.hydrate);
  const hydrated = useEnabledModelsStore((s) => s.hydrated);
  useEffect(() => {
    if (!hydrated) hydrate();
  }, [hydrated, hydrate]);
}

/**
 * The models to show in a COMPACT picker for a provider.
 *
 * - A curated provider shows exactly its enabled ids (in catalog order, with any
 *   selected-but-now-unlisted id kept so the current choice never vanishes).
 * - An uncurated provider shows its declared models, capped at the soft limit,
 *   with a flag telling the caller to offer the Manage dialog.
 */
export function compactModels(
  providerId: string,
  allModels: string[],
  opts: { explicitEnabled?: string[] | null; selected?: string } = {},
): { models: string[]; truncated: boolean; curated: boolean } {
  const seen = new Set<string>();
  const out: string[] = [];
  const push = (m: string) => {
    if (m && !seen.has(m)) {
      seen.add(m);
      out.push(m);
    }
  };

  const curated = Array.isArray(opts.explicitEnabled);
  if (curated) {
    const enabled = new Set(opts.explicitEnabled ?? []);
    for (const m of allModels) if (enabled.has(m)) push(m);
    // Keep any enabled id that the catalog no longer lists (custom/discovered).
    for (const m of opts.explicitEnabled ?? []) push(m);
    if (opts.selected) push(opts.selected);
    return { models: out, truncated: false, curated: true };
  }

  for (const m of allModels) push(m);
  if (opts.selected) push(opts.selected);
  const truncated = out.length > MODEL_LIST_SOFT_LIMIT;
  const models = truncated ? out.slice(0, MODEL_LIST_SOFT_LIMIT) : out;
  return { models, truncated, curated: false };
}
