'use client';

// ── WorkspaceCanvas — kernel edit chrome (dnd-kit) ───────────────────────────
// Renders sections/columns/cards and owns ALL drag/resize/hide chrome.
// Widgets stay pure: the page only supplies renderWidget(widgetId).
//
// Drag implementation is dnd-kit: PointerSensor on each card, droppable
// columns / new-column zones / new-section strip, and a DragOverlay ghost.
// Drop targets are resolved from dnd-kit collision detection; the tree is
// committed once on drag end via the workspace ops (Immer + Zustand store).

import React, { useEffect, useMemo, useState } from 'react';
import {
  DndContext, DragOverlay, PointerSensor, useSensor, useSensors,
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
  'rounded-2xl bg-[#0f0f0f]/60 dark:bg-[#0f0f0f]/60 bg-white/70 backdrop-blur-xl border border-white/10 dark:border-white/5 transition-all duration-300';

type OverKind = 'col' | 'newcol' | 'newsection';

/** Stable dnd ids: widget cards use their placement id; zones are prefixed. */
const idOf = {
  col: (columnId: string) => `col:${columnId}`,
  newcol: (sectionId: string) => `newcol:${sectionId}`,
  newsection: () => 'newsection',
};
const parseId = (id: string): { kind: OverKind; value: string } | null => {
  if (id === 'newsection') return { kind: 'newsection', value: '' };
  const [kind, value] = id.split(':');
  if (kind === 'col' || kind === 'newcol') return { kind, value: value ?? '' };
  return null;
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
  const [overId, setOverId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 4 },
    }),
  );

  // Index placement→location so drag-end can build a DropTarget without a DOM walk.
  const index = useMemo(() => {
    const m = new Map<string, { sectionId: string; columnId: string; index: number }>();
    layout.sections.forEach(s => s.columns.forEach(c => c.widgets.forEach((w, i) => m.set(w.id, { sectionId: s.id, columnId: c.id, index: i }))));
    return m;
  }, [layout]);

  const activePlacement = useMemo(() => {
    if (!activeId) return null;
    for (const s of layout.sections) for (const c of s.columns) {
      const w = c.widgets.find(x => x.id === activeId);
      if (w) return w;
    }
    return null;
  }, [activeId, layout]);

  useEffect(() => { ops.setDragging(activeId !== null); }, [activeId, ops]);

  const onDragStart = (e: DragStartEvent) => setActiveId(String(e.active.id));
  const onDragOver = (e: DragOverEvent) => setOverId(e.over ? String(e.over.id) : null);

  const onDragEnd = (e: DragEndEvent) => {
    const dragId = String(e.active.id);
    setActiveId(null);
    setOverId(null);
    if (!e.over) return;
    const parsed = parseId(String(e.over.id));
    if (!parsed) return;
    if (parsed.kind === 'newsection') {
      ops.moveWidgetToNewSection(dragId);
      return;
    }
    if (parsed.kind === 'newcol') {
      ops.moveWidget(dragId, { sectionId: parsed.value, columnId: null, index: 0 });
      return;
    }
    // Column target: insertion index of the dragged card among remaining siblings.
    const colId = parsed.value;
    const section = layout.sections.find(s => s.columns.some(c => c.id === colId));
    const column = section?.columns.find(c => c.id === colId);
    if (!section || !column) return;
    const origin = index.get(dragId);
    const siblings = column.widgets.filter(w => w.id !== dragId);
    let insert = siblings.length;
    if (origin && origin.columnId === colId && origin.index < siblings.length) {
      // Same column: dropping before position i keeps the card at i (after removal).
      insert = origin.index;
    } else {
      // Different column: dnd-kit doesn't give per-card hover indices here, so
      // use the hovered card's index within the target column.
      const overCard = e.over.data.current?.overIndex as number | undefined;
      insert = overCard != null ? Math.min(overCard, siblings.length) : siblings.length;
    }
    ops.moveWidget(dragId, { sectionId: section.id, columnId: colId, index: insert });
  };

  const isEmpty = layout.sections.every(s => s.columns.every(c => c.widgets.length === 0));

  return (
    <div className={cn('relative', className)} data-workspace>
      {/* Compact edit bar — never pushes content far: single slim row */}
      {editMode && (
        <div className="sticky top-0 z-30 mb-4 flex flex-wrap items-center gap-2 rounded-2xl border border-primary/30 bg-[#0f0f0f]/70 bg-white/70 backdrop-blur-xl px-3 py-2 animate-fade-in">
          <span className="flex items-center gap-1.5 text-xs font-bold text-primary font-sans">
            <Columns3 size={14} /> Customizing
          </span>
          <span className="text-[10px] text-muted-foreground hidden md:inline">Drag any card · drop on the dashed zones to create columns/sections</span>
          <div className="ml-auto flex items-center gap-1.5">
            <button
              onClick={() => setDrawerOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-border/40 bg-accent/30 hover:bg-accent/60 hover:border-primary/40 hover:text-primary text-muted-foreground px-3 py-1.5 text-xs font-bold transition-all cursor-pointer"
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
        onDragOver={onDragOver}
        onDragEnd={onDragEnd}
        onDragCancel={() => { setActiveId(null); setOverId(null); }}
      >
        <div className="flex flex-col gap-3">
          {layout.sections.map((section) => (
            <SectionRow
              key={section.id}
              section={section}
              editMode={editMode}
              dragging={dragging}
              activeId={activeId}
              overId={overId}
              ops={ops}
              renderWidget={renderWidget}
              onResizeHeight={ops.setWidgetHeight}
            />
          ))}
        </div>

        {/* New-section drop strip */}
        {(editMode || dragging) && !isEmpty && <NewSectionZone />}
        {activePlacement && (
          <DragOverlay dropAnimation={{ duration: 180, easing: 'cubic-bezier(0.18, 0.67, 0.6, 1.22)' }}>
            <div className={cn(CARD_CLASS, 'shadow-2xl shadow-black/40 rotate-[1.5deg] scale-[1.02] pointer-events-none opacity-95')} style={{ width: 360 }}>
              <div className="max-h-56 overflow-hidden pointer-events-none">
                {renderWidget(activePlacement.widgetId, activePlacement)}
              </div>
            </div>
          </DragOverlay>
        )}
      </DndContext>

      <WorkspaceDrawer
        open={editMode && drawerOpen}
        onClose={() => setDrawerOpen(false)}
        workspace={workspace}
        widgets={widgets}
      />
    </div>
  );
}

// ── Section row: columns + edit controls + resize handles ────────────────────

function SectionRow({
  section, editMode, dragging, activeId, overId, ops, renderWidget, onResizeHeight,
}: {
  section: WorkspaceSection;
  editMode: boolean;
  dragging: boolean;
  activeId: string | null;
  overId: string | null;
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
              overId={overId}
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
        {(editMode || dragging) && <NewColumnZone sectionId={section.id} overId={overId} />}
      </div>
    </div>
  );
}

// ── Droppable column with sortable-style cards ───────────────────────────────

function ColumnDroppable({
  column, section, editMode, dragging, activeId, overId, ops, renderWidget, onResizeHeight,
}: {
  column: WorkspaceSection['columns'][number];
  section: WorkspaceSection;
  editMode: boolean;
  dragging: boolean;
  activeId: string | null;
  overId: string | null;
  ops: WC['ops'];
  renderWidget: (widgetId: string, placement: WidgetPlacement) => React.ReactNode;
  onResizeHeight: (widgetId: string, h: number | null) => void;
}) {
  const colDndId = idOf.col(column.id);
  const { setNodeRef, isOver } = useDroppable({ id: colDndId, data: { kind: 'col', columnId: column.id, sectionId: section.id } });
  const hot = (isOver && activeId !== null) || (overId === colDndId && dragging);

  return (
    <div
      ref={setNodeRef}
      className={cn(
        'relative flex flex-col gap-2.5 min-h-[40px] min-w-0 flex-1',
        editMode && 'rounded-2xl outline-1 outline-dashed outline-border/20 p-1.5 -m-1.5',
        hot && 'outline-1 outline-dashed outline-primary/50 bg-primary/5',
      )}
      style={{ flexGrow: column.weight, flexBasis: 0 }}
    >
      {column.widgets.map((placement) => (
        <WidgetCard
          key={placement.id}
          placement={placement}
          columnId={column.id}
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
  placement, columnId, editMode, hidden, ops, renderWidget, onResizeHeight,
}: {
  placement: WidgetPlacement;
  columnId: string;
  editMode: boolean;
  hidden: boolean;
  ops: WC['ops'];
  renderWidget: (widgetId: string, placement: WidgetPlacement) => React.ReactNode;
  onResizeHeight: (widgetId: string, h: number | null) => void;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: placement.id, data: { columnId } });

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
      className={cn(
        CARD_CLASS,
        'group/card relative overflow-hidden',
        editMode ? 'cursor-grab active:cursor-grabbing' : 'cursor-default',
        (hidden || isDragging) && 'opacity-30',
      )}
    >
      {editMode && (
        <div className="absolute right-2 top-2 z-20 flex items-center gap-1 opacity-0 group-hover/card:opacity-100 transition-opacity" data-nodrag>
          <span
            {...attributes} {...listeners}
            className="rounded-lg bg-background/80 border border-border/40 p-1 text-muted-foreground cursor-grab active:cursor-grabbing"
            title="Drag"
          >
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
          data-nodrag
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

function NewColumnZone({ sectionId, overId }: { sectionId: string; overId: string | null }) {
  const dndId = idOf.newcol(sectionId);
  const { setNodeRef, isOver } = useDroppable({ id: dndId, data: { kind: 'newcol', sectionId } });
  return (
    <div
      ref={setNodeRef}
      className={cn(
        'hidden md:flex w-5 shrink-0 items-center justify-center rounded-xl border border-dashed text-muted-foreground/40 transition-all hover:border-primary/40 hover:text-primary',
        isOver && 'border-primary/60 text-primary bg-primary/5',
        overId === dndId && 'border-primary/60 text-primary',
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

// ── Column weight resize handle ──────────────────────────────────────────────

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
      // Live weight preview: scale current weight to the dragged pixel width.
      const w = Math.max(120, startW + ev.clientX - startX);
      target.style.flexGrow = String(Math.max(1, (w / total) * totalWeight));
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      document.body.style.userSelect = '';
      target.style.flexGrow = '';
      ops.setColumnWeight(columnId, Math.max(1, Math.min(6, Math.round((target.getBoundingClientRect().width / total) * totalWeight))));
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