'use client';

// ── useCustomize — the single hook a customizable page consumes (v3) ────────
// Wraps Section → Column → Element layout state + persistence + pure ops.

import { useCallback, useEffect, useState } from 'react';
import { defaultLayout, layoutFromPreset, type ElementStyle, type PageDefinition, type PageLayout, type Section } from './types';
import {
  addElement, allElements, clearLayout, loadLayout, placeElement, patched,
  patchSection, removeElement, saveLayout, setColumnCount, setColumnWidth, nudged,
} from './layout';

export function useCustomize(def: PageDefinition) {
  const [layout, setLayout] = useState<PageLayout>(() => defaultLayout(def));
  useEffect(() => { setLayout(loadLayout(def)); }, [def]);

  const apply = useCallback((next: PageLayout) => {
    setLayout(next);
    saveLayout(def, next);
  }, [def]);

  /** Patch an element: visibility and/or per-element style. */
  const patch = useCallback((id: string, p: { visible?: boolean; style?: Partial<ElementStyle> }) => {
    setLayout((prev) => {
      const next = patched(prev, id, p);
      saveLayout(def, next);
      return next;
    });
  }, [def]);

  /** Patch section-level layout styling (gap/padding). */
  const patchSec = useCallback((sectionId: string, p: Partial<Pick<Section, 'gap' | 'padding'>>) => {
    setLayout((prev) => {
      const next = patchSection(prev, sectionId, p);
      saveLayout(def, next);
      return next;
    });
  }, [def]);

  /** Drop an element at section/column/element position (drag & drop core). */
  const place = useCallback((elementId: string, target: { sectionId: string; columnId: string; elementIdx: number | null }) => {
    setLayout((prev) => {
      const next = placeElement(prev, elementId, target);
      saveLayout(def, next);
      return next;
    });
  }, [def]);

  const setColumns = useCallback((sectionId: string, count: 1 | 2 | 3 | 4) => {
    setLayout((prev) => {
      const next = setColumnCount(prev, sectionId, count);
      saveLayout(def, next);
      return next;
    });
  }, [def]);

  const setColWidth = useCallback((columnId: string, width: 1 | 2 | 3 | 4) => {
    setLayout((prev) => {
      const next = setColumnWidth(prev, columnId, width);
      saveLayout(def, next);
      return next;
    });
  }, [def]);

  const add = useCallback((widgetId: string, columnId: string | null) => {
    setLayout((prev) => {
      const next = addElement(prev, def, widgetId, columnId);
      saveLayout(def, next);
      return next;
    });
  }, [def]);

  const remove = useCallback((elementId: string) => {
    setLayout((prev) => {
      const next = removeElement(prev, elementId);
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

  const widgets = allElements(layout);
  const visible = widgets.filter((w) => w.visible);
  return {
    layout, widgets, visible,
    patch, patchSec, place, setColumns, setColWidth, add, remove, nudge,
    applyPreset, apply, reset,
  };
}