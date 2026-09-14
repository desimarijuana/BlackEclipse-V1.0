'use client';

// ── MarketWorkspace — the multi-chart trading terminal ───────────────────────
// Composes the grid kernel (useMarketWorkspace) with the panel components and
// the global toolbar. Responsibilities:
//   • render panels on a CSS grid (span-aware, free resize)
//   • panel move/resize in Customize mode
//   • layout presets, auto-arrange, add/duplicate/remove panels
//   • linked charts (symbol / timeframe / crosshair / range)
//   • full-page mode + single-chart fullscreen
//   • keyboard shortcuts
//   • workspace CRUD + persistence (via the kernel, already automatic)

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Maximize2, Minimize2, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useMarketWorkspace, type MarketWorkspaceController } from '@/lib/market-workspace/use-market-workspace';
import { useWorkspaces } from '@/lib/market-workspace/use-workspaces';
import { getWorkspacePreset } from '@/lib/market-workspace/presets';
import {
  clampRect, GRID_COLUMNS, MIN_PANEL_COLS, MIN_PANEL_ROWS, rectsOverlap,
  type ChartLink, type MarketPanel, type MarketPanelType, type PanelRect,
} from '@/lib/market-workspace/types';
import type { ChartState } from '@/lib/chart/types';
import { ChartPanel } from './chart-panel';
import { PanelContent } from './panel-content';
import { PanelToolbar } from './panel-toolbar';

/** Panels whose content needs a header with symbol controls. */
const CHART_LIKE = new Set<MarketPanelType>(['chart']);

export interface MarketWorkspaceProps {
  className?: string;
  /** Called when the user exits full-page mode (e.g. to restore global nav). */
  onRequestExitFullPage?: () => void;
  /** Hide the toolbar when embedded (the host renders its own chrome). */
  embedded?: boolean;
}

export function MarketWorkspace({ className, onRequestExitFullPage, embedded = false }: MarketWorkspaceProps) {
  const workspaces = useWorkspaces();
  const storageKey = workspaces.active?.storageKey ?? 'be_mws_layout_v1_pending';
  const workspace = useMarketWorkspace({ storageKey, defaultLayout: workspaces.defaultLayout });

  const { layout, editMode, activePanelId, focusedPanelId, fullPage, ops } = workspace;
  const gridRef = useRef<HTMLDivElement>(null);
  const [cellSize, setCellSize] = useState({ w: 100, h: 100 });
  const [savedAt, setSavedAt] = useState<number | null>(null);

  // Grid track sizing: presets use equal tracks; custom uses a fixed row height
  // so panels resize freely without collapsing rows.
  const isCustom = layout.layoutId === 'custom';

  // Measure the grid so pointer drags convert px → grid units.
  useEffect(() => {
    const el = gridRef.current;
    if (!el) return;
    const measure = () => {
      const rect = el.getBoundingClientRect();
      setCellSize({ w: rect.width / GRID_COLUMNS, h: isCustom ? 140 : rect.height / Math.max(1, layout.rows) });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [layout.rows, isCustom, fullPage]);

  // ── Panel drag / resize ────────────────────────────────────────────────────
  // Drag moves a panel by whole grid cells; resize adjusts its span. Both are
  // committed on pointer-up through the kernel (which re-flows overlaps).
  const dragRef = useRef<{
    mode: 'move' | 'resize';
    id: string;
    startX: number; startY: number;
    startRect: PanelRect;
  } | null>(null);
  const [preview, setPreview] = useState<{ id: string; rect: PanelRect } | null>(null);

  const onGridPointerDown = useCallback((panel: MarketPanel, mode: 'move' | 'resize') => (e: React.PointerEvent) => {
    if (!editMode) return;
    e.preventDefault();
    e.stopPropagation();
    ops.setActivePanel(panel.id);
    dragRef.current = { mode, id: panel.id, startX: e.clientX, startY: e.clientY, startRect: { ...panel.rect } };
    document.body.style.userSelect = 'none';

    const onMove = (ev: PointerEvent) => {
      const d = dragRef.current;
      if (!d) return;
      const dCols = Math.round((ev.clientX - d.startX) / cellSize.w);
      const dRows = Math.round((ev.clientY - d.startY) / cellSize.h);
      let rect: PanelRect;
      if (d.mode === 'move') {
        rect = { ...d.startRect, col: d.startRect.col + dCols, row: d.startRect.row + dRows };
      } else {
        rect = {
          ...d.startRect,
          colSpan: Math.max(MIN_PANEL_COLS, d.startRect.colSpan + dCols),
          rowSpan: Math.max(MIN_PANEL_ROWS, d.startRect.rowSpan + dRows),
        };
      }
      setPreview({ id: d.id, rect: clampRect(rect, Math.max(layout.rows + 4, 24)) });
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      document.body.style.userSelect = '';
      const d = dragRef.current;
      dragRef.current = null;
      const p = previewRef.current;
      setPreview(null);
      if (d && p && p.id === d.id) ops.setPanelRect(d.id, p.rect);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [editMode, cellSize, layout.rows, ops]);

  const previewRef = useRef(preview);
  previewRef.current = preview;

  // ── Panel CRUD / layout ────────────────────────────────────────────────────
  const addPanel = useCallback((type: MarketPanelType) => {
    ops.addPanel(type);
    ops.setActivePanel(null);
  }, [ops]);

  const applyPreset = useCallback((presetId: string) => {
    const p = getWorkspacePreset(presetId);
    if (p) ops.replaceLayout(p.build());
  }, [ops]);

  const resetWorkspace = useCallback(() => {
    workspaces.clear(workspaces.activeId!);
    ops.replaceLayout(workspaces.defaultLayout);
  }, [ops, workspaces]);

  const saveNow = useCallback(() => {
    // Persistence is automatic on every op; this is an explicit confirmation.
    try {
      localStorage.setItem(workspaces.active!.storageKey, JSON.stringify(layout));
      setSavedAt(Date.now());
    } catch { /* best effort */ }
  }, [layout, workspaces.active]);

  // ── Linked charts (symbol / timeframe) ─────────────────────────────────────
  // Symbol + timeframe are low-frequency, so they flow through the layout kernel
  // (persisted). Crosshair + range are high-frequency and flow through the
  // imperative link bus inside ChartPanel — never through React state here.
  const publishChart = useCallback((sourceId: string, chart: ChartState) => {
    for (const p of layout.panels) {
      if (p.type !== 'chart') continue;
      if (p.id === sourceId) {
        ops.setPanelChart(p.id, chart);
        continue;
      }
      const l = p.link;
      if (!l) continue;
      const peer = { ...(p.chart as ChartState) };
      if (l.symbol) { peer.symbol = chart.symbol; peer.market = chart.market; }
      if (l.timeframe) peer.timeframe = chart.timeframe;
      ops.setPanelChart(p.id, peer);
      if (l.symbol && (p.symbol !== chart.symbol || p.market !== chart.market)) {
        ops.setPanelSymbol(p.id, chart.symbol, chart.market);
      }
    }
    setSavedAt(Date.now());
  }, [layout.panels, ops]);

  // ── Keyboard shortcuts ─────────────────────────────────────────────────────
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing = !!target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable);
      const mod = e.ctrlKey || e.metaKey;

      if (e.key === 'Escape') {
        if (focusedPanelId) { ops.setFocusedPanel(null); return; }
        if (fullPage) { ops.setFullPage(false); onRequestExitFullPage?.(); return; }
      }
      if (mod && e.key === 'Enter') { e.preventDefault(); ops.setFullPage(!fullPage); return; }
      if (mod && e.key.toLowerCase() === 's') { e.preventDefault(); saveNow(); return; }
      if (mod && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        void import('@/lib/search/store').then(({ useCommandStore }) => useCommandStore.getState().setOpen(true));
        return;
      }
      if (!typing && e.key.toLowerCase() === 'f' && !mod) {
        // Fullscreen the active panel (or the first chart).
        const id = activePanelId ?? layout.panels.find(p => p.type === 'chart')?.id;
        if (id) { ops.setActivePanel(id); ops.setFocusedPanel(id); }
      }
      // Delete removes the active panel, but only while customizing — so a stray
      // Delete during normal trading never destroys a chart (a drawing deletion
      // inside a chart still works independently).
      if (!typing && e.key === 'Delete' && activePanelId && editMode) {
        ops.removePanel(activePanelId);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [activePanelId, focusedPanelId, fullPage, editMode, layout.panels, ops, saveNow, onRequestExitFullPage]);

  // ── Panel grid styles ──────────────────────────────────────────────────────
  // Normal mode: rows get a generous minimum height so charts stay big and
  // readable; the page scrolls when there are many rows. Full-page uses its own
  // viewport-filling style built below (from the chart-only row count).
  const gridStyle: React.CSSProperties = isCustom
    ? {
        gridTemplateColumns: `repeat(${GRID_COLUMNS}, minmax(0, 1fr))`,
        gridAutoRows: '380px',
        gridAutoFlow: 'row dense',
      }
    : {
        gridTemplateColumns: `repeat(${GRID_COLUMNS}, minmax(0, 1fr))`,
        gridTemplateRows: `repeat(${Math.max(1, layout.rows)}, minmax(380px, 1fr))`,
        gridAutoRows: 'minmax(380px, 1fr)',
      };

  const panelStyle = (panel: MarketPanel, override?: PanelRect): React.CSSProperties => {
    const r = override ?? panel.rect;
    return {
      gridColumn: `${r.col + 1} / span ${r.colSpan}`,
      gridRow: `${r.row + 1} / span ${r.rowSpan}`,
    };
  };

  const focused = focusedPanelId ? layout.panels.find(p => p.id === focusedPanelId) ?? null : null;

  // ── Render ─────────────────────────────────────────────────────────────────
  const renderChartPanel = (panel: MarketPanel, rectOverride?: PanelRect) => (
    <ChartPanel
      panel={panel}
      compact={panel.rect.colSpan <= 4 || panel.rect.rowSpan <= 1}
      gridStyle={panelStyle(panel, rectOverride)}
      active={activePanelId === panel.id}
      editMode={editMode}
      dragHandleProps={{ onPointerDown: onGridPointerDown(panel, 'move') }}
      resizeHandleProps={{ onPointerDown: onGridPointerDown(panel, 'resize') }}
      onChartChange={(chart) => publishChart(panel.id, chart)}
      onLinkChange={(link: ChartLink) => ops.setPanelLink(panel.id, link)}
      onToggleAi={() => ops.togglePanelAi(panel.id)}
      onRemove={() => ops.removePanel(panel.id)}
      onDuplicate={() => ops.duplicatePanel(panel.id)}
      onFocus={() => { ops.setActivePanel(panel.id); ops.setFocusedPanel(panel.id); }}
      onDropSymbol={(symbol, market) => ops.setPanelSymbol(panel.id, symbol, market)}
    />
  );

  const renderContentPanel = (panel: MarketPanel, rectOverride?: PanelRect) => (
    <div
      className={cn(
        'group/panel relative flex min-h-0 flex-col overflow-hidden rounded-2xl glass-card shadow-md shadow-black/10',
        activePanelId === panel.id && 'ring-1 ring-primary/50',
      )}
      style={panelStyle(panel, rectOverride)}
      onMouseDown={() => ops.setActivePanel(panel.id)}
    >
      <div className="min-h-0 flex-1">
        <PanelContent
          panel={panel}
          onPickSymbol={(symbol, market) => {
            // Clicking a watchlist row targets the active chart, else the first.
            const target = layout.panels.find(p => p.id === activePanelId && p.type === 'chart')
              ?? layout.panels.find(p => p.type === 'chart');
            if (target && market) publishChart(target.id, { ...(target.chart as ChartState), symbol, market });
          }}
        />
      </div>
      {editMode && (
        <PanelEditChrome
          onMove={onGridPointerDown(panel, 'move')}
          onResize={onGridPointerDown(panel, 'resize')}
          onRemove={() => ops.removePanel(panel.id)}
          onDuplicate={() => ops.duplicatePanel(panel.id)}
          onFocus={() => { ops.setActivePanel(panel.id); ops.setFocusedPanel(panel.id); }}
        />
      )}
    </div>
  );

  // Full page shows CHARTS ONLY — non-chart panels are omitted so the screen is
  // pure price action. Everything else stays exactly where the user left it.
  const visiblePanels = fullPage ? layout.panels.filter(p => p.type === 'chart') : layout.panels;

  // Render-only compaction for full page: keep each chart's column/span, but
  // re-flow rows tightly so there are no empty gaps left behind by non-chart
  // panels. Stored layout is never mutated.
  const fullPageRects = React.useMemo(() => {
    if (!fullPage) return new Map<string, PanelRect>();
    const map = new Map<string, PanelRect>();
    const placed: PanelRect[] = [];
    for (const p of visiblePanels) {
      let row = 0;
      // Walk down until this rect clears everything already placed.
      for (let guard = 0; guard < 200; guard++) {
        const candidate: PanelRect = { ...p.rect, row };
        if (!placed.some(r => rectsOverlap(candidate, r))) { placed.push(candidate); map.set(p.id, candidate); break; }
        row += 1;
      }
    }
    return map;
  }, [fullPage, visiblePanels]);

  const chartOnlyRows = Math.max(1, [...fullPageRects.values()].reduce((a, r) => Math.max(a, r.row + r.rowSpan), 0));
  const fullPageGridStyle: React.CSSProperties = {
    gridTemplateColumns: `repeat(${GRID_COLUMNS}, minmax(0, 1fr))`,
    gridTemplateRows: `repeat(${chartOnlyRows}, minmax(0, 1fr))`,
    gridAutoRows: 'minmax(0, 1fr)',
    height: '100%',
    flex: '1 1 0%',
  };

  // The panel grid is shared between normal and full-page modes.
  const gridEl = (
    <div
      ref={gridRef}
      data-market-workspace
      className={cn('grid min-h-0', fullPage ? 'gap-1.5' : 'flex-1 gap-2.5')}
      style={fullPage ? fullPageGridStyle : gridStyle}
    >
      {visiblePanels.map((panel) => {
        const previewRect = preview?.id === panel.id ? preview.rect : undefined;
        if (fullPage) {
          // Charts only; rows are viewport-fraction tracks so each fills the
          // screen. Stored layout is untouched — this is a render projection.
          return (
            <React.Fragment key={panel.id}>
              <ChartPanel
                panel={panel}
                compact={false}
                gridStyle={panelStyle(panel, fullPageRects.get(panel.id))}
                active={activePanelId === panel.id}
                onChartChange={(chart) => publishChart(panel.id, chart)}
                onLinkChange={(link: ChartLink) => ops.setPanelLink(panel.id, link)}
                onToggleAi={() => ops.togglePanelAi(panel.id)}
                onRemove={() => ops.removePanel(panel.id)}
                onDuplicate={() => ops.duplicatePanel(panel.id)}
                onFocus={() => { ops.setActivePanel(panel.id); ops.setFocusedPanel(panel.id); }}
                onDropSymbol={(symbol, market) => ops.setPanelSymbol(panel.id, symbol, market)}
              />
            </React.Fragment>
          );
        }
        if (CHART_LIKE.has(panel.type)) {
          return <React.Fragment key={panel.id}>{renderChartPanel(panel, previewRect)}</React.Fragment>;
        }
        return <React.Fragment key={panel.id}>{renderContentPanel(panel, previewRect)}</React.Fragment>;
      })}
      {visiblePanels.length === 0 && (
        <div className="col-span-full flex flex-col items-center justify-center rounded-2xl glass-card p-12 text-center">
          <p className="text-sm text-muted-foreground">
            {fullPage ? 'Add a chart to the workspace to use full page.' : 'No panels yet. Use Add Panel to begin.'}
          </p>
        </div>
      )}
    </div>
  );

  // Full-page overlay. Portaled to <body> because the app shell wraps this page
  // in a glass-card (backdrop-filter creates a containing block), which would
  // otherwise trap `position: fixed` and keep the global nav visible on top.
  const fullPageOverlay = fullPage && typeof document !== 'undefined'
    ? createPortal(
        <div className="fixed inset-0 z-[70] flex flex-col bg-background p-2">
          <div className="pointer-events-none absolute right-3 top-3 z-[75] flex items-center gap-1.5">
            <button
              onClick={() => { ops.setFullPage(false); onRequestExitFullPage?.(); }}
              className="pointer-events-auto glass-button inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold text-muted-foreground hover:text-primary cursor-pointer"
              title="Exit full page (Esc)"
            >
              <Minimize2 size={13} /> Exit
              <kbd className="ml-0.5 rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-[9px]">Esc</kbd>
            </button>
          </div>
          {gridEl}
        </div>,
        document.body,
      )
    : null;

  // Single-chart fullscreen overlay. Portaled for the same containing-block
  // reason, and it renders the panel's chart optimised for the full viewport.
  const focusedOverlay = focused && typeof document !== 'undefined'
    ? createPortal(
        <div className="fixed inset-0 z-[80] flex flex-col bg-background/95 p-3 backdrop-blur-md">
          <div className="mb-2 flex items-center gap-2">
            <span className="font-serif text-sm font-semibold text-foreground">
              {focused.chart?.symbol ?? focused.symbol ?? focused.type} — fullscreen
            </span>
            <span className="font-mono text-[9px] uppercase tracking-wide text-muted-foreground/60">Esc to exit</span>
            <div className="ml-auto flex items-center gap-1.5">
              {focused.type === 'chart' && (
                <button
                  onClick={() => ops.setPanelLink(focused.id, {
                    symbol: false, timeframe: false, crosshair: !focused.link?.crosshair, range: !focused.link?.range,
                  })}
                  className="glass-button inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold text-muted-foreground hover:text-primary cursor-pointer"
                  title="Toggle crosshair + range linking"
                >
                  <Maximize2 size={12} /> Link view
                </button>
              )}
              <button
                onClick={() => ops.setFocusedPanel(null)}
                className="glass-button inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold text-muted-foreground hover:text-primary cursor-pointer"
              >
                <Minimize2 size={12} /> Exit
              </button>
              <button
                onClick={() => ops.setFocusedPanel(null)}
                className="rounded-lg p-1.5 text-muted-foreground hover:text-rose-400 cursor-pointer"
              >
                <X size={16} />
              </button>
            </div>
          </div>
          <div className="min-h-0 flex-1">
            {focused.type === 'chart' ? (
              <ChartPanel
                panel={{ ...focused, rect: { col: 0, row: 0, colSpan: GRID_COLUMNS, rowSpan: 1 } }}
                compact={false}
                gridStyle={{ gridColumn: '1 / -1', gridRow: '1', height: '100%' }}
                active
                onChartChange={(chart) => publishChart(focused.id, chart)}
                onLinkChange={(link) => ops.setPanelLink(focused.id, link)}
                onToggleAi={() => ops.togglePanelAi(focused.id)}
                onRemove={() => { ops.removePanel(focused.id); ops.setFocusedPanel(null); }}
                onDuplicate={() => ops.duplicatePanel(focused.id)}
                onFocus={() => {}}
                onDropSymbol={(symbol, market) => ops.setPanelSymbol(focused.id, symbol, market)}
              />
            ) : (
              <div className="h-full overflow-hidden rounded-2xl glass-card">
                <PanelContent panel={focused} />
              </div>
            )}
          </div>
        </div>,
        document.body,
      )
    : null;

  return (
    <div className={cn('relative flex min-h-0 flex-col', className)}>
      {!embedded && !fullPage && (
        <div className="mb-3 flex flex-wrap items-center gap-3 border-b border-border/10 pb-3">
          <div className="min-w-0">
            <h1 className="font-serif text-xl font-semibold tracking-tight text-foreground">Market Workspace</h1>
            <p className="text-[11px] text-muted-foreground">
              {layout.panels.length} panels · {editMode ? 'customizing' : 'Ctrl+Enter full page · F chart fullscreen · Ctrl+K symbol search'}
            </p>
          </div>
          <div className="ml-auto">
            <PanelToolbar
              layoutId={layout.layoutId}
              editMode={editMode}
              fullPage={fullPage}
              panelCount={layout.panels.length}
              workspaceName={workspaces.active?.name ?? 'Workspace'}
              savedLabel={savedAt ? 'saved' : undefined}
              onAddPanel={addPanel}
              onLayout={(id) => ops.applyGridPreset(id)}
              onAutoArrange={() => ops.autoArrange()}
              onToggleEdit={() => ops.setEditMode(!editMode)}
              onToggleFullPage={() => ops.setFullPage(!fullPage)}
              onApplyPreset={applyPreset}
              onSave={saveNow}
              onReset={resetWorkspace}
              onRenameWorkspace={() => {
                const n = prompt('Rename workspace', workspaces.active?.name ?? '');
                if (n) workspaces.rename(workspaces.activeId!, n);
              }}
              onDuplicateWorkspace={() => workspaces.duplicate(workspaces.activeId!)}
            />
          </div>
        </div>
      )}

      {workspace.corrupt && !fullPage && (
        <div className="mb-3 rounded-2xl border border-amber-500/20 glass-card-subtle p-3 text-xs font-semibold text-amber-400">
          Saved workspace was unreadable — showing defaults. Your stored data was left untouched.
        </div>
      )}

      {fullPage ? fullPageOverlay : gridEl}

      {editMode && !fullPage && (
        <p className="mt-2 text-center text-[10px] text-muted-foreground">
          Drag a panel by its header to move · drag the bottom-right corner to resize · Delete removes the active panel · Done to finish.
        </p>
      )}

      {focusedOverlay}
    </div>
  );
}

// ── Edit chrome for a content (non-chart) panel ──────────────────────────────

function PanelEditChrome({
  onMove, onResize, onRemove, onDuplicate, onFocus,
}: {
  onMove: React.PointerEventHandler;
  onResize: React.PointerEventHandler;
  onRemove: () => void;
  onDuplicate: () => void;
  onFocus: () => void;
}) {
  return (
    <>
      <div
        onPointerDown={onMove}
        className="absolute inset-x-0 top-0 z-30 flex h-6 cursor-grab items-center justify-center rounded-t-2xl bg-background/50 opacity-0 transition-opacity group-hover/panel:opacity-100 active:cursor-grabbing"
        title="Drag to move panel"
      >
        <span className="h-1 w-10 rounded-full bg-border" />
      </div>
      <div className="absolute right-2 top-1.5 z-30 flex items-center gap-1 opacity-0 transition-opacity group-hover/panel:opacity-100">
        <button onClick={onFocus} className="rounded-lg border border-border/40 bg-background/80 p-1 text-muted-foreground hover:text-primary cursor-pointer" title="Fullscreen">
          <Maximize2 size={11} />
        </button>
        <button onClick={onDuplicate} className="rounded-lg border border-border/40 bg-background/80 p-1 text-muted-foreground hover:text-primary cursor-pointer" title="Duplicate">
          <Minimize2 size={11} className="rotate-45" />
        </button>
        <button onClick={onRemove} className="rounded-lg border border-border/40 bg-background/80 p-1 text-muted-foreground hover:text-rose-400 cursor-pointer" title="Remove">
          <X size={11} />
        </button>
      </div>
      <div
        onPointerDown={onResize}
        className="absolute bottom-0 right-0 z-30 h-4 w-4 cursor-nwse-resize opacity-0 transition-opacity group-hover/panel:opacity-100"
        title="Drag to resize panel"
      >
        <div className="absolute bottom-1 right-1 h-2 w-2 rounded-sm border-b-2 border-r-2 border-border" />
      </div>
    </>
  );
}

export type { MarketWorkspaceController };
