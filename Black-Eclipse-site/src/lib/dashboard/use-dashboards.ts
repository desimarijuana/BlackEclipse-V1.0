'use client';

// ── useDashboards — multiple-dashboard manager ───────────────────────────────
// Thin layer over the workspace kernel. Each dashboard is a named entry with
// its own storageKey; the kernel already keys stores by storageKey, so each
// dashboard gets an independent, persisted layout. This manager owns the
// dashboard index (list, active id, default id) and CRUD.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { newId } from '@/lib/workspace/types';
import { getDashboardTemplate } from './templates';
import { DASHBOARD_WIDGET_IDS } from './registry';

export interface DashboardEntry {
  id: string;
  name: string;
  /** localStorage key for this dashboard's layout. */
  storageKey: string;
  /** Template id used to seed the layout (first creation only). */
  templateId: string;
  isDefault: boolean;
}

const INDEX_KEY = 'be_dashboards_index_v3';
const ONBOARDED_KEY = 'be_dashboards_onboarded_v1';

// Bump the storage prefix when the widget catalog changes so stale layouts
// (referencing removed widget ids) don't leave empty columns. A fresh default
// template loads instead.
export const DASHBOARD_STORAGE_PREFIX = 'be_ws_dashboard_v3_';

// Legacy index keys, newest first. When the storage prefix is bumped we migrate
// the user's existing dashboards forward instead of silently seeding a fresh
// default (which made layouts appear "lost" after an update).
const LEGACY_INDEX_KEYS = ['be_dashboards_index_v2', 'be_dashboards_index_v1'];

/**
 * One-time migration from an older dashboard index/prefix to the current one.
 * Copies each legacy layout payload to its new storageKey and rewrites the
 * index. Idempotent: once v3 exists this is a no-op. Returns the migrated list
 * (or [] when there is nothing to migrate).
 */
function migrateLegacyDashboards(): DashboardEntry[] {
  if (typeof window === 'undefined') return [];
  try {
    for (const legacyKey of LEGACY_INDEX_KEYS) {
      const raw = localStorage.getItem(legacyKey);
      if (!raw) continue;
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) continue;
      const migrated: DashboardEntry[] = [];
      for (const e of parsed) {
        if (!e || typeof e.id !== 'string' || typeof e.name !== 'string') continue;
        const oldKey = typeof e.storageKey === 'string' ? e.storageKey : '';
        const newKey = `${DASHBOARD_STORAGE_PREFIX}${e.id}`;
        // Copy the layout payload to the new key (if it exists and isn't already there).
        if (oldKey && oldKey !== newKey) {
          try {
            const layout = localStorage.getItem(oldKey);
            if (layout && !localStorage.getItem(newKey)) localStorage.setItem(newKey, layout);
          } catch { /* best effort */ }
        }
        migrated.push({
          id: e.id,
          name: e.name,
          storageKey: newKey,
          templateId: typeof e.templateId === 'string' ? e.templateId : 'trader',
          isDefault: !!e.isDefault,
        });
      }
      if (migrated.length === 0) continue;
      if (!migrated.some((d) => d.isDefault)) migrated[0].isDefault = true;
      persistIndex(migrated);
      return migrated;
    }
  } catch { /* fall through to fresh seed */ }
  return [];
}

/** True when a dashboard entry has no stored layout yet (auto-seeded default). */
function isUnseeded(entry: DashboardEntry): boolean {
  try { return !localStorage.getItem(entry.storageKey); } catch { return true; }
}

function loadIndex(): DashboardEntry[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(INDEX_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((e): e is DashboardEntry =>
      e && typeof e.id === 'string' && typeof e.storageKey === 'string' && typeof e.name === 'string');
  } catch {
    return [];
  }
}

function persistIndex(list: DashboardEntry[]) {
  try { localStorage.setItem(INDEX_KEY, JSON.stringify(list)); } catch { /* best effort */ }
}

function seedDashboard(name: string, templateId: string): DashboardEntry {
  const id = newId('dash');
  return { id, name, storageKey: `${DASHBOARD_STORAGE_PREFIX}${id}`, templateId, isDefault: false };
}

export function isOnboarded(): boolean {
  if (typeof window === 'undefined') return true;
  try { return localStorage.getItem(ONBOARDED_KEY) === '1'; } catch { return true; }
}

export function markOnboarded() {
  try { localStorage.setItem(ONBOARDED_KEY, '1'); } catch { /* best effort */ }
}

export function useDashboards() {
  const [list, setList] = useState<DashboardEntry[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let existing = loadIndex();
    // If the current index only holds an auto-seeded default with no saved
    // layout, try to recover the user's legacy dashboards before giving up.
    const onlyUnseededSeed = existing.length === 1 && existing[0].templateId === 'trader' && isUnseeded(existing[0]);
    if (existing.length === 0 || onlyUnseededSeed) {
      const migrated = migrateLegacyDashboards();
      if (migrated.length > 0) existing = migrated;
    }
    let next = existing;
    if (next.length === 0) {
      // First run: seed a default "Main" dashboard from the Trader template.
      const main = seedDashboard('Main', 'trader');
      main.isDefault = true;
      next = [main];
      persistIndex(next);
    }
    setList(next);
    setActiveId(next.find(d => d.isDefault)?.id ?? next[0].id);
    setLoaded(true);
  }, []);

  const active = useMemo(() => list.find(d => d.id === activeId) ?? null, [list, activeId]);

  const create = useCallback((name: string, templateId: string) => {
    const entry = seedDashboard(name || 'Untitled', templateId);
    setList(prev => {
      const next = [...prev, entry];
      persistIndex(next);
      return next;
    });
    setActiveId(entry.id);
    return entry;
  }, []);

  const rename = useCallback((id: string, name: string) => {
    setList(prev => {
      const next = prev.map(d => (d.id === id ? { ...d, name: name || d.name } : d));
      persistIndex(next);
      return next;
    });
  }, []);

  const duplicate = useCallback((id: string) => {
    const src = list.find(d => d.id === id);
    if (!src) return;
    const copy = seedDashboard(`${src.name} (copy)`, src.templateId);
    // Copy the source layout into the new dashboard's storage key.
    try {
      const raw = localStorage.getItem(src.storageKey);
      if (raw) localStorage.setItem(copy.storageKey, raw);
    } catch { /* best effort */ }
    setList(prev => {
      const next = [...prev, copy];
      persistIndex(next);
      return next;
    });
    setActiveId(copy.id);
  }, [list]);

  const remove = useCallback((id: string) => {
    setList(prev => {
      const target = prev.find(d => d.id === id);
      const next = prev.filter(d => d.id !== id);
      if (next.length === 0) {
        const main = seedDashboard('Main', 'trader');
        main.isDefault = true;
        next.push(main);
      }
      // If we removed the default, promote the first remaining.
      if (target?.isDefault && next.length > 0) next[0] = { ...next[0], isDefault: true };
      persistIndex(next);
      return next;
    });
    setActiveId(prev => {
      if (prev === id) {
        const remaining = list.filter(d => d.id !== id);
        return (remaining.find(d => d.isDefault) ?? remaining[0])?.id ?? null;
      }
      return prev;
    });
  }, [list]);

  const reset = useCallback((id: string) => {
    // Clear the stored layout for this dashboard so the next mount rebuilds
    // from its template. The workspace store's resetToDefault() is the primary
    // reset path from the UI; this is a belt-and-suspenders storage clear.
    const entry = list.find(d => d.id === id);
    if (entry) {
      try { localStorage.removeItem(entry.storageKey); } catch { /* best effort */ }
    }
  }, [list]);

  const setDefault = useCallback((id: string) => {
    setList(prev => {
      const next = prev.map(d => ({ ...d, isDefault: d.id === id }));
      persistIndex(next);
      return next;
    });
  }, []);

  const switchTo = useCallback((id: string) => setActiveId(id), []);

  /** Export the active dashboard's layout as a JSON string. */
  const exportLayout = useCallback((id: string): string | null => {
    const entry = list.find(d => d.id === id);
    if (!entry) return null;
    try {
      const raw = localStorage.getItem(entry.storageKey);
      if (!raw) return null;
      return JSON.stringify({ version: 1, name: entry.name, templateId: entry.templateId, layout: JSON.parse(raw) }, null, 2);
    } catch { return null; }
  }, [list]);

  /** Import a dashboard layout from a JSON string, creating a new dashboard. */
  const importLayout = useCallback((text: string): boolean => {
    try {
      const parsed = JSON.parse(text);
      const layout = parsed.layout ?? parsed;
      if (!layout || !Array.isArray(layout.sections)) return false;
      const name = typeof parsed.name === 'string' ? parsed.name : 'Imported';
      const entry = seedDashboard(name, typeof parsed.templateId === 'string' ? parsed.templateId : 'trader');
      localStorage.setItem(entry.storageKey, JSON.stringify(layout));
      setList(prev => {
        const next = [...prev, entry];
        persistIndex(next);
        return next;
      });
      setActiveId(entry.id);
      return true;
    } catch { return false; }
  }, []);

  return {
    list,
    active,
    activeId,
    loaded,
    create,
    rename,
    duplicate,
    remove,
    reset,
    setDefault,
    switchTo,
    exportLayout,
    importLayout,
  };
}

export { DASHBOARD_WIDGET_IDS, getDashboardTemplate };
