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

const INDEX_KEY = 'be_dashboards_index_v2';
const ONBOARDED_KEY = 'be_dashboards_onboarded_v1';

// Bump the storage prefix when the widget catalog changes so stale layouts
// (referencing removed widget ids) don't leave empty columns. A fresh default
// template loads instead.
export const DASHBOARD_STORAGE_PREFIX = 'be_ws_dashboard_v2_';

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
    const existing = loadIndex();
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
