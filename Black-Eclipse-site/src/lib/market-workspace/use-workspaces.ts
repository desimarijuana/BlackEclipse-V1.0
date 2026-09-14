'use client';

// ── useWorkspaces — multiple named market workspaces ─────────────────────────
// Each workspace is a named entry with its own storageKey; the grid kernel
// keys stores by storageKey, so each gets an independent persisted layout.
// This manager owns the index (list / active id) plus CRUD: create, rename,
// duplicate, reset, remove.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { newPanelId } from './types';
import { defaultWorkspaceLayout } from './presets';

export interface WorkspaceEntry {
  id: string;
  name: string;
  storageKey: string;
  presetId: string;
}

const INDEX_KEY = 'be_market_workspaces_v1';
const ACTIVE_KEY = 'be_market_workspaces_active_v1';
const STORAGE_PREFIX = 'be_mws_layout_v1_';

function loadIndex(): WorkspaceEntry[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(INDEX_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((e): e is WorkspaceEntry =>
      e && typeof e.id === 'string' && typeof e.storageKey === 'string' && typeof e.name === 'string');
  } catch {
    return [];
  }
}

function persistIndex(list: WorkspaceEntry[]) {
  try { localStorage.setItem(INDEX_KEY, JSON.stringify(list)); } catch { /* best effort */ }
}

function loadActiveId(): string | null {
  if (typeof window === 'undefined') return null;
  try { return localStorage.getItem(ACTIVE_KEY); } catch { return null; }
}

function persistActiveId(id: string | null) {
  try {
    if (id) localStorage.setItem(ACTIVE_KEY, id);
    else localStorage.removeItem(ACTIVE_KEY);
  } catch { /* best effort */ }
}

function seedWorkspace(name: string, presetId: string): WorkspaceEntry {
  const id = newPanelId('mws');
  return { id, name, storageKey: `${STORAGE_PREFIX}${id}`, presetId };
}

export function useWorkspaces() {
  const [list, setList] = useState<WorkspaceEntry[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const activeIdRef = useRef<string | null>(null);
  activeIdRef.current = activeId;

  useEffect(() => {
    let existing = loadIndex();
    if (existing.length === 0) {
      const main = seedWorkspace('Trading Terminal', 'trading');
      existing = [main];
      persistIndex(existing);
    }
    setList(existing);
    const savedActive = loadActiveId();
    setActiveId(savedActive && existing.some(w => w.id === savedActive) ? savedActive : existing[0].id);
    setLoaded(true);
  }, []);

  const active = useMemo(() => list.find(w => w.id === activeId) ?? null, [list, activeId]);

  const setActive = useCallback((id: string) => {
    setActiveId(id);
    persistActiveId(id);
  }, []);

  const create = useCallback((name: string, presetId = 'trading') => {
    const entry = seedWorkspace(name || 'Untitled', presetId);
    setList(prev => { const next = [...prev, entry]; persistIndex(next); return next; });
    setActive(entry.id);
    return entry;
  }, [setActive]);

  const rename = useCallback((id: string, name: string) => {
    setList(prev => {
      const next = prev.map(w => (w.id === id ? { ...w, name: name || w.name } : w));
      persistIndex(next);
      return next;
    });
  }, []);

  const duplicate = useCallback((id: string) => {
    const src = list.find(w => w.id === id);
    if (!src) return;
    const copy = seedWorkspace(`${src.name} (copy)`, src.presetId);
    try {
      const raw = localStorage.getItem(src.storageKey);
      if (raw) localStorage.setItem(copy.storageKey, raw);
    } catch { /* best effort */ }
    setList(prev => { const next = [...prev, copy]; persistIndex(next); return next; });
    setActive(copy.id);
  }, [list, setActive]);

  const remove = useCallback((id: string) => {
    setList(prev => {
      const next = prev.filter(w => w.id !== id);
      if (next.length === 0) next.push(seedWorkspace('Trading Terminal', 'trading'));
      persistIndex(next);
      return next;
    });
    if (activeIdRef.current === id) {
      const remaining = list.filter(w => w.id !== id);
      setActive((remaining[0] ?? seedWorkspace('Trading Terminal', 'trading')).id);
    }
  }, [list, setActive]);

  /** Clear a workspace's stored layout so the next mount re-seeds the preset. */
  const clear = useCallback((id: string) => {
    const entry = list.find(w => w.id === id);
    if (entry) { try { localStorage.removeItem(entry.storageKey); } catch { /* best effort */ } }
  }, [list]);

  /** The default layout for the active workspace (unseeded → preset). */
  const defaultLayout = useMemo(() => defaultWorkspaceLayout(), []);

  return { list, active, activeId, loaded, defaultLayout, create, rename, duplicate, remove, clear, setActive };
}
