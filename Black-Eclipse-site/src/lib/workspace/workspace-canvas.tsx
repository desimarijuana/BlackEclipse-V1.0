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
import {
  DndContext, DragOverlay, PointerSensor, useSensor, useSensors,
  useDroppable, useDraggable, type DragStartEvent,
} from '@dnd-kit/core';
import {
  Columns3, GripVertical, Minus, Plus, Scan, Sparkles, X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { WorkspaceDrawer, type WorkspaceWidgetMeta } from './workspace-drawer';
import type { WidgetPlacement, WorkspaceSection } from './types';
import type { WorkspaceController as WC } from './use-workspace';

const CARD_CLASS =
  'rounded-2xl bg-[#0f0f0f]/60 dark:bg-[#0f0f0f]/60 bg-white/70 backdrop-blur-xl border border-white/15 dark:border-white/15 shadow-md shadow-black/10 transition-all duration-300';

/** Where the dragged card should land (kept in a ref for the commit + state for the UI). */
interface DropTargetInfo {
  sectionId: string;
  columnId: string;
  index: number;
}

/** Stable dnd ids: columns / edges / zones only — cards are not drop targets. */
const idOf = {
  col: (columnId: string) => `col:${columnId}`,
  colEdgeL: (columnId: string) => `edgeL:${columnId}`,
  colEdgeR: (columnId: string) => `edgeR:${columnId}`,
  newsection: (anchorId: string, pos: 'above' | 'below') => `newsec:${anchorId}:${pos}`,
};

interface WorkspaceCanvasProps {
  workspace: WC;
  renderWidget: (widgetId: string, placement: WidgetPlacement) => React.ReactNode;
  widgets: WorkspaceWidgetMeta[];
  className?: string;
}

export function WorkspaceCanvas({ workspace, renderWidget, widgets, className }: WorkspaceCanvasProps) {
  const { layout, editMode, ops, corrupt } = workspace;
  const [activeId, setActiveId] = useState<string | null>(null);
  const [activeLabel, setActiveLabel] = useState('');
  const [activeWidth, setActiveWidth] = useState(360);
  const [target, setTarget] = useState<DropTargetInfo | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

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
    const el = document.elementFromPoint(px, py);
    if (!el) return null;

    // 1) Inter-section strips → new section above/below the anchor.
    const strip = el.closest<HTMLElement>('[data-newsec]');
    if (strip) {
      const [anchorId, pos] = strip.dataset.newsec!.split(':') as [string, 'above' | 'below'];
      return { sectionId: anchorId, columnId: `__newsec:${anchorId}:${pos}`, index: 0 };
    }

    // 2) Left/right edges of a column → new column beside it.
    const edge = el.closest<HTMLElement>('[data-edge]');
    if (edge) {
      const { edge: side, col, sec } = edge.dataset as { edge: 'L' | 'R'; col: string; sec: string };
      return { sectionId: sec, columnId: `__newcol:${side === 'L' ? 'before' : 'after'}:${col}`, index: 0 };
    }

    // 3) Column interior → projected insertion index between cards.
    const colEl = el.closest<HTMLElement>('[data-wcol]');
    if (colEl) {
      const colId = colEl.dataset.wcol!;
      const section = layoutRef.current.sections.find(s => s.columns.some(c => c.id === colId));
      if (!section) return null;
      return { sectionId: section.id, columnId: colId, index: insertIndexFor(colEl, dragId, py) };
    }

    return null;
  }, []);

  // Track the live pointer while dragging; drive the drop target from it.
  useEffect(() => {
    if (!activeId) return;
    let raf = 0;
    let lastX = -1, lastY = -1;
    const onMove = (ev: PointerEvent) => {
      lastX = ev.clientX; lastY = ev.clientY;
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        setTargetBoth(computeTarget(lastX, lastY, activeId));
      });
    };
    window.addEventListener('pointermove', onMove, { passive: true });
    window.addEventListener('pointerdown', onMove, { passive: true });
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerdown', onMove);
      if (raf) cancelAnimationFrame(raf);
      setTargetBoth(null);
    };
  }, [activeId, computeTarget, setTargetBoth]);

  // Auto-scroll the nearest scrollable ancestor(s) toward the pointer while
  // dragging so off-screen rows are reachable (dnd-kit skips auto-scroll once
  // a DragOverlay is rendered, so we provide it ourselves).
  useEffect(() => {
    if (!activeId) return;
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
  }, [activeId]);

  const onDragEnd = () => {
    const dragId = activeId;
    setActiveId(null);
    const t = targetRef.current;
    setTargetBoth(null);
    if (!dragId || !t) return;
    if (t.columnId.startsWith('__newsec:')) {
      const [, anchorId, pos] = t.columnId.split(':') as [string, string, 'above' | 'below'];
      ops.moveWidgetToNewSectionAt(dragId, anchorId, pos);
      return;
    }
    if (t.columnId.startsWith('__newcol:')) {
      const [, when, anchorColId] = t.columnId.split(':') as [string, string, 'before' | 'after'];
      const section = layoutRef.current.sections.find(s => s.columns.some(c => c.id === anchorColId));
      const colIdx = section?.columns.findIndex(c => c.id === anchorColId) ?? -1;
      if (!section || colIdx === -1) return;
      ops.moveWidget(dragId, {
        sectionId: section.id,
        columnId: null,
        index: 0,
        columnIndex: when === 'before' ? colIdx : colIdx + 1,
      });
      return;
    }
    ops.moveWidget(dragId, { sectionId: t.sectionId, columnId: t.columnId, index: t.index });
  };

  /** Click-to-grab fallback for touchpads/touchscreens where drag pan-gestures fight the pointer sensor. */
  const [grabbedId, setGrabbedId] = useState<string | null>(null);

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

  /** Commit the grabbed card to the current projected target (or clear). */
  const releaseGrab = useCallback(() => {
    const id = grabStateRef.current.id;
    const t = targetRef.current;
    setGrabbedId(null);
    setTargetBoth(null);
    if (!id) return;
    // Click on the card itself (no target) = cancel.
    if (!t) return;
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
  }, [ops, setTargetBoth]);

  const onDragCancel = () => { setActiveId(null); setTargetBoth(null); };

  const isEmpty = layout.sections.every(s => s.columns.every(c => c.widgets.length === 0));

  return (
    <div className={cn('relative', className)} data-workspace>
      {/* Compact edit bar — single slim row */}
      {editMode && (
        <div className="ws-glass sticky top-0 z-30 mb-3 flex flex-wrap items-center gap-2 rounded-2xl px-3 py-2 shadow-lg shadow-black/20 animate-fade-in">
          <span className="flex items-center gap-1.5 text-xs font-bold text-primary font-sans">
            <Columns3 size={14} /> Customizing
          </span>
          <span className="text-[10px] text-muted-foreground hidden md:inline">Drag a card — release between cards, at a column edge, or on a row strip</span>
          <div className="ml-auto flex items-center gap-1.5">
            <button
              onClick={() => setDrawerOpen(v => !v)}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-bold transition-all cursor-pointer',
                drawerOpen
                  ? 'border-primary/40 bg-primary/15 text-primary'
                  : 'border-border/40 bg-accent/30 hover:bg-accent/60 hover:border-primary/40 hover:text-primary text-muted-foreground',
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
        <div className="mb-4 rounded-2xl border border-amber-500/20 bg-amber-500/5 backdrop-blur-md p-3.5 text-xs text-amber-400 font-semibold">
          Saved layout was unreadable — showing defaults. Your stored data was left untouched.
        </div>
      )}

      {isEmpty && (
        <div className="rounded-3xl bg-[#0f0f0f]/60 dark:bg-[#0f0f0f]/60 bg-white/70 backdrop-blur-xl border border-white/10 dark:border-white/5 p-12 text-center animate-fade-in-up">
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
        <div className="flex flex-col gap-3">
          {layout.sections.map((section, secIdx) => (
            <React.Fragment key={section.id}>
              {secIdx === 0 && (editMode || activeId !== null || grabbedId !== null) && (
                <NewSectionStrip
                  anchorId={section.id} pos="above"
                  dragging={activeId !== null || grabbedId !== null}
                  isGrabbing={grabbedId !== null}
                  onStripClick={() => grabbedId ? releaseGrab() : ops.createSectionAt(section.id, 'above')}
                />
              )}
              <SectionRow
                section={section}
                editMode={editMode}
                dragging={activeId !== null || grabbedId !== null}
                activeId={activeId}
                grabbedId={grabbedId}
                target={target}
                ops={ops}
                renderWidget={renderWidget}
                onResizeHeight={ops.setWidgetHeight}
                onCardTap={(id) => {
                  // Tap-to-grab / tap-to-place fallback for touch devices.
                  if (!grabbedId) setGrabbedId(id);
                  else if (grabbedId === id) setGrabbedId(null); // tap again = cancel
                  else releaseGrab();
                }}
              />
              {(editMode || activeId !== null || grabbedId !== null) && (
                <NewSectionStrip
                  anchorId={section.id} pos="below"
                  dragging={activeId !== null || grabbedId !== null}
                  isGrabbing={grabbedId !== null}
                  onStripClick={() => grabbedId ? releaseGrab() : ops.createSectionAt(section.id, 'below')}
                />
              )}
            </React.Fragment>
          ))}
        </div>

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
    </div>
  );
}

// ── Section row: columns + edit controls + resize handles ────────────────────

function SectionRow({
  section, editMode, dragging, activeId, grabbedId, target, ops, renderWidget, onResizeHeight, onCardTap,
}: {
  section: WorkspaceSection;
  editMode: boolean;
  dragging: boolean;
  activeId: string | null;
  grabbedId: string | null;
  target: DropTargetInfo | null;
  ops: WC['ops'];
  renderWidget: (widgetId: string, placement: WidgetPlacement) => React.ReactNode;
  onResizeHeight: (widgetId: string, h: number | null) => void;
  onCardTap: (widgetInstanceId: string) => void;
}) {
  return (
    <div className="rounded-2xl p-1 transition-all">
      {/* Section edit controls */}
      {editMode && (
        <div className="mb-1.5 flex items-center gap-1.5 px-1">
          <span className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground/60">Section</span>
          <div className="flex items-center rounded-xl border border-border/40 bg-accent/30 overflow-hidden">
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
        </div>
      )}

      <div className="flex flex-col md:flex-row gap-2.5 items-stretch">
        {section.columns.map((column, colIdx) => (
          <React.Fragment key={column.id}>
            <ColumnDroppable
              column={column}
              section={section}
              editMode={editMode}
              dragging={dragging}
              activeId={activeId}
              grabbedId={grabbedId}
              target={target}
              ops={ops}
              renderWidget={renderWidget}
              onResizeHeight={onResizeHeight}
              onCardTap={onCardTap}
            />
            {colIdx < section.columns.length - 1 && (
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
  column, section, editMode, dragging, activeId, grabbedId, target, ops, renderWidget, onResizeHeight, onCardTap,
}: {
  column: WorkspaceSection['columns'][number];
  section: WorkspaceSection;
  editMode: boolean;
  dragging: boolean;
  activeId: string | null;
  grabbedId: string | null;
  target: DropTargetInfo | null;
  ops: WC['ops'];
  renderWidget: (widgetId: string, placement: WidgetPlacement) => React.ReactNode;
  onResizeHeight: (widgetId: string, h: number | null) => void;
  onCardTap: (widgetInstanceId: string) => void;
}) {
  const { setNodeRef } = useDroppable({ id: idOf.col(column.id), data: { kind: 'col', columnId: column.id, sectionId: section.id } });

  const colIsTarget = target?.columnId === column.id;
  const edgeTarget = target?.columnId.startsWith('__newcol:')
    ? (target.columnId.split(':')[2] === column.id ? (target.columnId.split(':')[1] as 'before' | 'after') : null)
    : null;

  const widgets = column.widgets.map((placement, idx) => (
    <React.Fragment key={placement.id}>
      {colIsTarget && target.index === idx && <DropLine />}
      <WidgetCard
        placement={placement}
        editMode={editMode}
        hidden={activeId === placement.id}
        tapActive={grabbedId === placement.id}
        ops={ops}
        renderWidget={renderWidget}
        onResizeHeight={onResizeHeight}
        isLast={idx === column.widgets.length - 1}
        onCardTap={onCardTap}
      />
    </React.Fragment>
  ));
  if (colIsTarget && target.index >= column.widgets.length) widgets.push(<DropLine key="drop-line-end" />);

  return (
    <div
      ref={setNodeRef}
      data-wcol={column.id}
      className={cn(
        'relative flex flex-col gap-2.5 min-h-[40px] min-w-0 flex-1 transition-all',
        editMode && 'rounded-2xl outline-1 outline-dashed outline-border/20 p-1.5 -m-1.5',
        dragging && 'rounded-2xl outline-1 outline-dashed outline-border/30',
        colIsTarget && 'rounded-2xl outline-1 outline-dashed outline-primary/50',
      )}
      style={{ flexGrow: column.weight, flexBasis: 0 }}
    >
      {widgets}

      {/* Left/right edge halves → insert a new column beside this one.
          Rendered only during a drag: they're hit-targets for elementFromPoint,
          and would otherwise block grabbing cards at their edges. */}
      {dragging && <ColumnEdge side="L" column={column} section={section} hot={edgeTarget === 'before'} />}
      {dragging && <ColumnEdge side="R" column={column} section={section} hot={edgeTarget === 'after'} />}

      {/* Empty-column drop target */}
      {column.widgets.length === 0 && !colIsTarget && (
        <div className={cn(
          'flex min-h-[44px] flex-1 items-center justify-center rounded-xl border border-dashed border-border/30 text-[10px] font-semibold text-muted-foreground/50',
          dragging && 'border-primary/40 text-primary/70',
        )}>
          {dragging ? 'Drop a widget here' : 'Empty column'}
        </div>
      )}
    </div>
  );
}

function DropLine() {
  return <div className="ws-drop-indicator" aria-hidden />;
}

// ── Draggable widget card ────────────────────────────────────────────────────

function WidgetCard({
  placement, editMode, hidden, tapActive, ops, renderWidget, onResizeHeight, isLast, onCardTap,
}: {
  placement: WidgetPlacement;
  editMode: boolean;
  hidden: boolean;
  /** THIS card is the one being held in click-grab mode. */
  tapActive: boolean;
  ops: WC['ops'];
  renderWidget: (widgetId: string, placement: WidgetPlacement) => React.ReactNode;
  onResizeHeight: (widgetId: string, h: number | null) => void;
  isLast?: boolean;
  onCardTap: (widgetInstanceId: string) => void;
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
      onResizeHeight(placement.id, startH + (lastClientY - startY));
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  return (
    <div
      ref={setNodeRef}
      data-wcard={placement.id}
      style={placement.height != null ? { height: placement.height } : undefined}
      {...(editMode ? { ...attributes, ...listeners } : {})}
      onClick={editMode ? (e) => {
        // Only treat as a "tap" when the click wasn't a real drag (dnd-kit
        // keeps pointer capture; a genuine drag won't produce a click here).
        const moved = (e as unknown as { detail?: number }).detail === 0;
        if (!moved) onCardTap(placement.id);
      } : undefined}
      className={cn(
        CARD_CLASS,
        'group/card relative flex w-full flex-col overflow-hidden',
        // Fixed-height cards keep their size; auto cards fill leftover column
        // space (last one absorbs the remainder) so columns never show gaps.
        placement.height == null && (isLast ? 'flex-1' : 'flex-none'),
        editMode ? 'cursor-grab active:cursor-grabbing' : 'cursor-default',
        // Touch: let the pointer sensor own the gesture — no browser pan.
        editMode && 'touch-none select-none',
        (hidden || isDragging) && 'opacity-30',
        tapActive && 'ring-2 ring-primary/70 opacity-80',
      )}
    >
      {editMode && (
        <div
          className="absolute right-2 top-2 z-20 flex items-center gap-1 opacity-0 group-hover/card:opacity-100 transition-opacity"
          onPointerDown={(e) => e.stopPropagation()}
        >
          <span className="rounded-lg bg-background/80 border border-border/40 p-1 text-muted-foreground cursor-grab" title="Drag">
            <GripVertical size={12} />
          </span>
          <button
            onClick={() => ops.setWidgetHeight(placement.id, null)}
            className="rounded-lg bg-background/80 border border-border/40 p-1 text-muted-foreground hover:text-primary cursor-pointer"
            title="Fit height"
          ><Scan size={12} /></button>
          <button
            onClick={() => ops.removeWidget(placement.id)}
            className="rounded-lg bg-background/80 border border-border/40 p-1 text-muted-foreground hover:text-rose-400 cursor-pointer"
            title="Remove widget"
          ><X size={12} /></button>
        </div>
      )}
      <div className={cn('min-h-0 flex-1', placement.height != null && 'overflow-y-auto')}>
        {renderWidget(placement.widgetId, placement)}
      </div>
      {editMode && (
        <div
          onPointerDown={onResizePointerDown}
          className="absolute inset-x-0 bottom-0 h-3 cursor-ns-resize z-20 flex items-end justify-center opacity-0 group-hover/card:opacity-100 transition-opacity"
          title="Drag to resize height"
        >
          <div className="mb-0.5 h-1 w-10 rounded-full bg-border" />
        </div>
      )}
    </div>
  );
}

// ── Zones ────────────────────────────────────────────────────────────────────

/** Invisible left/right half of a column: dropping here creates a new column. */
function ColumnEdge({ side, column, section, hot }: {
  side: 'L' | 'R';
  column: WorkspaceSection['columns'][number];
  section: WorkspaceSection;
  hot: boolean;
}) {
  const dndId = side === 'L' ? idOf.colEdgeL(column.id) : idOf.colEdgeR(column.id);
  const { setNodeRef } = useDroppable({
    id: dndId,
    data: { kind: 'edge', side, columnId: column.id, sectionId: section.id },
  });
  return (
    <div
      ref={setNodeRef}
      data-edge={side}
      data-col={column.id}
      data-sec={section.id}
      className={cn(
        'absolute inset-y-0 z-10 w-[16%] min-w-[10px]',
        side === 'L' ? 'left-0 rounded-l-2xl' : 'right-0 rounded-r-2xl',
        hot ? 'bg-primary/10 outline-1 outline-dashed outline-primary/60' : 'bg-transparent',
      )}
      title={side === 'L' ? 'Drop to insert a column to the left' : 'Drop to insert a column to the right'}
    />
  );
}

/** Slim strip between/around sections: dropping (or clicking) creates a new
 * section there. While a card is click-grabbed, clicking commits the grab. */
function NewSectionStrip({ anchorId, pos, dragging, isGrabbing, onStripClick }: {
  anchorId: string;
  pos: 'above' | 'below';
  dragging: boolean;
  isGrabbing: boolean;
  onStripClick: () => void;
}) {
  const dndId = idOf.newsection(anchorId, pos);
  const { setNodeRef, isOver } = useDroppable({ id: dndId, data: { kind: 'newsec', anchorId, pos } });
  return (
    <button
      ref={setNodeRef}
      type="button"
      data-newsec={`${anchorId}:${pos}`}
      data-nodrag
      onClick={(e) => { e.stopPropagation(); onStripClick(); }}
      className={cn(
        'flex h-7 items-center justify-center gap-2 rounded-xl border border-dashed text-[9px] font-bold uppercase tracking-widest transition-all cursor-pointer touch-none',
        dragging ? 'opacity-100' : 'opacity-40 hover:opacity-100',
        isOver
          ? 'border-primary bg-primary/10 text-primary'
          : 'border-primary/40 text-primary/70',
      )}
    >
      <Plus size={11} />
      {isGrabbing
        ? (isOver ? 'Release to place here' : 'Click to place the held card here')
        : isOver ? 'Release for a new section' : 'New section here'}
    </button>
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
    if (!row || section.columns.length < 2) return;
    const total = row.getBoundingClientRect().width - (section.columns.length - 1) * 10; // gap-2.5
    const startX = e.clientX;
    const target = row.querySelector<HTMLElement>(`[data-wcol="${columnId}"]`);
    if (!target) return;
    const startW = target.getBoundingClientRect().width;
    const totalWeight = section.columns.reduce((a, c) => a + c.weight, 0);
    document.body.style.userSelect = 'none';

    const onMove = (ev: PointerEvent) => {
      const w = Math.max(120, startW + ev.clientX - startX);
      target.style.flexGrow = String(Math.max(0.4, (w / total) * totalWeight));
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      document.body.style.userSelect = '';
      target.style.flexGrow = '';
      // Float weight rounded to 0.1 — integer weights quantized so a second
      // resize often produced the same value (the "can't resize twice" bug).
      const w = Math.max(0.4, (target.getBoundingClientRect().width / total) * totalWeight);
      ops.setColumnWeight(columnId, Math.round(w * 10) / 10);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  return (
    <div
      onPointerDown={onPointerDown}
      className="hidden md:flex w-1.5 shrink-0 items-center justify-center group/colres cursor-ew-resize"
      title="Drag to resize column width"
    >
      <div className="h-10 w-1 rounded-full bg-border group-hover/colres:bg-primary transition-colors" />
    </div>
  );
}