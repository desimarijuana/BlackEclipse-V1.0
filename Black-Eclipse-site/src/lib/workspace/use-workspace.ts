'use client';

// ── useWorkspace — the customization kernel hook ─────────────────────────────
// Zustand store per workspace instance (overview grid, each per-fund
// workspace…). Owns: layout state (loaded once from storage with corrupt
// guard), edit mode, selection state, and every mutation op — each op runs an
// Immer producer on the layout tree AND persists immediately so
// rearrangements survive reload.

import { useMemo } from 'react';
import { create } from 'zustand';
import { produce } from 'immer';
import {
  addWidget as addWidgetDraft,
  moveWidget as moveWidgetDraft,
  removeWidget as removeWidgetDraft,
  setColumnCount as setColumnCountDraft,
  setColumnWeight as setColumnWeightDraft,
  setWidgetHeight as setWidgetHeightDraft,
  setWidgetConfig as setWidgetConfigDraft,
  toggleWidgetHidden as toggleWidgetHiddenDraft,
  duplicateWidget as duplicateWidgetDraft,
  moveWidgetToAdjacentColumn as moveWidgetToAdjacentColumnDraft,
  moveWidgetToNewSection as moveWidgetToNewSectionDraft,
  moveWidgetToNewSectionAt as moveWidgetToNewSectionAtDraft,
  createSectionAt as createSectionAtDraft,
  removeSection as removeSectionDraft,
  addWidgetToNewSectionAt as addWidgetToNewSectionAtDraft,
  locate,
} from './ops';
import { clearWorkspace, loadWorkspace, saveWorkspace } from './persistence';
import { WORKSPACE_TEMPLATES, type WorkspaceTemplate } from './templates';
import type { DropTarget, WidgetPlacement, WorkspaceLayout } from './types';

export interface UseWorkspaceOptions {
  /** localStorage key — unique per page/fund instance. */
  storageKey: string;
  defaultLayout: WorkspaceLayout;
  /** Registry ids this page understands; unknown stored widgets are dropped. */
  knownWidgetIds?: string[];
}

interface WorkspaceState {
  layout: WorkspaceLayout;
  corrupt: boolean;
  editMode: boolean;
  /** Currently selected (last-tapped) widget card, for editor UIs. */
  selectedWidgetId: string | null;
  /** True while any card is being dragged (drives drop-zone affordances). */
  dragging: boolean;
}

interface WorkspaceActions {
  commit: (recipe: (draft: WorkspaceLayout) => void) => void;
  addWidget: (widgetId: string, target?: DropTarget) => void;
  removeWidget: (widgetId: string) => void;
  moveWidget: (widgetId: string, target: DropTarget) => void;
  moveWidgetToNewSection: (widgetId: string) => void;
  moveWidgetToNewSectionAt: (widgetId: string, anchorSectionId: string, position: 'above' | 'below') => void;
  createSectionAt: (anchorSectionId: string, position: 'above' | 'below') => void;
  removeSection: (sectionId: string) => void;
  addWidgetToNewSectionAt: (widgetId: string, anchorSectionId: string, position: 'above' | 'below') => void;
  setColumnCount: (sectionId: string, count: number) => void;
  setColumnWeight: (columnId: string, weight: number) => void;
  setWidgetHeight: (widgetId: string, height: number | null) => void;
  setWidgetConfig: (widgetId: string, patch: Record<string, unknown>) => void;
  toggleWidgetHidden: (widgetId: string) => void;
  duplicateWidget: (widgetId: string) => void;
  moveWidgetToAdjacentColumn: (widgetId: string, direction: 'left' | 'right') => void;
  applyTemplate: (template: WorkspaceTemplate) => void;
  resetToDefault: () => void;
  setEditMode: (on: boolean) => void;
  selectWidget: (widgetId: string | null) => void;
  setDragging: (on: boolean) => void;
}

export type WorkspaceStore = WorkspaceState & WorkspaceActions;

function makeWorkspaceStore({ storageKey, defaultLayout, knownWidgetIds }: UseWorkspaceOptions) {
  const known = knownWidgetIds ? new Set(knownWidgetIds) : undefined;
  const initial = loadWorkspace(storageKey, defaultLayout, { knownWidgetIds: known });

  return create<WorkspaceStore>()((set, get) => {
    const commit = (recipe: (draft: WorkspaceLayout) => void) => {
      set(state => ({ layout: produce(state.layout, recipe) }));
      saveWorkspace(storageKey, get().layout);
    };

    return {
      layout: initial.layout,
      corrupt: initial.corrupt,
      editMode: false,
      selectedWidgetId: null,
      dragging: false,

      commit,
      addWidget: (widgetId, target) => commit(d => { addWidgetDraft(d, widgetId, target); }),
      removeWidget: (widgetId) => commit(d => { removeWidgetDraft(d, widgetId); }),
      moveWidget: (widgetId, target) => commit(d => { moveWidgetDraft(d, widgetId, target); }),
      moveWidgetToNewSection: (widgetId) => commit(d => { moveWidgetToNewSectionDraft(d, widgetId); }),
      moveWidgetToNewSectionAt: (widgetId, anchorSectionId, position) => commit(d => { moveWidgetToNewSectionAtDraft(d, widgetId, anchorSectionId, position); }),
      createSectionAt: (anchorSectionId, position) => commit(d => { createSectionAtDraft(d, anchorSectionId, position); }),
      removeSection: (sectionId) => commit(d => { removeSectionDraft(d, sectionId); }),
      addWidgetToNewSectionAt: (widgetId, anchorSectionId, position) => commit(d => { addWidgetToNewSectionAtDraft(d, widgetId, anchorSectionId, position); }),
      setColumnCount: (sectionId, count) => commit(d => { setColumnCountDraft(d, sectionId, count); }),
      setColumnWeight: (columnId, weight) => commit(d => { setColumnWeightDraft(d, columnId, weight); }),
      setWidgetHeight: (widgetId, height) => commit(d => { setWidgetHeightDraft(d, widgetId, height); }),
      setWidgetConfig: (widgetId, patch) => commit(d => { setWidgetConfigDraft(d, widgetId, patch); }),
      toggleWidgetHidden: (widgetId) => commit(d => { toggleWidgetHiddenDraft(d, widgetId); }),
      duplicateWidget: (widgetId) => commit(d => { duplicateWidgetDraft(d, widgetId); }),
      moveWidgetToAdjacentColumn: (widgetId, direction) => commit(d => { moveWidgetToAdjacentColumnDraft(d, widgetId, direction); }),
      applyTemplate: (template) => {
        clearWorkspace(storageKey);
        set({ layout: template.build(knownWidgetIds ?? []) });
        saveWorkspace(storageKey, get().layout);
      },
      resetToDefault: () => {
        clearWorkspace(storageKey);
        set({ layout: defaultLayout, corrupt: false });
        saveWorkspace(storageKey, get().layout);
      },
      setEditMode: (on) => set({ editMode: on, selectedWidgetId: on ? get().selectedWidgetId : null }),
      selectWidget: (widgetId) => set({ selectedWidgetId: widgetId }),
      setDragging: (on) => set({ dragging: on }),
    };
  });
}

const storeCache = new Map<string, ReturnType<typeof makeWorkspaceStore>>();

/** One shared store per storageKey so layout persists across mounts. */
export function useWorkspace(options: UseWorkspaceOptions) {
  const useStore = useMemo(() => {
    let s = storeCache.get(options.storageKey);
    if (!s) {
      s = makeWorkspaceStore(options);
      storeCache.set(options.storageKey, s);
    }
    return s;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- store is keyed by storageKey; defaults only seed creation
  }, [options.storageKey]);
  const layout = useStore(s => s.layout);
  const editMode = useStore(s => s.editMode);
  const corrupt = useStore(s => s.corrupt);
  const selectedWidgetId = useStore(s => s.selectedWidgetId);
  const dragging = useStore(s => s.dragging);
  const selected = useMemo(
    () => (selectedWidgetId ? locate(layout, selectedWidgetId)?.widget ?? null : null),
    [layout, selectedWidgetId],
  );

  return {
    layout,
    editMode,
    setEditMode: useStore.getState().setEditMode,
    corrupt,
    dragging,
    selectedWidgetId,
    selected,
    templates: WORKSPACE_TEMPLATES,
    ops: {
      addWidget: useStore.getState().addWidget,
      removeWidget: useStore.getState().removeWidget,
      moveWidget: useStore.getState().moveWidget,
      moveWidgetToNewSection: useStore.getState().moveWidgetToNewSection,
      moveWidgetToNewSectionAt: useStore.getState().moveWidgetToNewSectionAt,
      createSectionAt: useStore.getState().createSectionAt,
      removeSection: useStore.getState().removeSection,
      addWidgetToNewSectionAt: useStore.getState().addWidgetToNewSectionAt,
      setColumnCount: useStore.getState().setColumnCount,
      setColumnWeight: useStore.getState().setColumnWeight,
      setWidgetHeight: useStore.getState().setWidgetHeight,
      setWidgetConfig: useStore.getState().setWidgetConfig,
      toggleWidgetHidden: useStore.getState().toggleWidgetHidden,
      duplicateWidget: useStore.getState().duplicateWidget,
      moveWidgetToAdjacentColumn: useStore.getState().moveWidgetToAdjacentColumn,
      applyTemplate: useStore.getState().applyTemplate,
      resetToDefault: useStore.getState().resetToDefault,
      selectWidget: useStore.getState().selectWidget,
      setDragging: useStore.getState().setDragging,
    },
  };
}

/** Widget placement lookup used by the canvas for dnd ids. */
export function findPlacement(layout: WorkspaceLayout, id: string): WidgetPlacement | null {
  return locate(layout, id)?.widget ?? null;
}

export type WorkspaceController = ReturnType<typeof useWorkspace>;