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
import { ChartCandlestick, Copy, GripVertical, Maximize2, Minimize2, Trash2, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useMarketWorkspace, type MarketWorkspaceController } from '@/lib/market-workspace/use-market-workspace';
import { useWorkspaces } from '@/lib/market-workspace/use-workspaces';
import { getWorkspacePreset } from '@/lib/market-workspace/presets';
import {
  clampRect, GRID_COLUMNS, MAX_ROWS, MIN_PANEL_COLS, MIN_PANEL_ROWS,
  type ChartLink, type MarketPanel, type MarketPanelType, type PanelRect,
} from '@/lib/market-workspace/types';

/** Fallback row height (px) when the grid has not been measured yet. */
const CUSTOM_ROW_HEIGHT = 380;

/** Charts-per-row for full page — chosen so N charts tile a near-square grid. */
function fullPagePerRow(count: number): number {
  if (count <= 1) return 1;
  if (count === 2) return 2;
  if (count <= 4) return 2;
  if (count <= 6) return 3;
  if (count <= 9) return 3;
  return 4;
}
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

  // Measure the grid so pointer drags convert px → grid units. The row height is
  // read from the ACTUAL first-row track size (not a guessed constant) so a drag
  // of N pixels moves the panel exactly N/rowHeight rows.
  useEffect(() => {
    const el = gridRef.current;
    if (!el) return;
    const measure = () => {
      const rect = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      // Prefer the resolved template track; fall back to a sensible constant.
      const firstTrack = cs.gridTemplateRows.split(' ').map(parseFloat).find(Number.isFinite);
      const track = firstTrack && firstTrack > 0 ? firstTrack : CUSTOM_ROW_HEIGHT;
      // Moving a panel down by ONE row moves it by (track + row-gap) pixels.
      const gap = parseFloat(cs.rowGap) || 0;
      setCellSize({ w: rect.width / GRID_COLUMNS, h: track + gap });
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
    ops.setDragging(true);
    document.body.style.userSelect = 'none';

    const cellW = cellSize.w > 0 ? cellSize.w : 100;
    const cellH = cellSize.h > 0 ? cellSize.h : CUSTOM_ROW_HEIGHT;

    const onMove = (ev: PointerEvent) => {
      const d = dragRef.current;
      if (!d) return;
      const dCols = Math.round((ev.clientX - d.startX) / cellW);
      const dRows = Math.round((ev.clientY - d.startY) / cellH);
      const rect: PanelRect = d.mode === 'move'
        ? { ...d.startRect, col: d.startRect.col + dCols, row: d.startRect.row + dRows }
        : {
            ...d.startRect,
            colSpan: Math.max(MIN_PANEL_COLS, d.startRect.colSpan + dCols),
            rowSpan: Math.max(MIN_PANEL_ROWS, d.startRect.rowSpan + dRows),
          };
      setPreview({ id: d.id, rect: clampRect(rect, MAX_ROWS) });
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      document.body.style.userSelect = '';
      ops.setDragging(false);
      const d = dragRef.current;
      dragRef.current = null;
      const p = previewRef.current;
      setPreview(null);
      if (!d || !p || p.id !== d.id) return;
      // MOVE commits absolute placement (panel stays where dropped; anything it
      // lands on is pushed aside). RESIZE commits the new span.
      if (d.mode === 'move') ops.placePanel(d.id, p.rect.col, p.rect.row);
      else ops.setPanelRect(d.id, p.rect);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [editMode, cellSize, ops]);

  const previewRef = useRef(preview);
  previewRef.current = preview;

  // ── Panel CRUD / layout ────────────────────────────────────────────────────
  // A new panel usually lands below the fold, so remember the count we expect
  // and scroll/flash the new panel in a post-commit effect (deterministic —
  // no timer guessing about when React has rendered).
  const pendingScroll = useRef(false);
  const addPanel = useCallback((type: MarketPanelType) => {
    pendingScroll.current = true;
    // Seed a NEW chart with this workspace's own lead instrument rather than a
    // hard-coded AAPL: reuse the first chart's symbol/market in the layout.
    const lead = layout.panels.find(p => p.type === 'chart' && p.chart?.symbol);
    ops.addPanel(type, undefined, lead
      ? { symbol: lead.chart!.symbol, market: lead.chart!.market }
      : undefined);
    ops.setActivePanel(null);
  }, [ops, layout.panels]);

  useEffect(() => {
    if (!pendingScroll.current) return;
    pendingScroll.current = false;
    const grid = gridRef.current;
    const last = grid?.children[grid.children.length - 1] as HTMLElement | undefined;
    if (!last) return;
    // Two frames so the grid has fully laid out before measuring.
    requestAnimationFrame(() => requestAnimationFrame(() => {
      last.scrollIntoView({ behavior: 'smooth', block: 'center' });
      last.classList.add('ring-2', 'ring-primary/80');
      window.setTimeout(() => last.classList.remove('ring-2', 'ring-primary/80'), 1800);
    }));
  }, [layout.panels.length]);

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

  // Lock page scroll while full page (or a chart is fullscreen) so the reclaimed
  // space is actually usable and the background can't drift behind the overlay.
  useEffect(() => {
    if (!fullPage && !focusedPanelId) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, [fullPage, focusedPanelId]);

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
  // Normal mode: rows are exactly `layout.rows` tracks. When the panels fit on
  // screen the grid STRETCHES to fill the viewport (1fr min); when there are
  // more rows than fit, each track stays readable at >= 380px and the page
  // scrolls. `recomputeRows` keeps layout.rows equal to the content height, so
  // there is never phantom scroll space below the last panel.
  const gridStyle: React.CSSProperties = isCustom
    ? {
        gridTemplateColumns: `repeat(${GRID_COLUMNS}, minmax(0, 1fr))`,
        gridAutoRows: `${CUSTOM_ROW_HEIGHT}px`,
        gridAutoFlow: 'row dense',
      }
    : {
        gridTemplateColumns: `repeat(${GRID_COLUMNS}, minmax(0, 1fr))`,
        gridTemplateRows: `repeat(${Math.max(1, layout.rows)}, minmax(${CUSTOM_ROW_HEIGHT}px, 1fr))`,
        gridAutoRows: `minmax(${CUSTOM_ROW_HEIGHT}px, 1fr)`,
      };

  const panelStyle = (panel: MarketPanel, override?: PanelRect): React.CSSProperties => {
    const r = override ?? panel.rect;
    return {
      gridColumn: `${r.col + 1} / span ${r.colSpan}`,
      gridRow: `${r.row + 1} / span ${r.rowSpan}`,
    };
  };

  const focused = focusedPanelId ? layout.panels.find(p => p.id === focusedPanelId) ?? null : null;

  // Dense mode is driven by the panel's REAL rendered width/height, not its
  // column span — a 4-unit panel on a 3-col preset is wide, while a 4-unit panel
  // on a 12-col custom grid is narrow. Falls back to span heuristics until the
  // grid has been measured.
  const compactFor = (rect: PanelRect): boolean => {
    const w = cellSize.w * rect.colSpan;
    const h = cellSize.h * rect.rowSpan;
    if (cellSize.w <= 0 || w < 360) return rect.colSpan <= 4 || rect.rowSpan <= 1;
    return w < 560 || h < 320;
  };

  // ── Render ─────────────────────────────────────────────────────────────────
  const renderChartPanel = (panel: MarketPanel, rectOverride?: PanelRect) => (
    <ChartPanel
      panel={panel}
      compact={compactFor(rectOverride ?? panel.rect)}
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

  // Full page re-tiles the charts into a near-square grid that FILLS the
  // viewport, independent of their stored spans (a stored 2-row-tall chart would
  // otherwise render short). Stored layout is never mutated — this is a pure
  // render projection while full page is open.
  const fullPageRows = React.useMemo(
    () => Math.max(1, Math.ceil(visiblePanels.length / fullPagePerRow(visiblePanels.length))),
    [visiblePanels.length],
  );
  const fullPageRects = React.useMemo(() => {
    if (!fullPage) return new Map<string, PanelRect>();
    const perRow = fullPagePerRow(visiblePanels.length);
    const map = new Map<string, PanelRect>();
    // Group panels into rows of `perRow`; within each row divide the 12 columns
    // evenly so the final, shorter row still spans the full width.
    for (let start = 0; start < visiblePanels.length; start += perRow) {
      const rowItems = visiblePanels.slice(start, start + perRow);
      const colSpan = Math.floor(GRID_COLUMNS / rowItems.length);
      const row = Math.floor(start / perRow);
      rowItems.forEach((p, j) => {
        // The last item of a row absorbs any rounding remainder so the row
        // always fills all 12 columns (8+4, 4+4+4, etc).
        const isLast = j === rowItems.length - 1;
        const col = j * colSpan;
        const span = isLast ? GRID_COLUMNS - col : colSpan;
        map.set(p.id, { col, row, colSpan: span, rowSpan: 1 });
      });
    }
    return map;
  }, [fullPage, visiblePanels]);

  // Full page: every row is an equal fraction of the FULL viewport height, so
  // charts expand to use all the reclaimed space (no compact, no letterboxing).
  const fullPageGridStyle: React.CSSProperties = {
    gridTemplateColumns: `repeat(${GRID_COLUMNS}, minmax(0, 1fr))`,
    gridTemplateRows: `repeat(${fullPageRows}, minmax(0, 1fr))`,
    gridAutoRows: 'minmax(0, 1fr)',
    height: '100%',
    minHeight: 0,
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
                chrome="minimal"
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
  // While open, background scroll is locked so the charts own the whole screen.
  const fullPageOverlay = fullPage && typeof document !== 'undefined'
    ? createPortal(
        <div className="fixed inset-0 z-[70] flex h-[100dvh] w-screen flex-col overflow-hidden bg-background p-2">
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
    <div
      className={cn(
        // Fill the viewport (minus the top bar, page padding and the heading) so
        // a small number of charts stretch big, while extra rows still scroll.
        'relative flex flex-col',
        fullPage ? '' : 'min-h-[calc(100dvh-190px)]',
        className,
      )}
      data-market-workspace-root
    >
      {!embedded && !fullPage && (
        <div className="mb-3 flex flex-wrap items-center gap-3 border-b border-border/10 pb-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-primary/25 bg-primary/15 shadow-sm shadow-primary/10">
              <ChartCandlestick className="text-primary" size={18} />
            </span>
            <div className="min-w-0">
              <h1 className="font-serif text-xl font-semibold tracking-tight text-foreground">Chart Workspace</h1>
              <p className="text-[11px] text-muted-foreground">
                {layout.panels.length} panels · {editMode ? 'customizing' : 'Ctrl+Enter full page · F chart fullscreen · Ctrl+K symbol search'}
              </p>
            </div>
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
// Only ever rendered in edit mode. Icons are deliberately DISTINCT from the
// panel's close affordances: Fullscreen (expand), Duplicate (copy), Remove
// (trash) — no bare × here, so a trash can never be mistaken for "close chart".

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
        className="absolute inset-x-0 top-0 z-30 flex h-6 cursor-grab items-center justify-center rounded-t-2xl bg-primary/10 opacity-0 transition-opacity group-hover/panel:opacity-100 active:cursor-grabbing"
        title="Drag to move panel"
      >
        <GripVertical size={12} className="text-primary" />
      </div>
      <div className="absolute right-2 top-1.5 z-30 flex items-center gap-1 opacity-0 transition-opacity group-hover/panel:opacity-100">
        <button onClick={onFocus} className="rounded-lg border border-border/40 bg-background/80 p-1 text-muted-foreground hover:text-primary cursor-pointer" title="Fullscreen">
          <Maximize2 size={11} />
        </button>
        <button onClick={onDuplicate} className="rounded-lg border border-border/40 bg-background/80 p-1 text-muted-foreground hover:text-primary cursor-pointer" title="Duplicate panel">
          <Copy size={11} />
        </button>
        <button onClick={onRemove} className="rounded-lg border border-border/40 bg-background/80 p-1 text-muted-foreground hover:text-rose-400 cursor-pointer" title="Remove panel">
          <Trash2 size={11} />
        </button>
      </div>
      <div
        onPointerDown={onResize}
        className="absolute bottom-0 right-0 z-30 flex h-5 w-5 cursor-nwse-resize items-end justify-end p-1 opacity-0 transition-opacity group-hover/panel:opacity-100"
        title="Drag to resize panel"
      >
        <span className="h-2 w-2 rounded-sm border-b-2 border-r-2 border-primary" />
      </div>
    </>
  );
}

export type { MarketWorkspaceController };
