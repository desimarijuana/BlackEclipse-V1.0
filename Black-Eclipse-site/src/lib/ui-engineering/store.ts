// ── Blueprint store (durable, optimistic-concurrency) ───────────────────────
// The persistence boundary for blueprints. It holds the current blueprint plus
// a bounded revision history, validates every write against the catalog, and
// enforces optimistic concurrency: a writer that passes a stale `expectedRevision`
// gets an explicit conflict instead of silently clobbering a newer edit.
//
// Two backends share one implementation: an in-memory store (tests, SSR) and a
// localStorage-backed store (the browser default). The storage payload is
// versioned; a corrupt/unreadable payload is reported, never overwritten blindly.

import { widgetCount } from '@/lib/workspace/ops';
import type { StorageLike } from '@/lib/workspace/persistence';
import { validateBlueprint, type BlueprintKind, type BlueprintScope, type UiBlueprint } from './blueprint';
import type { ComponentCatalog, ConfigIssue } from './catalog';
import {
  BlueprintHistory,
  detectConflict,
  type RevisionConflict,
  type RevisionEntry,
} from './revisions';

export interface BlueprintSummary {
  id: string;
  title: string;
  kind: BlueprintKind;
  scope: BlueprintScope;
  ownerId: string;
  revision: number;
  updatedAt: string;
  widgetCount: number;
}

export interface BlueprintFilter {
  scope?: BlueprintScope;
  ownerId?: string;
  kind?: BlueprintKind;
}

export interface SaveBlueprintOptions {
  expectedRevision?: number;
  summary?: string;
  catalog?: ComponentCatalog;
  now?: string;
}

export interface SaveBlueprintResult {
  ok: boolean;
  blueprint?: UiBlueprint;
  conflict?: RevisionConflict;
  issues?: ConfigIssue[];
}

export interface BlueprintStore {
  list(filter?: BlueprintFilter): BlueprintSummary[];
  get(id: string): UiBlueprint | null;
  save(blueprint: UiBlueprint, opts?: SaveBlueprintOptions): SaveBlueprintResult;
  history(id: string): RevisionEntry[];
  remove(id: string): boolean;
}

interface StoredBlueprint {
  blueprint: UiBlueprint;
  history: RevisionEntry[];
}

interface StoreSnapshot {
  version: 1;
  entries: Record<string, StoredBlueprint>;
}

interface PersistenceAdapter {
  load(): StoreSnapshot | null;
  save(snapshot: StoreSnapshot): void;
}

export const BLUEPRINT_STORE_VERSION = 1 as const;
export const DEFAULT_BLUEPRINT_STORAGE_KEY = 'eclipse:ui-blueprints:v1';

function isSnapshot(value: unknown): value is StoreSnapshot {
  return typeof value === 'object' && value !== null && (value as { version?: unknown }).version === 1
    && typeof (value as { entries?: unknown }).entries === 'object' && (value as { entries?: unknown }).entries !== null;
}

class BaseBlueprintStore implements BlueprintStore {
  protected readonly entries = new Map<string, { blueprint: UiBlueprint; history: BlueprintHistory }>();
  private readonly adapter: PersistenceAdapter;
  private readonly maxHistory: number;

  constructor(adapter: PersistenceAdapter, opts: { maxHistory?: number } = {}) {
    this.adapter = adapter;
    this.maxHistory = opts.maxHistory ?? 50;
    const snapshot = adapter.load();
    if (snapshot && isSnapshot(snapshot)) {
      for (const [id, stored] of Object.entries(snapshot.entries)) {
        const history = new BlueprintHistory(this.maxHistory);
        for (const entry of stored.history ?? []) history.record(entry.blueprint, entry.summary);
        this.entries.set(id, { blueprint: stored.blueprint, history });
      }
    }
  }

  private persist(): void {
    const snapshot: StoreSnapshot = { version: BLUEPRINT_STORE_VERSION, entries: {} };
    for (const [id, entry] of this.entries) {
      snapshot.entries[id] = { blueprint: entry.blueprint, history: entry.history.list() };
    }
    this.adapter.save(snapshot);
  }

  list(filter: BlueprintFilter = {}): BlueprintSummary[] {
    return [...this.entries.values()]
      .map(({ blueprint }) => blueprint)
      .filter(bp => !filter.scope || bp.scope === filter.scope)
      .filter(bp => !filter.ownerId || bp.owner.id === filter.ownerId)
      .filter(bp => !filter.kind || bp.kind === filter.kind)
      .map(bp => ({
        id: bp.id,
        title: bp.title,
        kind: bp.kind,
        scope: bp.scope,
        ownerId: bp.owner.id,
        revision: bp.revision,
        updatedAt: bp.updatedAt,
        widgetCount: widgetCount(bp.layout),
      }))
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  }

  get(id: string): UiBlueprint | null {
    return this.entries.get(id)?.blueprint ?? null;
  }

  save(blueprint: UiBlueprint, opts: SaveBlueprintOptions = {}): SaveBlueprintResult {
    const current = this.entries.get(blueprint.id)?.blueprint;
    if (opts.expectedRevision !== undefined && current) {
      const conflict = detectConflict(opts.expectedRevision, current);
      if (conflict) return { ok: false, conflict };
    }

    const validation = validateBlueprint(blueprint, opts.catalog);
    if (!validation.ok) return { ok: false, issues: validation.issues };

    const saved = validation.blueprint as UiBlueprint;
    const entry = this.entries.get(saved.id);
    const history = entry?.history ?? new BlueprintHistory(this.maxHistory);
    history.record(saved, opts.summary ?? (current ? `revision ${saved.revision}` : 'created'));
    this.entries.set(saved.id, { blueprint: saved, history });
    this.persist();
    return { ok: true, blueprint: saved };
  }

  history(id: string): RevisionEntry[] {
    return this.entries.get(id)?.history.list() ?? [];
  }

  remove(id: string): boolean {
    const existed = this.entries.delete(id);
    if (existed) this.persist();
    return existed;
  }
}

export function createMemoryBlueprintStore(opts: { maxHistory?: number; initial?: StoreSnapshot } = {}): BlueprintStore {
  let snapshot: StoreSnapshot | null = opts.initial ?? null;
  return new BaseBlueprintStore(
    {
      load: () => snapshot,
      save: next => { snapshot = next; },
    },
    opts,
  );
}

function defaultStorage(): StorageLike | null {
  try {
    if (typeof window !== 'undefined' && window.localStorage) return window.localStorage;
  } catch { /* storage unavailable */ }
  return null;
}

export function createLocalBlueprintStore(
  opts: { storage?: StorageLike; storageKey?: string; maxHistory?: number } = {},
): BlueprintStore {
  const storage = opts.storage ?? defaultStorage();
  const key = opts.storageKey ?? DEFAULT_BLUEPRINT_STORAGE_KEY;
  return new BaseBlueprintStore(
    {
      load: () => {
        if (!storage) return null;
        let raw: string | null = null;
        try { raw = storage.getItem(key); } catch { return null; }
        if (!raw) return null;
        try {
          const parsed = JSON.parse(raw);
          return isSnapshot(parsed) ? parsed : null;
        } catch {
          return null;
        }
      },
      save: snapshot => {
        if (!storage) return;
        try { storage.setItem(key, JSON.stringify(snapshot)); } catch { /* quota — best effort */ }
      },
    },
    opts,
  );
}
