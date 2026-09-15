'use client';

// ── useMarketWorkspace — the grid customization kernel ───────────────────────
// Zustand store per workspace instance. Owns layout state (loaded once from
// storage with a corrupt-read guard), edit mode, panel selection, the
// full-viewport / chart-fullscreen modes, and every mutation op — each op runs
// an Immer producer on the layout tree AND persists immediately.

import { useMemo } from 'react';
import { create } from 'zustand';
import { produce } from 'immer';
import {
  addPanel as addPanelDraft,
  applyGridPreset as applyGridPresetDraft,
  autoArrange as autoArrangeDraft,
  duplicatePanel as duplicatePanelDraft,
  placePanel as placePanelDraft,
  removePanel as removePanelDraft,
  setPanelChart as setPanelChartDraft,
  setPanelConfig as setPanelConfigDraft,
  setPanelLink as setPanelLinkDraft,
  setPanelRect as setPanelRectDraft,
  setPanelSymbol as setPanelSymbolDraft,
  togglePanelAi as togglePanelAiDraft,
} from './ops';
import { cloneLayout, normalizeLayout } from './ops';
import { clearWorkspace, loadWorkspace, saveWorkspace } from './persistence';
import type { MarketPanel, MarketPanelType, MarketWorkspaceLayout, PanelRect } from './types';

export interface UseMarketWorkspaceOptions {
  storageKey: string;
  defaultLayout: MarketWorkspaceLayout;
}

interface MarketWorkspaceState {
  layout: MarketWorkspaceLayout;
  corrupt: boolean;
  /** Layout-edit mode — reveals panel drag/resize chrome. */
  editMode: boolean;
  /** Panel being dragged/resized. */
  activePanelId: string | null;
  /** Panel focused full-viewport (chart fullscreen). */
  focusedPanelId: string | null;
  /** Whole-workspace full-page mode (global nav hidden). */
  fullPage: boolean;
  /** True while a panel drag is in flight (drives grid affordances). */
  dragging: boolean;
}

interface MarketWorkspaceActions {
  commit: (recipe: (draft: MarketWorkspaceLayout) => void) => void;
  addPanel: (type: MarketPanelType, rect?: PanelRect, seed?: { symbol?: string; market?: string }) => void;
  removePanel: (id: string) => void;
  duplicatePanel: (id: string) => void;
  setPanelRect: (id: string, rect: PanelRect) => void;
  /** Absolute-placement drag commit (keeps the panel where it was dropped). */
  placePanel: (id: string, col: number, row: number) => void;
  setPanelChart: (id: string, chart: MarketPanel['chart']) => void;
  setPanelSymbol: (id: string, symbol: string, market?: string) => void;
  setPanelLink: (id: string, link: MarketPanel['link']) => void;
  setPanelConfig: (id: string, patch: Record<string, unknown>) => void;
  togglePanelAi: (id: string) => void;
  applyGridPreset: (layoutId: string) => void;
  autoArrange: () => void;
  replaceLayout: (layout: MarketWorkspaceLayout) => void;
  setEditMode: (on: boolean) => void;
  setActivePanel: (id: string | null) => void;
  setFocusedPanel: (id: string | null) => void;
  setFullPage: (on: boolean) => void;
  setDragging: (on: boolean) => void;
}

export type MarketWorkspaceStore = MarketWorkspaceState & MarketWorkspaceActions;

function makeStore({ storageKey, defaultLayout }: UseMarketWorkspaceOptions) {
  const initial = loadWorkspace(storageKey, defaultLayout);

  return create<MarketWorkspaceStore>()((set, get) => {
    const commit = (recipe: (draft: MarketWorkspaceLayout) => void) => {
      const next = produce(get().layout, recipe);
      set({ layout: next });
      saveWorkspace(storageKey, next);
    };

    return {
      layout: initial.layout,
      corrupt: initial.corrupt,
      editMode: false,
      activePanelId: null,
      focusedPanelId: null,
      fullPage: false,
      dragging: false,

      commit,
      addPanel: (type, rect, seed) => commit(d => { addPanelDraft(d, type, rect, seed); }),
      removePanel: (id) => commit(d => { removePanelDraft(d, id); }),
      duplicatePanel: (id) => commit(d => { duplicatePanelDraft(d, id); }),
      setPanelRect: (id, rect) => commit(d => { setPanelRectDraft(d, id, rect); }),
      placePanel: (id, col, row) => commit(d => { placePanelDraft(d, id, col, row); }),
      setPanelChart: (id, chart) => commit(d => { setPanelChartDraft(d, id, chart); }),
      setPanelSymbol: (id, symbol, market) => commit(d => { setPanelSymbolDraft(d, id, symbol, market); }),
      setPanelLink: (id, link) => commit(d => { setPanelLinkDraft(d, id, link); }),
      setPanelConfig: (id, patch) => commit(d => { setPanelConfigDraft(d, id, patch); }),
      togglePanelAi: (id) => commit(d => { togglePanelAiDraft(d, id); }),
      applyGridPreset: (layoutId) => commit(d => { applyGridPresetDraft(d, layoutId); }),
      autoArrange: () => commit(d => { autoArrangeDraft(d); }),
      replaceLayout: (layout) => {
        const clean = normalizeLayout(layout) ?? cloneLayout(layout);
        clearWorkspace(storageKey);
        set({ layout: clean, corrupt: false, activePanelId: null, focusedPanelId: null });
        saveWorkspace(storageKey, clean);
      },
      setEditMode: (on) => set({ editMode: on, activePanelId: on ? get().activePanelId : null }),
      setActivePanel: (id) => set({ activePanelId: id }),
      setFocusedPanel: (id) => set({ focusedPanelId: id }),
      setFullPage: (on) => set({ fullPage: on, focusedPanelId: on ? get().focusedPanelId : null }),
      setDragging: (on) => set({ dragging: on }),
    };
  });
}

const storeCache = new Map<string, ReturnType<typeof makeStore>>();

export function useMarketWorkspace(options: UseMarketWorkspaceOptions) {
  const useStore = useMemo(() => {
    let s = storeCache.get(options.storageKey);
    if (!s) {
      s = makeStore(options);
      storeCache.set(options.storageKey, s);
    }
    return s;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- store keyed by storageKey; defaults only seed creation
  }, [options.storageKey]);

  const layout = useStore(s => s.layout);
  const editMode = useStore(s => s.editMode);
  const corrupt = useStore(s => s.corrupt);
  const activePanelId = useStore(s => s.activePanelId);
  const focusedPanelId = useStore(s => s.focusedPanelId);
  const fullPage = useStore(s => s.fullPage);
  const dragging = useStore(s => s.dragging);

  const activePanel = useMemo(
    () => (activePanelId ? layout.panels.find(p => p.id === activePanelId) ?? null : null),
    [layout, activePanelId],
  );

  const ops = useStore.getState();

  return {
    layout,
    editMode,
    corrupt,
    activePanelId,
    activePanel,
    focusedPanelId,
    fullPage,
    dragging,
    ops: {
      addPanel: ops.addPanel,
      removePanel: ops.removePanel,
      duplicatePanel: ops.duplicatePanel,
      setPanelRect: ops.setPanelRect,
      placePanel: ops.placePanel,
      setPanelChart: ops.setPanelChart,
      setPanelSymbol: ops.setPanelSymbol,
      setPanelLink: ops.setPanelLink,
      setPanelConfig: ops.setPanelConfig,
      togglePanelAi: ops.togglePanelAi,
      applyGridPreset: ops.applyGridPreset,
      autoArrange: ops.autoArrange,
      replaceLayout: ops.replaceLayout,
      setEditMode: ops.setEditMode,
      setActivePanel: ops.setActivePanel,
      setFocusedPanel: ops.setFocusedPanel,
      setFullPage: ops.setFullPage,
      setDragging: ops.setDragging,
    },
  };
}

export type MarketWorkspaceController = ReturnType<typeof useMarketWorkspace>;

/** True when a panel type is a chart (renders OHLC data). */
export function isChartPanel(panel: MarketPanel): boolean {
  return panel.type === 'chart';
}
