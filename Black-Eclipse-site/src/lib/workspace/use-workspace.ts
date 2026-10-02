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
import { newId } from './types';
import type { PlacementSizing } from './ops';
import {
  addWidget as addWidgetDraft,
  moveWidget as moveWidgetDraft,
  removeWidget as removeWidgetDraft,
  setColumnCount as setColumnCountDraft,
  setColumnWeight as setColumnWeightDraft,
  setColumnWeights as setColumnWeightsDraft,
  setWidgetHeight as setWidgetHeightDraft,
  setWidgetConfig as setWidgetConfigDraft,
  toggleWidgetHidden as toggleWidgetHiddenDraft,
  duplicateWidget as duplicateWidgetDraft,
  moveWidgetToAdjacentColumn as moveWidgetToAdjacentColumnDraft,
  moveWidgetToNewSection as moveWidgetToNewSectionDraft,
  moveWidgetToNewSectionAt as moveWidgetToNewSectionAtDraft,
  addWidgetToNewSection as addWidgetToNewSectionDraft,
  createSectionAt as createSectionAtDraft,
  removeSection as removeSectionDraft,
  createSectionInZone as createSectionInZoneDraft,
  addWidgetToNewSectionAt as addWidgetToNewSectionAtDraft,
  setZoneHidden as setZoneHiddenDraft,
  setZoneWidth as setZoneWidthDraft,
  cloneLayout,
  locate,
} from './ops';
import { clearWorkspace, loadWorkspace, saveWorkspace } from './persistence';
import { WORKSPACE_TEMPLATES, type WorkspaceTemplate } from './templates';
import type { DropTarget, WidgetPlacement, WorkspaceLayout, WorkspaceZone } from './types';

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
  addWidget: (widgetId: string, target?: DropTarget, sizing?: PlacementSizing) => void;
  removeWidget: (widgetId: string) => void;
  moveWidget: (widgetId: string, target: DropTarget) => void;
  moveWidgetToNewSection: (widgetId: string) => void;
  moveWidgetToNewSectionAt: (widgetId: string, anchorSectionId: string, position: 'above' | 'below') => void;
  addWidgetToNewSection: (widgetId: string, zone?: WorkspaceZone, sizing?: PlacementSizing) => void;
  createSectionAt: (anchorSectionId: string, position: 'above' | 'below') => void;
  removeSection: (sectionId: string) => void;
  createSectionInZone: (zone: WorkspaceZone) => void;
  /** Hide/show a whole side zone (keeps its sections for later restore). */
  setZoneHidden: (zone: WorkspaceZone, hidden: boolean) => void;
  /** Set a side zone's width in px (null = reset to default). */
  setZoneWidth: (zone: WorkspaceZone, width: number | null) => void;
  addWidgetToNewSectionAt: (widgetId: string, anchorSectionId: string, position: 'above' | 'below', sizing?: PlacementSizing) => void;
  setColumnCount: (sectionId: string, count: number) => void;
  setColumnWeight: (columnId: string, weight: number) => void;
  setColumnWeights: (sectionId: string, updates: ReadonlyArray<{ columnId: string; weight: number }>) => void;
  setWidgetHeight: (widgetId: string, height: number | null) => void;
  setWidgetConfig: (widgetId: string, patch: Record<string, unknown>) => void;
  toggleWidgetHidden: (widgetId: string) => void;
  duplicateWidget: (widgetId: string) => void;
  moveWidgetToAdjacentColumn: (widgetId: string, direction: 'left' | 'right') => void;
  applyTemplate: (template: WorkspaceTemplate) => void;
  resetToDefault: () => void;
  setEditMode: (on: boolean) => void;
  /**
   * Flip edit mode using the STORE's current value (not a render-time closure).
   * A handler that does `setEditMode(!workspace.editMode)` can act on a stale
   * value when two toggles land before a re-render, leaving the user stuck in
   * edit mode — this reads `get()` at call time instead.
   */
  toggleEditMode: () => void;
  selectWidget: (widgetId: string | null) => void;
  setDragging: (on: boolean) => void;
}

export type WorkspaceStore = WorkspaceState & WorkspaceActions;

function makeWorkspaceStore({ storageKey, defaultLayout, knownWidgetIds }: UseWorkspaceOptions) {
  const known = knownWidgetIds ? new Set(knownWidgetIds) : undefined;
  const initial = loadWorkspace(storageKey, defaultLayout, { knownWidgetIds: known });

  // Blank-layout self-heal: a stored layout with NO widgets at all while the
  // defaults DO have widgets is the residue of a build that failed to resolve a
  // template. Restore the defaults rather than show an empty board. (A user who
  // deliberately empties a workspace has no saved payload, so this never fights
  // that state.) Storage was bumped to v8 for the persona-rename break, so this
  // is a belt-and-suspenders guard for any future resolver failure.
  const storedWidgetCount = initial.layout.sections
    .reduce((a, s) => a + s.columns.reduce((b, c) => b + c.widgets.length, 0), 0);
  const defaultWidgetCount = defaultLayout.sections
    .reduce((a, s) => a + s.columns.reduce((b, c) => b + c.widgets.length, 0), 0);
  if (!initial.corrupt && storedWidgetCount === 0 && defaultWidgetCount > 0) {
    initial.layout = cloneLayout(defaultLayout);
    saveWorkspace(storageKey, initial.layout);
  }

  // One-time side-zone migration: when the default layout declares `left` /
  // `right` sections but a stored layout (from before that zone existed) has
  // none, append the defaults (with their widgets) so an existing dashboard
  // gains the side columns without losing its centre arrangement. Persisted
  // immediately so it runs once. No-op for single-zone pages (fund workspaces)
  // whose defaults have no side zones.
  const sideZones = (['left', 'right'] as const).filter(z =>
    defaultLayout.sections.some(s => s.zone === z)
    && !initial.layout.sections.some(s => s.zone === z),
  );
  if (!initial.corrupt && sideZones.length > 0) {
    const appended = sideZones.flatMap(zone =>
      defaultLayout.sections
        .filter(s => s.zone === zone)
        .map(s => ({
          id: newId('sec'),
          zone,
          columns: s.columns.map(c => ({
            id: newId('col'),
            weight: c.weight,
            widgets: c.widgets.map(w => ({ ...w, id: newId('wid') })),
          })),
        })),
    );
    initial.layout = { version: 1, sections: [...initial.layout.sections, ...appended] };
    saveWorkspace(storageKey, initial.layout);
  }

  return create<WorkspaceStore>()((set, get) => {
    const commit = (recipe: (draft: WorkspaceLayout) => void) => {
      // NOTE: masonry packing runs at COMPOSE time (defaults/templates/reset),
      // never here. Re-packing on every edit would silently reshuffle cards the
      // user just arranged (masonry has no stable fixed point for equal-height
      // cards), so a drag commits exactly where it was dropped. Content-driven
      // heights keep live layouts gap-free without re-packing.
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
      addWidget: (widgetId, target, sizing) => commit(d => { addWidgetDraft(d, widgetId, target, sizing); }),
      removeWidget: (widgetId) => commit(d => { removeWidgetDraft(d, widgetId); }),
      moveWidget: (widgetId, target) => commit(d => { moveWidgetDraft(d, widgetId, target); }),
      moveWidgetToNewSection: (widgetId) => commit(d => { moveWidgetToNewSectionDraft(d, widgetId); }),
      moveWidgetToNewSectionAt: (widgetId, anchorSectionId, position) => commit(d => { moveWidgetToNewSectionAtDraft(d, widgetId, anchorSectionId, position); }),
      addWidgetToNewSection: (widgetId, zone, sizing) => commit(d => { addWidgetToNewSectionDraft(d, widgetId, zone, sizing); }),
      createSectionAt: (anchorSectionId, position) => commit(d => { createSectionAtDraft(d, anchorSectionId, position); }),
      removeSection: (sectionId) => commit(d => { removeSectionDraft(d, sectionId); }),
      createSectionInZone: (zone) => commit(d => { createSectionInZoneDraft(d, zone); }),
      setZoneHidden: (zone, hidden) => commit(d => { setZoneHiddenDraft(d, zone, hidden); }),
      setZoneWidth: (zone, width) => commit(d => { setZoneWidthDraft(d, zone, width); }),
      addWidgetToNewSectionAt: (widgetId, anchorSectionId, position, sizing) => commit(d => { addWidgetToNewSectionAtDraft(d, widgetId, anchorSectionId, position, sizing); }),
      setColumnCount: (sectionId, count) => commit(d => { setColumnCountDraft(d, sectionId, count); }),
      setColumnWeight: (columnId, weight) => commit(d => { setColumnWeightDraft(d, columnId, weight); }),
      setColumnWeights: (sectionId, updates) => commit(d => { setColumnWeightsDraft(d, sectionId, updates); }),
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
      toggleEditMode: () => {
        const on = !get().editMode;
        set({ editMode: on, selectedWidgetId: on ? get().selectedWidgetId : null });
      },
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
    toggleEditMode: useStore.getState().toggleEditMode,
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
      addWidgetToNewSection: useStore.getState().addWidgetToNewSection,
      createSectionAt: useStore.getState().createSectionAt,
      removeSection: useStore.getState().removeSection,
      createSectionInZone: useStore.getState().createSectionInZone,
      setZoneHidden: useStore.getState().setZoneHidden,
      setZoneWidth: useStore.getState().setZoneWidth,
      addWidgetToNewSectionAt: useStore.getState().addWidgetToNewSectionAt,
      setColumnCount: useStore.getState().setColumnCount,
      setColumnWeight: useStore.getState().setColumnWeight,
      setColumnWeights: useStore.getState().setColumnWeights,
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