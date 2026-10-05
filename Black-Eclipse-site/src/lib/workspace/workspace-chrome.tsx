'use client';

// ── Workspace drop chrome ────────────────────────────────────────────────────
// The small droppable affordances shared by WorkspaceCanvas: drop lines,
// confirm ghosts, column edges, inter-section "new section" strips and the
// empty-centre placeholder. Split out of workspace-canvas.tsx to keep that
// kernel file within its size budget.

import React from 'react';
import { useDroppable } from '@dnd-kit/core';
import { GripVertical, Plus, Sparkles } from '@/lib/icons';
import { cn } from '@/lib/utils';
import type { WorkspaceSection } from './types';

/** Stable dnd ids: columns / edges / zones only — cards are not drop targets. */
export const idOf = {
  col: (columnId: string) => `col:${columnId}`,
  colEdgeL: (columnId: string) => `edgeL:${columnId}`,
  colEdgeR: (columnId: string) => `edgeR:${columnId}`,
  newsection: (anchorId: string, pos: 'above' | 'below') => `newsec:${anchorId}:${pos}`,
};

export function DropLine() {
  return <div className="ws-drop-indicator" aria-hidden />;
}

/** Armed-position preview (two-click confirm): a labeled ghost slot. Clicking
 *  it confirms the placement (same as clicking the spot again). */
export function ConfirmGhost({ onConfirm }: { onConfirm: () => void }) {
  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); onConfirm(); }}
      className="w-full rounded-2xl border-2 border-dashed border-primary/70 bg-primary/10 px-4 py-3 flex items-center gap-2 animate-fade-in cursor-pointer text-left"
    >
      <GripVertical size={14} className="text-primary shrink-0" />
      <span className="font-serif text-sm font-semibold text-primary truncate">Click again to confirm</span>
    </button>
  );
}

/** Invisible left/right half of a column: dropping here creates a new column. */
export function ColumnEdge({ side, column, section, hot }: {
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
        'absolute inset-y-0 z-10 w-2',
        side === 'L' ? 'left-0 rounded-l-2xl' : 'right-0 rounded-r-2xl',
        hot ? 'bg-primary/10 outline-1 outline-dashed outline-primary/60' : 'bg-transparent',
      )}
      title={side === 'L' ? 'Drop to insert a column to the left' : 'Drop to insert a column to the right'}
    />
  );
}

/** Slim strip between/around sections: dropping (or clicking) creates a new
 * section there. While a card is click-grabbed, clicking commits the grab. */
export function NewSectionStrip({ anchorId, pos, dragging, isGrabbing, isAdding, onStripClick }: {
  anchorId: string;
  pos: 'above' | 'below';
  dragging: boolean;
  isGrabbing: boolean;
  isAdding: boolean;
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
      onClick={(e) => {
        // During an add-project the click must bubble to the canvas so it
        // commits the placement (including "new section" targets).
        if (isAdding) return;
        e.stopPropagation();
        onStripClick();
      }}
      className={cn(
        'flex h-7 items-center justify-center gap-2 rounded-xl border border-dashed text-[9px] font-bold uppercase tracking-widest transition-all cursor-pointer touch-none',
        dragging ? 'opacity-100' : 'opacity-40 hover:opacity-100',
        isOver
          ? 'border-primary bg-primary/10 text-primary'
          : 'border-primary/40 text-primary/70',
      )}
    >
      <Plus size={11} />
      {isGrabbing || isAdding
        ? (isOver ? 'Click to place here' : 'Click to place the held widget here')
        : isOver ? 'Release for a new section' : 'New section here'}
    </button>
  );
}

/**
 * Placeholder droppable that stands in for the centre zone when it has no
 * sections. Carries `data-emptyzone` so `computeTarget` resolves a drop (or a
 * library add-project click) to a brand-new MAIN section, and offers a direct
 * click-to-place when a card is grabbed or a widget is being added.
 */
export function EmptyMainZone({ dragging, grabbedId, isAdding, onPlace }: {
  dragging: boolean;
  grabbedId: string | null;
  isAdding: boolean;
  onPlace: (coords: { x: number; y: number }) => void;
}) {
  const { setNodeRef } = useDroppable({ id: 'empty-zone-main', data: { kind: 'emptyzone' } });
  return (
    <div
      ref={setNodeRef}
      data-emptyzone="main"
      onClick={grabbedId ? (e) => { e.stopPropagation(); onPlace({ x: e.clientX, y: e.clientY }); } : undefined}
      className={cn(
        'flex min-h-[160px] flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-white/15 dark:border-white/10 text-center transition-all',
        (dragging || grabbedId) && 'cursor-pointer border-primary/40',
        isAdding && 'border-primary/50',
      )}
    >
      <Sparkles size={22} className="text-primary/70" />
      <span className="font-serif text-sm font-semibold text-foreground">Centre is empty</span>
      <span className="px-6 text-[11px] text-muted-foreground">
        {grabbedId
          ? 'Click here to place the held widget'
          : isAdding
            ? 'Click here to place the new widget'
            : dragging
              ? 'Drop a widget here'
              : 'Open Customize to add a widget, or drop one from the library'}
      </span>
    </div>
  );
}
