'use client';

// ── useCustomize — the single hook a customizable page consumes (v2) ────────
// Wraps section-based layout state + persistence + pure ops for one page.

import { useCallback, useEffect, useState } from 'react';
import { defaultLayout, layoutFromPreset, type PageDefinition, type PageLayout, type ColumnCount } from './types';
import {
  addWidget, allWidgets, clearLayout, loadLayout, placeWidget, patched,
  removeWidget, saveLayout, setSectionColumns, nudged,
} from './layout';

export function useCustomize(def: PageDefinition) {
  const [layout, setLayout] = useState<PageLayout>(() => defaultLayout(def));
  // Hydrate from storage after mount (SSR-safe).
  useEffect(() => { setLayout(loadLayout(def)); }, [def]);

  const apply = useCallback((next: PageLayout) => {
    setLayout(next);
    saveLayout(def, next);
  }, [def]);

  const patch = useCallback((id: string, p: Parameters<typeof patched>[2]) => {
    setLayout((prev) => {
      const next = patched(prev, id, p);
      saveLayout(def, next);
      return next;
    });
  }, [def]);

  const place = useCallback((widgetId: string, sectionId: string, beforeId: string | null) => {
    setLayout((prev) => {
      const next = placeWidget(prev, widgetId, sectionId, beforeId);
      saveLayout(def, next);
      return next;
    });
  }, [def]);

  const setColumns = useCallback((sectionId: string, columns: ColumnCount) => {
    setLayout((prev) => {
      const next = setSectionColumns(prev, sectionId, columns);
      saveLayout(def, next);
      return next;
    });
  }, [def]);

  const add = useCallback((widgetId: string, sectionId: string | null) => {
    setLayout((prev) => {
      const next = addWidget(prev, def, widgetId, sectionId);
      saveLayout(def, next);
      return next;
    });
  }, [def]);

  const remove = useCallback((widgetId: string) => {
    setLayout((prev) => {
      const next = removeWidget(prev, widgetId);
      saveLayout(def, next);
      return next;
    });
  }, [def]);

  const nudge = useCallback((id: string, dir: -1 | 1) => {
    setLayout((prev) => {
      const next = nudged(prev, id, dir);
      saveLayout(def, next);
      return next;
    });
  }, [def]);

  const applyPreset = useCallback((presetId: string) => {
    const preset = def.presets.find((p) => p.id === presetId);
    if (preset) apply(layoutFromPreset(def, preset));
  }, [def, apply]);

  const reset = useCallback(() => {
    clearLayout(def);
    setLayout(defaultLayout(def));
  }, [def]);

  const widgets = allWidgets(layout);
  const visible = widgets.filter((w) => w.visible);
  return {
    layout, widgets, visible,
    patch, place, setColumns, add, remove, nudge,
    applyPreset, apply, reset,
  };
}