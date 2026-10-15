'use client';

// ── WorkspaceCanvas — kernel edit chrome (dnd-kit) ───────────────────────────
// Renders sections/columns/cards and owns ALL drag/resize/hide chrome.
// Widgets stay pure: the page only supplies renderWidget(widgetId).
//
// Drag model (insertion-based): while dragging, every gap between sibling
// cards shows a live drop-indicator line; the pointer's projected (column,
// index) position is tracked continuously and COMMITTED once on release.
//
// IMPORTANT: the drop target is derived from the REAL pointer position via a
// native window pointermove listener — NOT from dnd-kit's DragOver delta.
// dnd-kit's delta is scroll-adjusted (raw delta minus auto-scroll), so
// activator+delta stops matching client coordinates the moment the container
// auto-scrolls mid-drag, and elementFromPoint then hits the wrong element.

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  DndContext, DragOverlay, PointerSensor, useSensor, useSensors,
  useDroppable, useDraggable, type DragStartEvent,
} from '@dnd-kit/core';
import {
  ChevronLeft, ChevronRight, Columns3, Copy, EyeOff, GripVertical, Minus, Plus, Sparkles, Trash2, X,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import { canHandleKeyboardEvent, matchesShortcut } from '@/lib/keyboard';
import { WorkspaceDrawer, type WorkspaceWidgetMeta } from './workspace-drawer';
import { ColumnEdge, ConfirmGhost, DropLine, EmptyMainZone, NewSectionStrip, idOf } from './workspace-chrome';
import type { WidgetPlacement, WorkspaceSection } from './types';
import { MAX_ZONE_WIDTH, MIN_COLUMN_WEIGHT, MIN_ZONE_WIDTH } from './types';
import type { WorkspaceController as WC } from './use-workspace';

const CARD_CLASS =
  'rounded-2xl glass-card shadow-md shadow-black/10 transition-all duration-300';

/** Where the dragged card should land (kept in a ref for the commit + state for the UI). */
interface DropTargetInfo {
  sectionId: string;
  columnId: string;
  index: number;
}

interface WorkspaceCanvasProps {
  workspace: WC;
  renderWidget: (widgetId: string, placement: WidgetPlacement) => React.ReactNode;
  widgets: WorkspaceWidgetMeta[];
  className?: string;
  /** Hide the built-in edit bar (used when a host provides its own chrome). */
  hideEditBar?: boolean;
  /** Widget id currently being dragged in from the library (add-drag mode). */
  addingWidgetId?: string | null;
  /** Label for the add-drag ghost. */
  addingLabel?: string;
  /** 'hold' = release to place · 'click' = project then double-click to confirm. */
  addingMode?: 'hold' | 'click';
  /** Called when an add-drag ends (committed or cancelled) so the host clears it. */
  onAddingEnd?: () => void;
  /**
   * Enable the side `left` / `right` zones: sections tagged with that zone
   * render in a narrow column beside the main canvas, under the SAME drag
   * context, so cards can be dragged freely between centre and sides. When a
   * zone is unset, its sections render in the main column (single-zone pages
   * like fund workspaces).
   */
  zones?: { left?: WorkspaceZoneConfig; right?: WorkspaceZoneConfig };
  /** Tighter gutters between zones, sections, columns and cards. */
  dense?: boolean;
}

/** Per-zone presentation config (width, header, collapse state). */
export interface WorkspaceZoneConfig {
  /** Width class for the zone column (default `w-72`). */
  className?: string;
  /** Header rendered above the zone (e.g. "Market" title + collapse button). */
  header?: React.ReactNode;
  /** Collapse the zone down to a slim expand affordance. */
  collapsed?: boolean;
  /** Toggle the zone collapse state (renders the expand button when collapsed). */
  onToggle?: () => void;
}

export function WorkspaceCanvas({ workspace, renderWidget, widgets, className, hideEditBar = false, addingWidgetId = null, addingLabel, addingMode = 'hold', onAddingEnd, zones, dense = false }: WorkspaceCanvasProps) {
  const { layout, editMode, ops, corrupt } = workspace;
  const rootRef = useRef<HTMLDivElement>(null);
  const zoneRowRef = useRef<HTMLDivElement>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [activeLabel, setActiveLabel] = useState('');
  const [activeWidth, setActiveWidth] = useState(360);
  const [target, setTarget] = useState<DropTargetInfo | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  // Side-zone widths only apply once the zones sit in a row again (lg+). Below
  // that the zones stack full-width, so a user-pinned pixel width must not leak
  // through (it would overflow the stacked column).
  const [zonesSideBySide, setZonesSideBySide] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia('(min-width: 1024px)');
    const update = () => setZonesSideBySide(mq.matches);
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, []);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  // Live drop target — a ref so the pointermove handler and onDragEnd always
  // see the freshest projection without re-render churn.
  const targetRef = useRef<DropTargetInfo | null>(null);
  const setTargetBoth = useCallback((t: DropTargetInfo | null) => {
    targetRef.current = t;
    setTarget(prev => {
      const same = (a: DropTargetInfo | null, b: DropTargetInfo | null) =>
        a === b || (a !== null && b !== null && a.sectionId === b.sectionId && a.columnId === b.columnId && a.index === b.index);
      if (same(prev, t)) return prev;
      return t;
    });
  }, []);
  const layoutRef = useRef(layout);
  useEffect(() => { layoutRef.current = layout; }, [layout]);

  const activePlacement = useMemo(() => {
    if (!activeId) return null;
    for (const s of layout.sections) for (const c of s.columns) {
      const w = c.widgets.find(x => x.id === activeId);
      if (w) return w;
    }
    return null;
  }, [activeId, layout]);

  useEffect(() => { ops.setDragging(activeId !== null); }, [activeId, ops]);

  const onDragStart = (e: DragStartEvent) => {
    setActiveId(String(e.active.id));
    for (const s of layout.sections) for (const c of s.columns) {
      const w = c.widgets.find(x => x.id === String(e.active.id));
      if (w) {
        setActiveLabel(widgets.find(m => m.widgetId === w.widgetId)?.label ?? w.widgetId);
        break;
      }
    }
    const rect = e.active.rect.current.initial as { width?: number } | undefined;
    setActiveWidth(Math.min(520, Math.max(280, rect?.width ?? 360)));
  };

  // ── Real-pointer drop projection ────────────────────────────────────────────
  // Runs on every native pointermove while a drag is active. elementFromPoint
  // with true client coordinates is immune to dnd-kit's scroll-adjusted delta,
  // and fires continuously (dnd-kit's onDragOver only fires when its `over`
  // id changes, which never happens between gaps inside one column).

  /** Insertion index within a column element for a pointer y (gaps between cards). */
  const insertIndexFor = (colEl: HTMLElement, dragId: string, y: number): number => {
    const cards = Array.from(colEl.querySelectorAll<HTMLElement>('[data-wcard]'))
      .filter(el => el.getAttribute('data-wcard') !== dragId);
    for (let i = 0; i < cards.length; i++) {
      const r = cards[i].getBoundingClientRect();
      if (y < r.top + r.height / 2) return i;
    }
    return cards.length;
  };

  const computeTarget = useCallback((px: number, py: number, dragId: string): DropTargetInfo | null => {
    // CRITICAL: use elementsFromPoint (plural), not elementFromPoint. During a
    // drag, dnd-kit's DragOverlay follows the cursor and sits above the columns,
    // so elementFromPoint returns the overlay (which has no [data-wcol]) and the
    // projection yields null → drops never commit. Walk the stack and use the
    // first element that belongs to a real drop zone, skipping the overlay.
    const stack = document.elementsFromPoint(px, py);
    // 1) Inter-section strips → new section above/below the anchor.
    for (const el of stack) {
      const strip = el.closest<HTMLElement>('[data-newsec]');
      if (strip) {
        const [anchorId, pos] = strip.dataset.newsec!.split(':') as [string, 'above' | 'below'];
        return { sectionId: anchorId, columnId: `__newsec:${anchorId}:${pos}`, index: 0 };
      }
    }

    // 2) Left/right edges of a column → new column beside it.
    for (const el of stack) {
      const edge = el.closest<HTMLElement>('[data-edge]');
      if (edge) {
        const { edge: side, col, sec } = edge.dataset as { edge: 'L' | 'R'; col: string; sec: string };
        return { sectionId: sec, columnId: `__newcol:${side === 'L' ? 'before' : 'after'}:${col}`, index: 0 };
      }
    }

    // 3) Column interior → projected insertion index between cards.
    for (const el of stack) {
      const colEl = el.closest<HTMLElement>('[data-wcol]');
      if (!colEl) continue;
      const colId = colEl.dataset.wcol!;
      const section = layoutRef.current.sections.find(s => s.columns.some(c => c.id === colId));
      if (!section) continue;
      return { sectionId: section.id, columnId: colId, index: insertIndexFor(colEl, dragId, py) };
    }

    // 4) Empty centre zone → create a NEW main section holding the card. This
    //    is what makes an emptied centre (e.g. rails still present) able to
    //    receive a drop again — without it computeTarget returned null and both
    //    drag-drop and library adds silently did nothing.
    for (const el of stack) {
      if (el.closest<HTMLElement>('[data-emptyzone]')) {
        return { sectionId: '', columnId: '__newmain', index: 0 };
      }
    }

    return null;
  }, []);

  // Track the live pointer while dragging; drive the drop target from it.
  // lastPointerRef is shared: onDragEnd re-projects from it so the committed
  // position matches exactly what the user saw at release.
  const lastPointerRef = useRef<{ x: number; y: number } | null>(null);
  /** Set when a real dnd drag ends — clicks within the window are its echo. */
  const lastDragEndRef = useRef(0);
  useEffect(() => {
    if (!activeId) return;
    let raf = 0;
    let lastX = -1, lastY = -1;
    const onMove = (ev: PointerEvent) => {
      lastX = ev.clientX; lastY = ev.clientY;
      lastPointerRef.current = { x: lastX, y: lastY };
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        setTargetBoth(computeTarget(lastX, lastY, activeId));
      });
    };
    window.addEventListener('pointermove', onMove, { passive: true });
    return () => {
      window.removeEventListener('pointermove', onMove);
      if (raf) cancelAnimationFrame(raf);
      setTargetBoth(null);
    };
  }, [activeId, computeTarget, setTargetBoth]);

  /** Click-to-grab fallback for touchpads/touchscreens where drag pan-gestures fight the pointer sensor. */
  const [grabbedId, setGrabbedId] = useState<string | null>(null);
  /** Two-click confirm: a projected target the user previewed and armed with click 1. */
  const [armedTarget, setArmedTarget] = useState<DropTargetInfo | null>(null);
  const armedTargetRef = useRef<DropTargetInfo | null>(null);
  const setArmedBoth = useCallback((t: DropTargetInfo | null) => {
    armedTargetRef.current = t;
    setArmedTarget(t);
  }, []);

  // Auto-scroll the nearest scrollable ancestor(s) toward the pointer while
  // dragging OR click-grabbing so off-screen rows (e.g. an empty section at
  // the bottom) are reachable. dnd-kit skips auto-scroll once a DragOverlay
  // is rendered, so we provide it ourselves.
  useEffect(() => {
    if (!activeId && !grabbedId) return;
    let raf = 0;
    const lastPointer = { y: -1 };
    const track = (ev: PointerEvent) => { lastPointer.y = ev.clientY; };

    const scrollableAncestors = (node: Element | null): HTMLElement[] => {
      const out: HTMLElement[] = [];
      let cur = node?.parentElement;
      while (cur && cur !== document.body) {
        const st = getComputedStyle(cur);
        const scrollable = /(auto|scroll)/.test(st.overflowY) && cur.scrollHeight > cur.clientHeight + 2;
        if (scrollable) out.push(cur);
        cur = cur.parentElement;
      }
      return out;
    };

    const step = () => {
      raf = requestAnimationFrame(step);
      if (lastPointer.y < 0) return;
      const node = document.querySelector('[data-workspace]');
      const pad = 90;
      const m = 48;
      for (const el of scrollableAncestors(node)) {
        const r = el.getBoundingClientRect();
        if (lastPointer.y < r.top + pad) el.scrollBy({ top: -Math.ceil((pad - (lastPointer.y - r.top)) / 2) });
        else if (lastPointer.y > r.bottom - m) el.scrollBy({ top: Math.ceil((lastPointer.y - (r.bottom - m)) / 2) });
      }
    };
    window.addEventListener('pointermove', track, { passive: true });
    raf = requestAnimationFrame(step);
    return () => {
      window.removeEventListener('pointermove', track);
      cancelAnimationFrame(raf);
    };
  }, [activeId, grabbedId]);

  const onDragEnd = () => {
    const dragId = activeId;
    lastDragEndRef.current = performance.now();
    setActiveId(null);
    // Re-project from the exact release position — the last rAF frame can be
    // a frame behind the pointer, which made cards land "one notch" off.
    const p = lastPointerRef.current;
    const t = dragId && p ? computeTarget(p.x, p.y, dragId) : targetRef.current;
    setTargetBoth(null);
    if (!dragId || !t) return;
    // Real pointer drags commit immediately on release — the card lands where
    // the user dropped it. The two-click confirm model is reserved for the
    // click-grab fallback (touch/touchpad) where there is no drag gesture.
    commitTarget(dragId, t);
  };

  // While grabbed (no active dnd drag), the pointermove projection still runs
  // so the user can hover targets; release places the card.
  const grabStateRef = useRef<{ id: string | null; label: string }>({ id: null, label: '' });
  useEffect(() => {
    grabStateRef.current.id = grabbedId;
    if (grabbedId) {
      for (const s of layout.sections) for (const c of s.columns) {
        const w = c.widgets.find(x => x.id === grabbedId);
        if (w) { grabStateRef.current.label = widgets.find(m => m.widgetId === w.widgetId)?.label ?? w.widgetId; break; }
      }
    }
  }, [grabbedId, layout, widgets]);

  // Pointer projection for click-grab mode (no dnd drag active).
  useEffect(() => {
    if (!grabbedId) return;
    let raf = 0;
    let lastX = -1, lastY = -1;
    const onMove = (ev: PointerEvent) => {
      lastX = ev.clientX; lastY = ev.clientY;
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        setTargetBoth(computeTarget(lastX, lastY, grabbedId));
      });
    };
    window.addEventListener('pointermove', onMove, { passive: true });
    return () => {
      window.removeEventListener('pointermove', onMove);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [grabbedId, computeTarget, setTargetBoth]);

  /** Commit a target for the grabbed card (shared by confirm + strip paths). */
  const commitTarget = useCallback((id: string, t: DropTargetInfo) => {
    if (t.columnId === '__newmain') {
      ops.moveWidgetToNewSection(id);
      return;
    }
    if (t.columnId.startsWith('__newsec:')) {
      const [, anchorId, pos] = t.columnId.split(':') as [string, string, 'above' | 'below'];
      ops.moveWidgetToNewSectionAt(id, anchorId, pos);
      return;
    }
    if (t.columnId.startsWith('__newcol:')) {
      const [, when, anchorColId] = t.columnId.split(':') as [string, string, 'before' | 'after'];
      const section = layoutRef.current.sections.find(s => s.columns.some(c => c.id === anchorColId));
      const colIdx = section?.columns.findIndex(c => c.id === anchorColId) ?? -1;
      if (!section || colIdx === -1) return;
      ops.moveWidget(id, { sectionId: section.id, columnId: null, index: 0, columnIndex: when === 'before' ? colIdx : colIdx + 1 });
      return;
    }
    ops.moveWidget(id, { sectionId: t.sectionId, columnId: t.columnId, index: t.index });
  }, [ops]);

  /**
   * Commit an ADD from the library at a projected target. Mirrors
   * commitTarget but inserts a brand-new placement instead of moving one, and
   * creates a whole new section when dropped on an inter-section strip.
   */
  const commitAdd = useCallback((widgetId: string, t: DropTargetInfo) => {
    // Carry the widget's intrinsic sizing so a freshly added chart/map gets a
    // definite frame instead of collapsing (the "blank widget" regression).
    const meta = widgets.find(m => m.widgetId === widgetId);
    const sizing = meta ? { defaultHeight: meta.defaultHeight, minHeight: meta.minHeight } : undefined;
    if (t.columnId === '__newmain') {
      ops.addWidgetToNewSection(widgetId, 'main', sizing);
      return;
    }
    if (t.columnId.startsWith('__newsec:')) {
      const [, anchorId, pos] = t.columnId.split(':') as [string, string, 'above' | 'below'];
      ops.addWidgetToNewSectionAt(widgetId, anchorId, pos, sizing);
      return;
    }
    if (t.columnId.startsWith('__newcol:')) {
      const [, when, anchorColId] = t.columnId.split(':') as [string, string, 'before' | 'after'];
      const section = layoutRef.current.sections.find(s => s.columns.some(c => c.id === anchorColId));
      const colIdx = section?.columns.findIndex(c => c.id === anchorColId) ?? -1;
      if (!section || colIdx === -1) return;
      ops.addWidget(widgetId, { sectionId: section.id, columnId: null, index: 0, columnIndex: when === 'before' ? colIdx : colIdx + 1 }, sizing);
      return;
    }
    ops.addWidget(widgetId, { sectionId: t.sectionId, columnId: t.columnId, index: t.index }, sizing);
  }, [ops, widgets]);

  // ── Add-drag from the library ───────────────────────────────────────────────
  // A widget dragged out of the palette has no DOM card yet, so it uses the
  // same real-pointer projection as a grab but commits an ADD on release. The
  // host passes `addingWidgetId`; we own the listeners + floating ghost.
  const [addGhost, setAddGhost] = useState<{ x: number; y: number } | null>(null);
  useEffect(() => {
    if (!addingWidgetId) { setAddGhost(null); return; }
    const widgetId = addingWidgetId;
    const holdMode = addingMode === 'hold';
    let raf = 0;
    let lx = -1, ly = -1;
    function cleanup() {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('contextmenu', onCtx);
      if (raf) cancelAnimationFrame(raf);
      setTargetBoth(null);
      setAddGhost(null);
    }
    function onMove(ev: PointerEvent) {
      lx = ev.clientX; ly = ev.clientY;
      lastPointerRef.current = { x: lx, y: ly };
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        setTargetBoth(computeTarget(lx, ly, '__add__'));
        setAddGhost({ x: lx, y: ly });
      });
    }
    function onUp(ev: PointerEvent) {
      // Hold mode commits on release. Click mode keeps projecting so the user
      // can position the ghost and then double-click to confirm.
      if (!holdMode) return;
      const t = computeTarget(ev.clientX, ev.clientY, '__add__');
      cleanup();
      if (t) commitAdd(widgetId, t);
      onAddingEnd?.();
    }
    function onKey(e: KeyboardEvent) {
      if (matchesShortcut(e, 'escape') && canHandleKeyboardEvent(e, rootRef.current)) {
        e.preventDefault();
        cleanup();
        onAddingEnd?.();
      }
    }
    function onCtx(e: MouseEvent) {
      e.preventDefault(); cleanup(); onAddingEnd?.();
    }
    window.addEventListener('pointermove', onMove, { passive: true });
    window.addEventListener('pointerup', onUp);
    window.addEventListener('keydown', onKey);
    window.addEventListener('contextmenu', onCtx);
    return cleanup;
  }, [addingWidgetId, addingMode, computeTarget, commitAdd, setTargetBoth, onAddingEnd]);

  /**
   * Click-to-place for a grabbed card. A click on a drop target commits the
   * move (and a double-click also confirms). Clicking outside cancels.
   */
  const confirmOrArm = useCallback((coords?: { x: number; y: number }) => {
    const id = grabStateRef.current.id;
    if (!id) return;
    const t = coords ? computeTarget(coords.x, coords.y, id) : targetRef.current;
    if (!t) {
      // Click outside any drop area = cancel.
      setGrabbedId(null);
      setTargetBoth(null);
      setArmedBoth(null);
      return;
    }
    setGrabbedId(null);
    setTargetBoth(null);
    setArmedBoth(null);
    commitTarget(id, t);
  }, [computeTarget, commitTarget, setArmedBoth, setTargetBoth]);

  /** Cancel grab entirely (Escape / right-click / strip with no arm). */
  const cancelGrab = useCallback(() => {
    setGrabbedId(null);
    setTargetBoth(null);
    setArmedBoth(null);
  }, [setArmedBoth, setTargetBoth]);

  // Escape OR contextmenu (right-click) cancels the click-grab.
  useEffect(() => {
    if (!grabbedId) return;
    const onKey = (e: KeyboardEvent) => {
      if (!matchesShortcut(e, 'escape') || !canHandleKeyboardEvent(e, rootRef.current)) return;
      e.preventDefault();
      cancelGrab();
    };
    const onCtx = (e: MouseEvent) => { e.preventDefault(); cancelGrab(); };
    window.addEventListener('keydown', onKey);
    window.addEventListener('contextmenu', onCtx);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('contextmenu', onCtx);
    };
  }, [grabbedId, cancelGrab]);

  const onDragCancel = () => { lastDragEndRef.current = performance.now(); setActiveId(null); setTargetBoth(null); };

  /** Ghost-slot click: commit the armed target for the held card. */
  const onGhostConfirm = useCallback(() => {
    const id = grabStateRef.current.id;
    const t = armedTargetRef.current;
    cancelGrab();
    if (id && t) commitTarget(id, t);
  }, [cancelGrab, commitTarget]);

  /** Click on an empty column while grabbing → place into it (index 0). */
  const onEmptyColumnClick = useCallback((coords: { x: number; y: number }) => {
    const id = grabStateRef.current.id;
    if (!id) return;
    const t = computeTarget(coords.x, coords.y, id);
    if (!t) return;
    setGrabbedId(null);
    setTargetBoth(null);
    setArmedBoth(null);
    commitTarget(id, t);
  }, [computeTarget, commitTarget, setArmedBoth, setTargetBoth]);

  // Single-click placement for a library add-project. A double-click fires
  // click→click→dblclick, so guard against committing twice.
  const addCommitGuardRef = useRef(0);
  const commitAddAt = useCallback((px: number, py: number) => {
    if (!addingWidgetId) return;
    const now = performance.now();
    if (now - addCommitGuardRef.current < 350) return;
    addCommitGuardRef.current = now;
    const t = computeTarget(px, py, '__add__');
    onAddingEnd?.();
    if (t) commitAdd(addingWidgetId, t);
  }, [addingWidgetId, computeTarget, commitAdd, onAddingEnd]);

  /**
   * Double-click commit: the ADD for a click-project, or the held card move.
   */
  const commitOnDoubleClick = useCallback((px: number, py: number) => {
    if (addingWidgetId) { commitAddAt(px, py); return; }
    const id = grabStateRef.current.id;
    if (!id) return;
    const t = computeTarget(px, py, id);
    setGrabbedId(null);
    setTargetBoth(null);
    setArmedBoth(null);
    if (t) commitTarget(id, t);
  }, [addingWidgetId, commitAddAt, computeTarget, commitTarget, setArmedBoth, setTargetBoth]);

  const isEmpty = layout.sections.every(s => s.columns.every(c => c.widgets.length === 0));
  // Any edit-gesture in flight: dnd drag, click-grab, or an add-drag from the library.
  const dragging = activeId !== null || grabbedId !== null || addingWidgetId !== null;

  const hiddenZones = layout.hiddenZones ?? [];
  const mainSections = layout.sections.filter(s => (s.zone ?? 'main') === 'main');
  const leftSections = layout.sections.filter(s => s.zone === 'left');
  const rightSections = layout.sections.filter(s => s.zone === 'right');

  /** Render one zone's stack of sections (strips + rows) — all zones share the
   *  same DndContext so cards drag freely between centre and sides. */
  const renderZone = (sections: WorkspaceSection[]) => (
    <div className={cn('flex flex-col', dense ? 'gap-1.5' : 'gap-3')}>
      {sections.map((section, secIdx) => (
        <React.Fragment key={section.id}>
          {secIdx === 0 && (editMode || dragging) && (
            <NewSectionStrip
              anchorId={section.id} pos="above"
              dragging={dragging}
              isGrabbing={grabbedId !== null}
              isAdding={addingWidgetId !== null}
              onStripClick={() => {
                if (addingWidgetId) return; // add-project commits on click
                if (grabbedId) ops.moveWidgetToNewSectionAt(grabbedId, section.id, 'above');
                else ops.createSectionAt(section.id, 'above');
              }}
            />
          )}
          <SectionRow
            section={section}
            editMode={editMode}
            dragging={dragging}
            activeId={activeId}
            grabbedId={grabbedId}
            armedTarget={armedTarget}
            target={target}
            ops={ops}
            renderWidget={renderWidget}
            onResizeHeight={ops.setWidgetHeight}
            onCardTap={(id, coords) => {
              // Add-project in flight → card clicks are ignored (the ghost
              // already follows the pointer; double-click commits).
              if (addingWidgetId) return;
              // Click-to-pick-up model: a single click picks up a card
              // (floating ghost + live drop-line follow the cursor), a
              // single click on a target arms the preview, and a
              // double-click confirms. Same card click cancels.
              if (!grabbedId) setGrabbedId(id);
              else if (grabbedId === id) cancelGrab();
              else confirmOrArm(coords);
            }}
            lastDragEndRef={lastDragEndRef}
            onGhostConfirm={onGhostConfirm}
            onEmptyColumnClick={onEmptyColumnClick}
            dense={dense}
          />
          {(editMode || dragging) && (
            <NewSectionStrip
              anchorId={section.id} pos="below"
              dragging={dragging}
              isGrabbing={grabbedId !== null}
              isAdding={addingWidgetId !== null}
              onStripClick={() => {
                if (addingWidgetId) return; // add-project commits on click
                if (grabbedId) ops.moveWidgetToNewSectionAt(grabbedId, section.id, 'below');
                else ops.createSectionAt(section.id, 'below');
              }}
            />
          )}
        </React.Fragment>
      ))}
    </div>
  );

  /** Centre zone: the main sections, or a droppable placeholder when the centre
   *  has been emptied (so drops/adds still have a target). */
  const renderMain = () => (
    mainSections.length > 0
      ? renderZone(mainSections)
      : <EmptyMainZone
          dragging={dragging}
          grabbedId={grabbedId}
          isAdding={addingWidgetId !== null}
          onPlace={onEmptyColumnClick}
        />
  );

  return (
    <div
      className={cn('relative', className)}
      ref={rootRef}
      data-workspace
      onClick={(e) => {
        // Single click places a library add-project (the classic
        // "click to project, click to place"); double-click also confirms.
        if (addingWidgetId) commitAddAt(e.clientX, e.clientY);
      }}
      onDoubleClick={(e) => {
        if (!grabbedId && !addingWidgetId) return;
        e.preventDefault();
        commitOnDoubleClick(e.clientX, e.clientY);
      }}
    >
      {/* Compact edit bar — single slim row */}
      {editMode && !hideEditBar && (
        <div className={cn('glass-card sticky top-0 z-30 flex flex-wrap items-center gap-2 rounded-2xl px-3 py-2 shadow-lg shadow-black/20 animate-fade-in', dense ? 'mb-2' : 'mb-3')}>
          <span className="flex items-center gap-1.5 text-xs font-bold text-primary font-sans">
            <Columns3 size={14} /> Customizing
          </span>
          <span className="text-[10px] text-muted-foreground hidden md:inline">Drag to move · click to pick up, double-click to place · right-click / Esc cancels</span>
          <div className="ml-auto flex items-center gap-1.5">
            <button
              onClick={() => setDrawerOpen(v => !v)}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-bold transition-all cursor-pointer',
                drawerOpen
                  ? 'border-primary/40 bg-primary/15 text-primary'
                  : 'border-white/15 dark:border-white/10 bg-accent/30 hover:bg-accent/60 hover:border-primary/40 hover:text-primary text-muted-foreground',
              )}
            >
              <Plus size={13} /> Widgets / Templates
            </button>
            <button
              onClick={() => { setDrawerOpen(false); workspace.setEditMode(false); }}
              className="rounded-xl border border-primary/40 bg-primary/15 text-primary px-3 py-1.5 text-xs font-bold transition-all cursor-pointer"
            >
              Done
            </button>
          </div>
        </div>
      )}
      {editMode && drawerOpen && (
        <WorkspaceDrawer onClose={() => setDrawerOpen(false)} workspace={workspace} widgets={widgets} />
      )}
      {corrupt && (
        <div className="mb-4 rounded-2xl border border-amber-500/20 glass-card-subtle p-3.5 text-xs text-amber-400 font-semibold">
          Saved layout was unreadable — showing defaults. Your stored data was left untouched.
        </div>
      )}

      {isEmpty && (
        <div className="rounded-3xl glass-card p-12 text-center animate-fade-in-up">
          <Sparkles className="mx-auto text-primary" size={28} />
          <h3 className="mt-3 font-serif text-lg text-foreground">This workspace is empty</h3>
          <p className="mt-1 text-xs text-muted-foreground">Open <span className="font-bold text-primary">Customize</span> to add widgets and shape the layout.</p>
        </div>
      )}

      <DndContext
        sensors={sensors}
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
        onDragCancel={onDragCancel}
      >
        {(() => {
          const leftCfg = zones?.left;
          const rightCfg = zones?.right;
          const showLeft = leftSections.length > 0 && !hiddenZones.includes('left');
          const showRight = rightSections.length > 0 && !hiddenZones.includes('right');
          if (!showLeft && !showRight) return renderMain();

          const widths = layout.zoneWidths ?? {};

          /** One side column: collapsed → slim expand handle; else header + stack. */
          const zoneColumn = (
            zone: 'left' | 'right',
            sections: WorkspaceSection[],
            cfg: WorkspaceZoneConfig,
          ) => {
            if (cfg.collapsed) {
              return (
                <button
                  key={zone}
                  onClick={cfg.onToggle}
                  className="glass-card-subtle shrink-0 self-start rounded-xl p-2 text-muted-foreground hover:text-primary cursor-pointer"
                  title={`Open ${zone} panel`}
                >
                  {zone === 'left' ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
                </button>
              );
            }
            const w = widths[zone];
            return (
              <div
                key={zone}
                data-zone={zone}
                style={zonesSideBySide && w != null ? { width: w, flexShrink: 0 } : undefined}
                className={cn(
                  'shrink-0',
                  // Stacked below the main canvas on mobile, a side column from lg up.
                  zone === 'left' ? 'order-2 lg:order-none' : 'order-3 lg:order-none',
                  cfg.className ?? 'w-72',
                )}
              >
                {cfg.header}
                {renderZone(sections)}
              </div>
            );
          };

          const resizer = (zone: 'left' | 'right') => (
            <ZoneResizer zone={zone} onCommit={(px) => ops.setZoneWidth(zone, px)} />
          );

          return (
            <div ref={zoneRowRef} className={cn('flex flex-col items-stretch lg:flex-row lg:items-start', dense ? 'gap-1.5' : 'gap-4')}>
              {showLeft && leftCfg && zoneColumn('left', leftSections, leftCfg)}
              {showLeft && !leftCfg?.collapsed && resizer('left')}
              <div className="order-1 min-w-0 flex-1 lg:order-none">{renderMain()}</div>
              {showRight && !rightCfg?.collapsed && resizer('right')}
              {showRight && rightCfg && zoneColumn('right', rightSections, rightCfg)}
            </div>
          );
        })()}

        {(activePlacement || grabStateRef.current.id) && (
          <DragOverlay dropAnimation={null}>
            <div
              className={cn(CARD_CLASS, 'shadow-2xl shadow-black/50 rotate-[1.5deg] pointer-events-none opacity-95 px-4 py-3 flex items-center gap-2')}
              style={{ width: activeWidth }}
            >
              <GripVertical size={14} className="text-primary shrink-0" />
              <span className="font-serif text-sm font-semibold text-foreground truncate">
                {grabbedId ? grabStateRef.current.label : activeLabel}
              </span>
            </div>
          </DragOverlay>
        )}
      </DndContext>

      {/* Grab hint + cancel */}
      {grabbedId && (
        <div className="sticky bottom-4 z-40 mt-3 flex items-center justify-center gap-2 animate-fade-in">
          <div className="glass-card flex items-center gap-2 rounded-2xl px-3 py-2 shadow-lg shadow-black/30">
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground hidden md:inline">
              Click a spot to place (double-click confirms) · right-click / Esc cancels
            </span>
            <button
              onClick={cancelGrab}
              className="rounded-xl border border-border/40 bg-accent/30 hover:bg-accent/60 text-muted-foreground hover:text-foreground px-3 py-1.5 text-xs font-bold transition-all cursor-pointer"
            >Cancel</button>
          </div>
        </div>
      )}

      {/* Add-drag (library → canvas) hint + floating ghost. Rendered through a
          portal so fixed positioning is not trapped by a transformed ancestor. */}
      {addingWidgetId && (
        <div className="sticky bottom-4 z-40 mt-3 flex items-center justify-center gap-2 animate-fade-in">
          <div className="glass-card flex items-center gap-2 rounded-2xl px-3 py-2 shadow-lg shadow-black/30">
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground hidden md:inline">
              {addingMode === 'hold'
                ? `Drop ${addingLabel ?? 'the widget'} on a column or a “New section” strip · Esc cancels`
                : `Click a spot to place ${addingLabel ?? 'the widget'} (double-click confirms) · right-click / Esc cancels`}
            </span>
            <button
              onClick={() => onAddingEnd?.()}
              className="rounded-xl border border-border/40 bg-accent/30 hover:bg-accent/60 text-muted-foreground hover:text-foreground px-3 py-1.5 text-xs font-bold transition-all cursor-pointer"
            >Cancel</button>
          </div>
        </div>
      )}
      {addingWidgetId && addGhost && typeof document !== 'undefined' && createPortal(
        <div
          className="pointer-events-none fixed z-[60]"
          style={{ left: addGhost.x, top: addGhost.y, transform: 'translate(-50%, -50%)' }}
        >
          <div
            className={cn(CARD_CLASS, 'flex items-center gap-2 px-4 py-3 opacity-95 shadow-2xl shadow-black/50 rotate-[1.5deg]')}
            style={{ width: 280 }}
          >
            <Plus size={14} className="text-primary shrink-0" />
            <span className="font-serif text-sm font-semibold text-foreground truncate">{addingLabel ?? 'New widget'}</span>
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}

// ── Section row: columns + edit controls + resize handles ────────────────────

function SectionRow({
  section, editMode, dragging, activeId, grabbedId, armedTarget, target, ops, renderWidget, onResizeHeight, onCardTap, lastDragEndRef, onGhostConfirm, onEmptyColumnClick, dense,
}: {
  section: WorkspaceSection;
  editMode: boolean;
  dragging: boolean;
  activeId: string | null;
  grabbedId: string | null;
  armedTarget: DropTargetInfo | null;
  target: DropTargetInfo | null;
  ops: WC['ops'];
  renderWidget: (widgetId: string, placement: WidgetPlacement) => React.ReactNode;
  onResizeHeight: (widgetId: string, h: number | null) => void;
  onCardTap: (widgetInstanceId: string, coords?: { x: number; y: number }) => void;
  lastDragEndRef: React.MutableRefObject<number>;
  onGhostConfirm: () => void;
  onEmptyColumnClick: (coords: { x: number; y: number }) => void;
  dense: boolean;
}) {
  return (
    <div className={cn('rounded-2xl transition-all', dense ? 'p-0.5' : 'p-1')}>
      {/* Section edit controls */}
      {editMode && (
        <div className="mb-1.5 flex items-center gap-1.5 px-1">
          <span className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground/60">Section</span>
          <div className="flex items-center rounded-xl border border-white/15 dark:border-white/10 glass-card-subtle overflow-hidden">
            <button
              onClick={() => ops.setColumnCount(section.id, section.columns.length - 1)}
              disabled={section.columns.length <= 1}
              className="p-1 text-muted-foreground hover:text-primary disabled:opacity-30 cursor-pointer"
              title="Remove column"
            ><Minus size={12} /></button>
            <span className="px-1.5 text-[10px] font-mono text-muted-foreground">{section.columns.length}</span>
            <button
              onClick={() => ops.setColumnCount(section.id, section.columns.length + 1)}
              disabled={section.columns.length >= 4}
              className="p-1 text-muted-foreground hover:text-primary disabled:opacity-30 cursor-pointer"
              title="Add column"
            ><Plus size={12} /></button>
          </div>
          <button
            onClick={() => {
              const count = section.columns.reduce((a, c) => a + c.widgets.length, 0);
              if (count === 0 || confirm('Delete this section and its widgets?')) ops.removeSection(section.id);
            }}
            className="ml-1 rounded-xl border border-white/15 dark:border-white/10 glass-card-subtle p-1.5 text-muted-foreground hover:text-rose-400 hover:border-rose-500/40 transition-colors cursor-pointer"
            title="Delete this section"
          ><Trash2 size={12} /></button>
        </div>
      )}

      {/* items-start (not stretch): a short column must NOT grow to the height
          of its tallest sibling — that is what produced blank tail space under
          short widgets. Each card owns its own pinned height. */}
      <div className={cn('flex flex-col md:flex-row items-start', dense ? 'gap-1.5' : 'gap-2.5')}>
        {section.columns.map((column, colIdx) => (
          <React.Fragment key={column.id}>
            <ColumnDroppable
              column={column}
              section={section}
              editMode={editMode}
              dense={dense}
              dragging={dragging}
              activeId={activeId}
              grabbedId={grabbedId}
              armedTarget={armedTarget}
              target={target}
              ops={ops}
              renderWidget={renderWidget}
              onResizeHeight={onResizeHeight}
              onCardTap={onCardTap}
              lastDragEndRef={lastDragEndRef}
              onGhostConfirm={onGhostConfirm}
              onEmptyColumnClick={onEmptyColumnClick}
            />
            {editMode && colIdx < section.columns.length - 1 && (
              <ColumnWeightHandle columnId={column.id} section={section} ops={ops} />
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}

// ── Column with live insertion indicator + edge drop halves ──────────────────

function ColumnDroppable({
  column, section, editMode, dragging, activeId, grabbedId, armedTarget, target, ops, renderWidget, onResizeHeight, onCardTap, lastDragEndRef, onGhostConfirm, onEmptyColumnClick, dense,
}: {
  column: WorkspaceSection['columns'][number];
  section: WorkspaceSection;
  editMode: boolean;
  dragging: boolean;
  activeId: string | null;
  grabbedId: string | null;
  armedTarget: DropTargetInfo | null;
  target: DropTargetInfo | null;
  ops: WC['ops'];
  renderWidget: (widgetId: string, placement: WidgetPlacement) => React.ReactNode;
  onResizeHeight: (widgetId: string, h: number | null) => void;
  onCardTap: (widgetInstanceId: string, coords?: { x: number; y: number }) => void;
  lastDragEndRef: React.MutableRefObject<number>;
  /** Confirm the armed placement (ghost slot click). */
  onGhostConfirm: () => void;
  /** Click on an empty column while grabbing → arm/place into it. */
  onEmptyColumnClick: (coords: { x: number; y: number }) => void;
  dense: boolean;
}) {
  const { setNodeRef } = useDroppable({ id: idOf.col(column.id), data: { kind: 'col', columnId: column.id, sectionId: section.id } });

  const colIsTarget = target?.columnId === column.id;
  const edgeTarget = target?.columnId.startsWith('__newcol:')
    ? (target.columnId.split(':')[2] === column.id ? (target.columnId.split(':')[1] as 'before' | 'after') : null)
    : null;
  // Two-click confirm: this column holds the ARMED (previewed) position.
  const colIsArmed = armedTarget?.columnId === column.id;

  const widgets = column.widgets.map((placement, idx) => (
    <React.Fragment key={placement.id}>
      {colIsTarget && target.index === idx && <DropLine />}
      {colIsArmed && armedTarget.index === idx && <ConfirmGhost onConfirm={onGhostConfirm} />}
      <WidgetCard
        placement={placement}
        editMode={editMode}
        hidden={activeId === placement.id}
        tapActive={grabbedId === placement.id}
        lastDragEndRef={lastDragEndRef}
        ops={ops}
        renderWidget={renderWidget}
        onResizeHeight={onResizeHeight}
        onCardTap={onCardTap}
      />
    </React.Fragment>
  ));
  if (colIsTarget && target.index >= column.widgets.length) widgets.push(<DropLine key="drop-line-end" />);
  if (colIsArmed && armedTarget.index >= column.widgets.length) {
    widgets.push(<ConfirmGhost key="confirm-ghost-end" onConfirm={onGhostConfirm} />);
  }

  return (
    <div
      ref={setNodeRef}
      data-wcol={column.id}
      onClick={grabbedId && column.widgets.length === 0 ? (e) => {
        // Clicking an empty column while grabbing → arm/place into it.
        e.stopPropagation();
        onEmptyColumnClick({ x: e.clientX, y: e.clientY });
      } : undefined}
      className={cn(
        'relative flex flex-col min-h-[40px] min-w-0 flex-1 transition-all',
        dense ? 'gap-1.5' : 'gap-2.5',
        editMode && 'rounded-2xl outline-1 outline-dashed outline-border/20 p-1.5 -m-1.5',
        dragging && 'rounded-2xl outline-1 outline-dashed outline-border/30',
        colIsTarget && 'rounded-2xl outline-1 outline-dashed outline-primary/50',
        grabbedId && column.widgets.length === 0 && 'cursor-pointer',
      )}
      style={{ flexGrow: column.weight, flexBasis: 0 }}
    >
      {widgets}

      {/* Left/right edge halves → insert a new column beside this one.
          Rendered only during a drag: they're hit-targets for elementFromPoint,
          and would otherwise block grabbing cards at their edges. */}
      {dragging && <ColumnEdge side="L" column={column} section={section} hot={edgeTarget === 'before'} />}
      {dragging && <ColumnEdge side="R" column={column} section={section} hot={edgeTarget === 'after'} />}

      {/* Empty-column drop target — clickable in grab mode to arm/place. */}
      {column.widgets.length === 0 && (
        <button
          type="button"
          onClick={(e) => {
            if (grabbedId) {
              e.stopPropagation();
              onEmptyColumnClick({ x: e.clientX, y: e.clientY });
            }
            // Otherwise let the click bubble: during an add-project the canvas
            // commits the placement at the pointer; idle clicks are no-ops.
          }}
          className={cn(
            'flex min-h-[44px] flex-1 items-center justify-center rounded-xl border border-dashed border-white/15 dark:border-white/10 text-[10px] font-semibold text-muted-foreground/50 cursor-pointer',
            dragging && 'border-primary/40 text-primary/70',
            grabbedId && 'hover:border-primary/60 hover:text-primary/80',
          )}
        >
          {dragging ? 'Drop a widget here' : grabbedId ? 'Click to place here' : 'Empty column'}
        </button>
      )}
    </div>
  );
}

// ── Side-zone width resizer ──────────────────────────────────────────────────

/**
 * Vertical drag handle between a side zone and the centre. Dragging adjusts the
 * zone's width in real px (bounded), committing once on release so the layout
 * persists. Always available (both normal and edit mode) — resizing a panel is a
 * reading preference, not a customization.
 */
function ZoneResizer({ zone, onCommit }: {
  zone: 'left' | 'right';
  onCommit: (px: number) => void;
}) {
  const [hot, setHot] = useState(false);
  const onPointerDown = (e: React.PointerEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const handle = e.currentTarget as HTMLElement;
    const row = handle.parentElement;
    const panel = row?.querySelector<HTMLElement>(`[data-zone="${zone}"]`);
    if (!panel) return;
    const startX = e.clientX;
    const startW = panel.getBoundingClientRect().width;
    const dir = zone === 'left' ? 1 : -1; // left panel grows rightward
    document.body.style.userSelect = 'none';
    let lastW = startW;
    const onMove = (ev: PointerEvent) => {
      const next = Math.max(MIN_ZONE_WIDTH, Math.min(MAX_ZONE_WIDTH, Math.round(startW + dir * (ev.clientX - startX))));
      lastW = next;
      panel.style.width = `${next}px`;
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      document.body.style.userSelect = '';
      panel.style.width = '';
      onCommit(lastW);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };
  return (
    <div
      onPointerDown={onPointerDown}
      onMouseEnter={() => setHot(true)}
      onMouseLeave={() => setHot(false)}
      className={cn('group/zres shrink-0 self-stretch cursor-ew-resize hidden lg:block', 'w-2 -mx-1 rounded-full transition-colors')}
      title={`Drag to resize ${zone} panel`}
      data-nodrag
    >
      <div className={cn('mx-auto h-full w-0.5 rounded-full transition-colors', hot ? 'bg-primary/70' : 'bg-border/40')} />
    </div>
  );
}

// ── Draggable widget card ────────────────────────────────────────────────────

/**
 * A card is DEFINITE when it has a pinned height or a `defaultHeight` — its
 * body stretches to fill the frame (charts, lists). Otherwise it is CONTENT
 * driven and grows with its widget, with `minHeight` acting only as a floor.
 */
function isDefiniteCard(placement: WidgetPlacement): boolean {
  return placement.height != null || placement.defaultHeight != null;
}

/**
 * Inline size for a card.
 *  - `height`        → exact user-pinned height.
 *  - `defaultHeight` → a DEFINITE frame height (not a min). This matters: a
 *    frame card's body is `flex-1` with percentage/absolute-inset children
 *    (ECharts `absolute inset-0`, `h-full` map hosts). Those only resolve
 *    against a definite height — with `min-height` alone the flex body's height
 *    is ambiguous and the chart canvas collapses to 0px (the "blank charts"
 *    bug). Frames are meant to be fixed boxes whose widget fills/scrolls.
 *  - `minHeight`     → a floor under content that GROWS (compact tiles).
 */
function cardStyle(placement: WidgetPlacement): React.CSSProperties | undefined {
  if (placement.height != null) return { height: placement.height };
  if (placement.defaultHeight != null) return { height: placement.defaultHeight };
  if (placement.minHeight != null) return { minHeight: placement.minHeight };
  return undefined;
}

function WidgetCard({
  placement, editMode, hidden, tapActive, ops, renderWidget, onResizeHeight, onCardTap, lastDragEndRef,
}: {
  placement: WidgetPlacement;
  editMode: boolean;
  hidden: boolean;
  /** THIS card is the one being held in click-grab mode. */
  tapActive: boolean;
  ops: WC['ops'];
  renderWidget: (widgetId: string, placement: WidgetPlacement) => React.ReactNode;
  onResizeHeight: (widgetId: string, h: number | null) => void;
  onCardTap: (widgetInstanceId: string, coords?: { x: number; y: number }) => void;
  lastDragEndRef: React.MutableRefObject<number>;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: placement.id });

  // ── Height resize (bottom edge, edit mode) ─────────────────────────────────
  const onResizePointerDown = (e: React.PointerEvent) => {
    e.stopPropagation();
    e.preventDefault();
    const card = (e.currentTarget as HTMLElement).closest('[data-wcard]') as HTMLElement | null;
    if (!card) return;
    const startY = e.clientY;
    const startH = card.getBoundingClientRect().height;
    document.body.style.userSelect = 'none';

    let lastClientY = e.clientY;
    const onMove = (ev: PointerEvent) => {
      lastClientY = ev.clientY;
      card.style.height = `${Math.max(140, startH + ev.clientY - startY)}px`;
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      document.body.style.userSelect = '';
      // Commit from the TRACKED pointer delta. Clearing the inline preview style
      // first would let React re-render and reset the card to its stored height,
      // so measuring the DOM here read the stale size and the widget snapped
      // back to its previous height — the "resize keeps reverting" bug.
      const next = Math.max(140, startH + (lastClientY - startY));
      card.style.height = '';
      onResizeHeight(placement.id, next);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  return (
    <div
      ref={setNodeRef}
      data-wcard={placement.id}
      style={cardStyle(placement)}
      {...(editMode ? { ...attributes, ...listeners } : {})}
      onClick={editMode ? (e) => {
        // A genuine dnd-kit drag never produces a click (pointer capture).
        // A click arriving right after one does — ignore it; everything else
        // is a tap (grab / place / cancel).
        if (performance.now() - lastDragEndRef.current < 200) return;
        onCardTap(placement.id, { x: e.clientX, y: e.clientY });
      } : undefined}
      className={cn(
        CARD_CLASS,
        'group/card relative flex w-full flex-col overflow-hidden',
        // Sizing (see cardStyle): a pinned/default height makes the card a
        // definite frame and its BODY stretches to fill; a content-only card
        // grows with its widget. The body class below must match this choice.
        editMode ? 'cursor-grab active:cursor-grabbing' : 'cursor-default',
        // Touch: let the pointer sensor own the gesture — no browser pan.
        editMode && 'touch-none select-none',
        (hidden || isDragging) && 'opacity-30',
        tapActive && 'ring-2 ring-primary/70 opacity-80',
      )}
    >
      {editMode && (
        <div
          className="absolute right-2 top-2 z-30 flex items-center gap-1 opacity-0 group-hover/card:opacity-100 transition-opacity"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
        >
          <span
            {...(editMode ? { ...attributes, ...listeners } : {})}
            className="rounded-lg bg-background/80 border border-border/40 p-1 text-muted-foreground cursor-grab active:cursor-grabbing"
            title="Drag"
          >
            <GripVertical size={12} />
          </span>
          <button
            onClick={() => ops.moveWidgetToAdjacentColumn(placement.id, 'left')}
            className="rounded-lg bg-background/80 border border-border/40 p-1 text-muted-foreground hover:text-primary cursor-pointer"
            title="Move to column on the left"
          ><ChevronLeft size={12} /></button>
          <button
            onClick={() => ops.moveWidgetToAdjacentColumn(placement.id, 'right')}
            className="rounded-lg bg-background/80 border border-border/40 p-1 text-muted-foreground hover:text-primary cursor-pointer"
            title="Move to column on the right"
          ><ChevronRight size={12} /></button>
          <button
            onClick={() => ops.duplicateWidget(placement.id)}
            className="rounded-lg bg-background/80 border border-border/40 p-1 text-muted-foreground hover:text-primary cursor-pointer"
            title="Duplicate widget"
          ><Copy size={12} /></button>
          <button
            onClick={() => ops.toggleWidgetHidden(placement.id)}
            className={cn(
              'rounded-lg bg-background/80 border border-border/40 p-1 cursor-pointer',
              placement.hidden ? 'text-amber-400' : 'text-muted-foreground hover:text-primary',
            )}
            title={placement.hidden ? 'Unhide widget' : 'Hide widget'}
          ><EyeOff size={12} /></button>
          <button
            onClick={() => ops.removeWidget(placement.id)}
            className="rounded-lg bg-background/80 border border-border/40 p-1 text-muted-foreground hover:text-rose-400 cursor-pointer"
            title="Remove widget"
          ><X size={12} /></button>
        </div>
      )}
      {/* No overflow scroll on the card body: a widget must render FULL SIZE
          within its pinned height. The card itself is overflow-hidden, so
          content is clipped rather than showing an inner scrollbar. Widgets
          that need to scroll internally opt in themselves (scrollbar-hide).
          A definite card (pinned or `defaultHeight`) stretches its body to fill
          that frame; a content-only card lets the widget define the height (a
          flex-basis:0 body would otherwise collapse it). */}
      <div className={cn('flex flex-col', isDefiniteCard(placement) ? 'min-h-0 flex-1' : 'shrink-0')}>
        {placement.hidden ? (
          <div className="flex h-full items-center justify-center p-4">
            <span className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-2 py-1 text-[10px] font-semibold text-amber-400/80">
              Hidden — unhide in edit mode
            </span>
          </div>
        ) : (
          renderWidget(placement.widgetId, placement)
        )}
      </div>
      {editMode && (
        <div
          onPointerDown={onResizePointerDown}
          className="absolute inset-x-0 bottom-0 h-3 cursor-ns-resize z-30 flex items-end justify-center opacity-0 group-hover/card:opacity-100 transition-opacity"
          title="Drag to resize height"
        >
          <div className="mb-0.5 h-1 w-10 rounded-full bg-border" />
        </div>
      )}
    </div>
  );
}

// ── Column weight resize handle (float weights — re-resizable) ───────────────

function ColumnWeightHandle({ columnId, section, ops }: {
  columnId: string;
  section: WorkspaceSection;
  ops: WC['ops'];
}) {
  const onPointerDown = (e: React.PointerEvent) => {
    e.stopPropagation();
    e.preventDefault();
    const row = (e.currentTarget as HTMLElement).parentElement as HTMLElement | null;
    const sectionForRow = section;
    if (!row || sectionForRow.columns.length < 2) return;
    const target = row.querySelector<HTMLElement>(`[data-wcol="${columnId}"]`);
    if (!target) return;
    const colIdx = sectionForRow.columns.findIndex(c => c.id === columnId);
    if (colIdx === -1) return;
    const startX = e.clientX;
    const rowW = row.getBoundingClientRect().width;
    const gap = 10; // gap-2.5
    const totalW = Math.max(1, rowW - (sectionForRow.columns.length - 1) * gap);
    // px → weight conversion from the ACTUAL rendered geometry, so the live
    // preview matches the committed result exactly.
    const pxPerWeight = totalW / sectionForRow.columns.reduce((a, c) => a + c.weight, 0);
    const startWeights = sectionForRow.columns.map(c => c.weight);
    // The handle sits on the RIGHT edge of `columnId`: grow it by shrinking the
    // next column by the same px amount. That keeps the section total constant
    // (other columns never shift) and is fully reversible left↔right, which the
    // old single-weight approach was not — its clamped weight snapped back.
    const left = sectionForRow.columns[colIdx];
    const right = sectionForRow.columns[colIdx + 1];
    const leftId = left.id;
    const rightId = right.id;
    const startLeft = startWeights[colIdx];
    const startRight = startWeights[colIdx + 1];
    const minW = MIN_COLUMN_WEIGHT;
    let lastX = startX;
    document.body.style.userSelect = 'none';

    const compute = (clientX: number) => {
      // Desired delta in weight units, bounded so neither side leaves its range.
      const rawDelta = (clientX - startX) / pxPerWeight;
      const delta = Math.max(minW - startLeft, Math.min(startRight - minW, rawDelta));
      const round = (n: number) => Math.round(n * 10) / 10;
      const newLeft = round(startLeft + delta);
      // Round the pair sum so the two weights always add up to the same total.
      const newRight = round(startLeft + startRight - newLeft);
      return { left: newLeft, right: newRight };
    };

    const onMove = (ev: PointerEvent) => {
      lastX = ev.clientX;
      const { left: lw, right: rw } = compute(lastX);
      target.style.flexGrow = String(lw);
      const rightEl = row.querySelector<HTMLElement>(`[data-wcol="${rightId}"]`);
      if (rightEl) rightEl.style.flexGrow = String(rw);
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      document.body.style.userSelect = '';
      target.style.flexGrow = '';
      const rightEl = row.querySelector<HTMLElement>(`[data-wcol="${rightId}"]`);
      if (rightEl) rightEl.style.flexGrow = '';
      const { left: lw, right: rw } = compute(lastX);
      ops.setColumnWeights(sectionForRow.id, [
        { columnId: leftId, weight: lw },
        { columnId: rightId, weight: rw },
      ]);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  return (
    <div
      onPointerDown={onPointerDown}
      onClick={(e) => e.stopPropagation()}
      className="hidden md:flex w-1.5 shrink-0 items-center justify-center group/colres cursor-ew-resize"
      title="Drag to resize column width"
    >
      <div className="h-10 w-1 rounded-full bg-border group-hover/colres:bg-primary transition-colors" />
    </div>
  );
}
