'use client';

// ── useWorkspace — the customization kernel hook ─────────────────────────────
// One hook per workspace instance (overview grid, each per-fund workspace…).
// Owns: layout state (loaded once from storage with corrupt guard), edit
// mode, and every mutation op — each op updates the tree AND persists
// immediately so rearrangements survive reload.

import { useCallback, useMemo, useState } from 'react';
import {
  addWidget as opAdd,
  moveWidget as opMove,
  removeWidget as opRemove,
  setColumnCount as opSetCount,
  setColumnWeight as opSetWeight,
  setWidgetHeight as opSetHeight,
  moveWidgetToNewSection as opMoveNewSection,
} from './ops';
import { clearWorkspace, loadWorkspace, saveWorkspace } from './persistence';
import { WORKSPACE_TEMPLATES, type WorkspaceTemplate } from './templates';
import type { DropTarget, WorkspaceLayout } from './types';

export interface UseWorkspaceOptions {
  /** localStorage key — unique per page/fund instance. */
  storageKey: string;
  defaultLayout: WorkspaceLayout;
  /** Registry ids this page understands; unknown stored widgets are dropped. */
  knownWidgetIds?: string[];
}

export function useWorkspace({ storageKey, defaultLayout, knownWidgetIds }: UseWorkspaceOptions) {
  const known = useMemo(
    () => (knownWidgetIds ? new Set(knownWidgetIds) : undefined),
    [knownWidgetIds],
  );
  const [initial] = useState(() => loadWorkspace(storageKey, defaultLayout, { knownWidgetIds: known }));
  const [corrupt, setCorrupt] = useState(initial.corrupt);
  const [layout, setLayout] = useState<WorkspaceLayout>(initial.layout);

  /** Commit a pure op: update the tree and persist immediately. */
  const commit = useCallback((next: WorkspaceLayout) => {
    setLayout(next);
    saveWorkspace(storageKey, next);
  }, [storageKey]);

  const addWidget = useCallback((widgetId: string, target?: DropTarget) => {
    commit(opAdd(layout, widgetId, target));
  }, [commit, layout]);

  const removeWidget = useCallback((widgetId: string) => {
    commit(opRemove(layout, widgetId));
  }, [commit, layout]);

  const moveWidget = useCallback((widgetId: string, target: DropTarget) => {
    commit(opMove(layout, widgetId, target));
  }, [commit, layout]);

  const moveWidgetToNewSection = useCallback((widgetId: string) => {
    commit(opMoveNewSection(layout, widgetId));
  }, [commit, layout]);

  const setColumnCount = useCallback((sectionId: string, count: number) => {
    commit(opSetCount(layout, sectionId, count));
  }, [commit, layout]);

  const setColumnWeight = useCallback((columnId: string, weight: number) => {
    commit(opSetWeight(layout, columnId, weight));
  }, [commit, layout]);

  const setWidgetHeight = useCallback((widgetId: string, height: number | null) => {
    commit(opSetHeight(layout, widgetId, height));
  }, [commit, layout]);

  const applyTemplate = useCallback((template: WorkspaceTemplate) => {
    commit(template.build(knownWidgetIds ?? []));
  }, [commit, knownWidgetIds]);

  const resetToDefault = useCallback(() => {
    clearWorkspace(storageKey);
    setCorrupt(false);
    commit(defaultLayout);
  }, [commit, defaultLayout, storageKey]);

  const [editMode, setEditMode] = useState(false);

  return {
    layout,
    editMode,
    setEditMode,
    /** True when the stored layout was corrupt and defaults were shown instead. */
    corrupt,
    templates: WORKSPACE_TEMPLATES,
    ops: {
      addWidget,
      removeWidget,
      moveWidget,
      moveWidgetToNewSection,
      setColumnCount,
      setColumnWeight,
      setWidgetHeight,
      applyTemplate,
      resetToDefault,
    },
  };
}

export type WorkspaceController = ReturnType<typeof useWorkspace>;
