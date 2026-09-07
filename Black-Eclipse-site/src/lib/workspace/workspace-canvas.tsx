'use client';

// ── WorkspaceCanvas — kernel edit chrome (dnd-kit) ───────────────────────────
// Renders sections/columns/cards and owns ALL drag/resize/hide chrome.
// Widgets stay pure: the page only supplies renderWidget(widgetId).
//
// Drag (KISS): whole card is draggable in edit mode; each column is the ONLY
// drop target (pointerWithin) and the card is appended to that column. The
// far-right "+" strip creates a new column; the bottom strip a new section.
// A lightweight labelled ghost follows the cursor.

import React, { useEffect, useMemo, useState } from 'react';
import {
  DndContext, DragOverlay, PointerSensor, useSensor, useSensors, pointerWithin,
  useDroppable, useDraggable, type DragStartEvent, type DragEndEvent, type DragOverEvent,
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

/** Stable dnd ids: columns / zones only — cards are not drop targets. */
const idOf = {
  col: (columnId: string) => `col:${columnId}`,
  newcol: (sectionId: string) => `newcol:${sectionId}`,
  newsection: () => 'newsection',
};

interface WorkspaceCanvasProps {
  workspace: WC;
  renderWidget: (widgetId: string, placement: WidgetPlacement) => React.ReactNode;
  widgets: WorkspaceWidgetMeta[];
  className?: string;
}

export function WorkspaceCanvas({ workspace, renderWidget, widgets, className }: WorkspaceCanvasProps) {
  const { layout, editMode, dragging, ops, corrupt } = workspace;
  const [activeId, setActiveId] = useState<string | null>(null);
  const [activeLabel, setActiveLabel] = useState('');
  const [activeWidth, setActiveWidth] = useState(360);
  const [overColId, setOverColId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

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

  const onDragOver = (e: DragOverEvent) => {
    const id = e.over ? String(e.over.id) : null;
    setOverColId(id?.startsWith('col:') ? id.slice(4) : null);
  };

  /** Pointer y for the current drag, from the activator event + accumulated delta. */
  const pointerY = (e: DragEndEvent): number => {
    const act = e.activatorEvent as PointerEvent | undefined;
    return (act?.clientY ?? 0) + e.delta.y;
  };

  /** Insertion index within a column for a pointer y — gaps between sibling cards. */
  const insertIndexFor = (colId: string, dragId: string, y: number): number => {
    const colEl = document.querySelector(`[data-wcol="${colId}"]`);
    if (!colEl) return Number.MAX_SAFE_INTEGER;
    const cards = Array.from(colEl.querySelectorAll<HTMLElement>('[data-wcard]'))
      .filter(el => el.getAttribute('data-wcard') !== dragId);
    for (let i = 0; i < cards.length; i++) {
      const r = cards[i].getBoundingClientRect();
      if (y < r.top + r.height / 2) return i;
    }
    return cards.length;
  };

  const onDragEnd = (e: DragEndEvent) => {
    const dragId = String(e.active.id);
    const overId = e.over ? String(e.over.id) : null;
    setActiveId(null);
    setOverColId(null);
    if (!overId) return;
    if (overId === idOf.newsection()) {
      ops.moveWidgetToNewSection(dragId);
      return;
    }
    if (overId.startsWith('newcol:')) {
      ops.moveWidget(dragId, { sectionId: overId.slice(7), columnId: null, index: 0 });
      return;
    }
    if (overId.startsWith('col:')) {
      const colId = overId.slice(4);
      const section = layout.sections.find(s => s.columns.some(c => c.id === colId));
      const column = section?.columns.find(c => c.id === colId);
      if (!section || !column) return;
      ops.moveWidget(dragId, { sectionId: section.id, columnId: colId, index: insertIndexFor(colId, dragId, pointerY(e)) });
    }
  };

  const isEmpty = layout.sections.every(s => s.columns.every(c => c.widgets.length === 0));

  return (
    <div className={cn('relative', className)} data-workspace>
      {/* Compact edit bar — single slim row */}
      {editMode && (
        <div className="sticky top-0 z-30 mb-3 flex flex-wrap items-center gap-2 rounded-2xl border border-white/15 dark:border-white/10 bg-[#0f0f0f]/70 dark:bg-[#0f0f0f]/70 bg-white/80 backdrop-blur-xl px-3 py-2 shadow-lg shadow-black/20 animate-fade-in">
          <span className="flex items-center gap-1.5 text-xs font-bold text-primary font-sans">
            <Columns3 size={14} /> Customizing
          </span>
          <span className="text-[10px] text-muted-foreground hidden md:inline">Drag any card · drop on a column · use the + zones for new columns/sections</span>
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
        collisionDetection={pointerWithin}
        onDragStart={onDragStart}
        onDragOver={onDragOver}
        onDragEnd={onDragEnd}
        onDragCancel={() => { setActiveId(null); setOverColId(null); }}
      >
        <div className="flex flex-col gap-3">
          {layout.sections.map((section) => (
            <SectionRow
              key={section.id}
              section={section}
              editMode={editMode}
              dragging={dragging}
              activeId={activeId}
              overColId={overColId}
              ops={ops}
              renderWidget={renderWidget}
              onResizeHeight={ops.setWidgetHeight}
            />
          ))}
        </div>

        {/* New-section drop strip */}
        {(editMode || dragging) && !isEmpty && <NewSectionZone />}
        {activePlacement && (
          <DragOverlay dropAnimation={null}>
            <div
              className={cn(CARD_CLASS, 'shadow-2xl shadow-black/50 rotate-[1.5deg] pointer-events-none opacity-95 px-4 py-3 flex items-center gap-2')}
              style={{ width: activeWidth }}
            >
              <GripVertical size={14} className="text-primary shrink-0" />
              <span className="font-serif text-sm font-semibold text-foreground truncate">{activeLabel}</span>
            </div>
          </DragOverlay>
        )}
      </DndContext>
    </div>
  );
}

// ── Section row: columns + edit controls + resize handles ────────────────────

function SectionRow({
  section, editMode, dragging, activeId, overColId, ops, renderWidget, onResizeHeight,
}: {
  section: WorkspaceSection;
  editMode: boolean;
  dragging: boolean;
  activeId: string | null;
  overColId: string | null;
  ops: WC['ops'];
  renderWidget: (widgetId: string, placement: WidgetPlacement) => React.ReactNode;
  onResizeHeight: (widgetId: string, h: number | null) => void;
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
              isHot={overColId === column.id}
              ops={ops}
              renderWidget={renderWidget}
              onResizeHeight={onResizeHeight}
            />
            {editMode && colIdx < section.columns.length - 1 && (
              <ColumnWeightHandle columnId={column.id} section={section} ops={ops} />
            )}
          </React.Fragment>
        ))}

        {/* New-column drop zone (drag) */}
        {(editMode || dragging) && <NewColumnZone sectionId={section.id} />}
      </div>
    </div>
  );
}

// ── Droppable column ─────────────────────────────────────────────────────────

function ColumnDroppable({
  column, section, editMode, dragging, activeId, isHot, ops, renderWidget, onResizeHeight,
}: {
  column: WorkspaceSection['columns'][number];
  section: WorkspaceSection;
  editMode: boolean;
  dragging: boolean;
  activeId: string | null;
  isHot: boolean;
  ops: WC['ops'];
  renderWidget: (widgetId: string, placement: WidgetPlacement) => React.ReactNode;
  onResizeHeight: (widgetId: string, h: number | null) => void;
}) {
  const { setNodeRef } = useDroppable({ id: idOf.col(column.id), data: { kind: 'col', columnId: column.id, sectionId: section.id } });

  return (
    <div
      ref={setNodeRef}
      data-wcol={column.id}
      className={cn(
        'relative flex flex-col gap-2.5 min-h-[40px] min-w-0 flex-1 transition-all',
        editMode && 'rounded-2xl outline-1 outline-dashed outline-border/20 p-1.5 -m-1.5',
        isHot && activeId !== null && 'rounded-2xl outline-2 outline-dashed outline-primary/70 bg-primary/10',
        dragging && !isHot && 'outline-1 outline-dashed outline-border/30',
      )}
      style={{ flexGrow: column.weight, flexBasis: 0 }}
    >
      {column.widgets.map((placement) => (
        <WidgetCard
          key={placement.id}
          placement={placement}
          editMode={editMode}
          hidden={activeId === placement.id}
          ops={ops}
          renderWidget={renderWidget}
          onResizeHeight={onResizeHeight}
        />
      ))}

      {/* Empty-column drop target */}
      {column.widgets.length === 0 && (
        <div className={cn(
          'flex min-h-[44px] flex-1 items-center justify-center rounded-xl border border-dashed border-border/30 text-[10px] font-semibold text-muted-foreground/50',
          (dragging || editMode) && 'border-primary/40 text-primary/70',
        )}>
          {dragging ? 'Drop a widget here' : editMode ? 'Drop a widget here' : 'Empty column'}
        </div>
      )}
    </div>
  );
}

// ── Draggable widget card ────────────────────────────────────────────────────

function WidgetCard({
  placement, editMode, hidden, ops, renderWidget, onResizeHeight,
}: {
  placement: WidgetPlacement;
  editMode: boolean;
  hidden: boolean;
  ops: WC['ops'];
  renderWidget: (widgetId: string, placement: WidgetPlacement) => React.ReactNode;
  onResizeHeight: (widgetId: string, h: number | null) => void;
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

    const onMove = (ev: PointerEvent) => {
      card.style.height = `${Math.max(140, startH + ev.clientY - startY)}px`;
    };
    const onUp = (ev: PointerEvent) => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      document.body.style.userSelect = '';
      onResizeHeight(placement.id, startH + ev.clientY - startY);
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
      className={cn(
        CARD_CLASS,
        'group/card relative overflow-hidden',
        editMode ? 'cursor-grab active:cursor-grabbing' : 'cursor-default',
        (hidden || isDragging) && 'opacity-30',
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
      <div className={cn('h-full', placement.height != null && 'overflow-y-auto')}>
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

function NewColumnZone({ sectionId }: { sectionId: string }) {
  const dndId = idOf.newcol(sectionId);
  const { setNodeRef, isOver } = useDroppable({ id: dndId, data: { kind: 'newcol', sectionId } });
  return (
    <div
      ref={setNodeRef}
      className={cn(
        'hidden md:flex w-6 shrink-0 items-center justify-center rounded-xl border border-dashed transition-all',
        isOver ? 'border-primary/60 text-primary bg-primary/10' : 'border-border/30 text-muted-foreground/40',
      )}
      title="Drop here to create a new column"
    >
      <Plus size={12} />
    </div>
  );
}

function NewSectionZone() {
  const { setNodeRef, isOver } = useDroppable({ id: idOf.newsection(), data: { kind: 'newsection' } });
  return (
    <div
      ref={setNodeRef}
      className={cn(
        'mt-3 flex h-11 items-center justify-center gap-2 rounded-2xl border border-dashed text-[10px] font-bold uppercase tracking-widest transition-all',
        isOver
          ? 'border-primary bg-primary/10 text-primary'
          : 'border-primary/50 text-primary animate-fade-in',
      )}
    >
      <Plus size={12} /> {isOver ? 'Release to create a section' : 'Drop here for a new section'}
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
    const onUp = (ev: PointerEvent) => {
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