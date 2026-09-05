'use client';

// ── WorkspaceCanvas — kernel edit chrome ─────────────────────────────────────
// Renders sections/columns/cards and owns ALL drag/resize/hide chrome.
// Widgets stay pure: the page only supplies renderWidget(widgetId).
//
// Drag implementation is pointer-based (no HTML5 DnD): the whole card is the
// drag surface, a ghost clone follows the cursor, a highlight bar marks the
// exact insertion point (within column / empty column / new column / new
// section), and edge auto-scroll keeps off-screen targets reachable. The tree
// is committed (and persisted) once on drop.

import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Columns3, GripVertical, Minus, Plus, Scan, Sparkles, X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { WorkspaceDrawer, type WorkspaceWidgetMeta } from './workspace-drawer';
import type { DropTarget, WidgetPlacement } from './types';
import type { WorkspaceController as WC } from './use-workspace';

const CARD_CLASS =
  'rounded-2xl bg-[#0f0f0f]/60 dark:bg-[#0f0f0f]/60 bg-white/70 backdrop-blur-xl border border-white/10 dark:border-white/5 transition-all duration-300';

type DragState = { widgetId: string } | null;
type Hit = (DropTarget & { kind: 'col' | 'newcol' | 'newsection' }) | null;

interface WorkspaceCanvasProps {
  workspace: WC;
  renderWidget: (widgetId: string, placement: WidgetPlacement) => React.ReactNode;
  widgets: WorkspaceWidgetMeta[];
  className?: string;
}

export function WorkspaceCanvas({ workspace, renderWidget, widgets, className }: WorkspaceCanvasProps) {
  const { layout, editMode, ops, corrupt } = workspace;
  const [drag, setDrag] = useState<DragState>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const ghostRef = useRef<HTMLElement | null>(null);
  const dragRef = useRef<{ widgetId: string; started: boolean; offX: number; offY: number } | null>(null);
  const hitRef = useRef<Hit>(null);
  const indicatorRef = useRef<HTMLDivElement | null>(null);
  const domOriginRef = useRef<{ parent: HTMLElement; next: ChildNode | null } | null>(null);
  const rafRef = useRef<number | null>(null);
  const scrollSpeedRef = useRef(0);
  const suppressClickRef = useRef(false);

  const clearIndicator = useCallback(() => {
    indicatorRef.current?.remove();
    indicatorRef.current = null;
    document.querySelectorAll('[data-wcol].ws-drop-hot, [data-wnewcol].ws-drop-hot, [data-wnewsection].ws-drop-hot')
      .forEach(el => el.classList.remove('ws-drop-hot'));
  }, []);

  const endDrag = useCallback(() => {
    if (rafRef.current !== null) { cancelAnimationFrame(rafRef.current); rafRef.current = null; }
    scrollSpeedRef.current = 0;
    document.body.style.userSelect = '';
    ghostRef.current?.remove();
    ghostRef.current = null;
    clearIndicator();
    // Restore the dragged card to its original DOM slot so React reconciles
    // the committed layout from a clean, known tree.
    const dragId = dragRef.current?.widgetId;
    const origin = domOriginRef.current;
    if (dragId && origin) {
      const el = document.querySelector<HTMLElement>(`[data-wcard="${dragId}"]`);
      if (el && el.parentElement !== origin.parent) origin.parent.insertBefore(el, origin.next);
    }
    domOriginRef.current = null;
    dragRef.current = null;
    hitRef.current = null;
    setDrag(null);
  }, [clearIndicator]);

  useEffect(() => () => endDrag(), [endDrag]);

  // ── Drop-target resolution + highlight (live DOM, no re-render) ────────────
  const resolveHit = useCallback((x: number, y: number): Hit => {
    const el = document.elementFromPoint(x, y);
    if (!el) return null;

    const newSectionZone = (el as HTMLElement).closest?.('[data-wnewsection]') as HTMLElement | null;
    if (newSectionZone) {
      return { kind: 'newsection', sectionId: '', columnId: null, index: 0 };
    }
    const newColZone = (el as HTMLElement).closest?.('[data-wnewcol]') as HTMLElement | null;
    if (newColZone) {
      return { kind: 'newcol', sectionId: newColZone.getAttribute('data-wnewcol') || '', columnId: null, index: 0 };
    }
    const colEl = (el as HTMLElement).closest?.('[data-wcol]') as HTMLElement | null;
    if (colEl) {
      const columnId = colEl.getAttribute('data-wcol') || '';
      const sectionId = colEl.getAttribute('data-section') || '';
      const dragId = dragRef.current?.widgetId;
      const cards = [...colEl.querySelectorAll<HTMLElement>('[data-wcard]')]
        .filter(c => c.getAttribute('data-wcard') !== dragId);
      let index = cards.length;
      for (let i = 0; i < cards.length; i++) {
        const r = cards[i].getBoundingClientRect();
        if (y < r.top + r.height / 2) { index = i; break; }
      }
      return { kind: 'col', sectionId, columnId, index };
    }
    return null;
  }, []);

  const paintHit = useCallback((hit: Hit) => {
    clearIndicator();
    if (!hit) return;
    const dragId = dragRef.current?.widgetId;
    const draggedEl = dragId ? document.querySelector<HTMLElement>(`[data-wcard="${dragId}"]`) : null;

    // Column targets: LIVE PREVIEW — physically move the dragged card into the
    // target column at the insertion index. What you see is what will commit.
    if (hit.kind === 'col') {
      const colEl = document.querySelector<HTMLElement>(`[data-wcol="${hit.columnId}"]`);
      if (!colEl || !draggedEl) return;
      const cards = [...colEl.querySelectorAll<HTMLElement>('[data-wcard]')]
        .filter(c => c.getAttribute('data-wcard') !== dragId);
      const anchor = cards[hit.index] ?? null;
      if (draggedEl.parentElement !== colEl || draggedEl.nextElementSibling !== anchor) {
        colEl.insertBefore(draggedEl, anchor);
      }
      colEl.classList.add('ws-drop-hot');
      return;
    }

    // New-column / new-section targets: highlight + indicator bar.
    let parent: HTMLElement | null = null;
    if (hit.kind === 'newcol') {
      parent = document.querySelector<HTMLElement>(`[data-wnewcol="${hit.sectionId}"]`);
    } else {
      parent = document.querySelector<HTMLElement>('[data-wnewsection]');
    }
    if (!parent) return;
    parent.classList.add('ws-drop-hot');
    let ind = indicatorRef.current;
    if (!ind) {
      ind = document.createElement('div');
      ind.className = 'ws-drop-indicator';
      indicatorRef.current = ind;
    }
    parent.appendChild(ind);
  }, [clearIndicator]);

  // ── Drag start (whole card surface) ────────────────────────────────────────
  const onCardPointerDown = useCallback((e: React.PointerEvent, widgetId: string) => {
    if (e.button !== 0) return;
    if ((e.target as HTMLElement).closest('[data-nodrag],button,a,input,select,textarea')) return;
    const card = (e.currentTarget as HTMLElement).closest('[data-wcard]') as HTMLElement | null;
    if (!card) return;

    e.preventDefault();
    const sx = e.clientX;
    const sy = e.clientY;
    const rect = card.getBoundingClientRect();
    const info = { widgetId, started: false, offX: e.clientX - rect.left, offY: e.clientY - rect.top };
    dragRef.current = info;

    const EDGE = 90;
    const MAX_SPEED = 18;
    const scrollStep = () => {
      const speed = scrollSpeedRef.current;
      const scroller = document.scrollingElement as HTMLElement | null;
      if (speed !== 0 && scroller) scroller.scrollTop += speed;
      rafRef.current = speed !== 0 ? requestAnimationFrame(scrollStep) : null;
    };

    const onMove = (ev: PointerEvent) => {
      const d = dragRef.current;
      if (!d) return;
      if (!d.started) {
        if (Math.hypot(ev.clientX - sx, ev.clientY - sy) < 4) return;
        d.started = true;
        document.body.style.userSelect = 'none';
        setDrag({ widgetId });
        suppressClickRef.current = true;
        domOriginRef.current = { parent: card.parentElement!, next: card.nextSibling };
        // Ghost clone of the live card.
        const ghost = card.cloneNode(true) as HTMLElement;
        ghost.style.width = `${rect.width}px`;
        ghost.style.position = 'fixed';
        ghost.style.left = '0';
        ghost.style.top = '0';
        ghost.style.zIndex = '9999';
        ghost.style.pointerEvents = 'none';
        ghost.style.opacity = '0.92';
        ghost.style.transform = `translate3d(${ev.clientX - d.offX}px, ${ev.clientY - d.offY}px, 0) rotate(1.5deg) scale(1.02)`;
        ghost.classList.add('shadow-2xl', 'shadow-black/40', 'pointer-events-none');
        document.body.appendChild(ghost);
        ghostRef.current = ghost;
        card.classList.add('opacity-30');
      }
      const ghost = ghostRef.current;
      if (ghost) {
        ghost.style.transform = `translate3d(${ev.clientX - d.offX}px, ${ev.clientY - d.offY}px, 0) rotate(1.5deg) scale(1.02)`;
      }
      const hit = resolveHit(ev.clientX, ev.clientY);
      if (JSON.stringify(hit) !== JSON.stringify(hitRef.current)) {
        hitRef.current = hit;
        paintHit(hit);
      }
      // Edge auto-scroll
      const vh = window.innerHeight;
      let speed = 0;
      if (ev.clientY < EDGE) speed = -Math.min(MAX_SPEED, ((EDGE - ev.clientY) / EDGE) * MAX_SPEED);
      else if (ev.clientY > vh - EDGE) speed = Math.min(MAX_SPEED, ((ev.clientY - (vh - EDGE)) / EDGE) * MAX_SPEED);
      scrollSpeedRef.current = speed;
      if (speed !== 0 && rafRef.current === null) rafRef.current = requestAnimationFrame(scrollStep);
    };

    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      card.classList.remove('opacity-30');
      const hit = hitRef.current;
      const d = dragRef.current;
      const started = d?.started ?? false;
      endDrag();
      if (!started) { suppressClickRef.current = false; return; }
      setTimeout(() => { suppressClickRef.current = false; }, 150);
      if (!hit || !d) return;
      if (hit.kind === 'newsection') ops.moveWidgetToNewSection(d.widgetId);
      else ops.moveWidget(d.widgetId, { sectionId: hit.sectionId, columnId: hit.columnId, index: hit.index });
    };

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [endDrag, ops, paintHit, resolveHit]);

  // Drag gating: only start visuals after a real threshold. Track origin here.
  const originRef = useRef<{ x: number; y: number } | null>(null);
  const onCardPointerDownGate = useCallback((e: React.PointerEvent, widgetId: string) => {
    originRef.current = { x: e.clientX, y: e.clientY };
    onCardPointerDown(e, widgetId);
  }, [onCardPointerDown]);

  // ── Height resize (bottom edge, edit mode) ─────────────────────────────────
  const onResizePointerDown = useCallback((e: React.PointerEvent, widgetId: string) => {
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
      ops.setWidgetHeight(widgetId, Math.max(140, startH + ev.clientY - startY));
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [ops]);

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
              data-nodrag
              onClick={() => setDrawerOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-border/40 bg-accent/30 hover:bg-accent/60 hover:border-primary/40 hover:text-primary text-muted-foreground px-3 py-1.5 text-xs font-bold transition-all cursor-pointer"
            >
              <Plus size={13} /> Widgets / Templates
            </button>
            <button
              data-nodrag
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

      <div className="flex flex-col gap-3">
        {layout.sections.map((section) => (
          <div key={section.id} className="rounded-2xl p-1 transition-all">
            {/* Section edit controls */}
            {editMode && (
              <div className="mb-1.5 flex items-center gap-1.5 px-1" data-nodrag>
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
              {section.columns.map((column) => (
                <div
                  key={column.id}
                  data-wcol={column.id}
                  data-section={section.id}
                  className={cn(
                    'relative flex flex-col gap-2.5 min-h-[40px] min-w-0 flex-1',
                    editMode && 'rounded-2xl outline-1 outline-dashed outline-border/20 p-1.5 -m-1.5',
                  )}
                  style={{ flexGrow: column.weight, flexBasis: 0 }}
                >
                  {column.widgets.map((placement) => (
                    <div
                      key={placement.id}
                      data-wcard={placement.id}
                      onPointerDown={(e) => onCardPointerDownGate(e, placement.id)}
                      onClickCapture={(e) => { if (suppressClickRef.current && drag) { e.preventDefault(); e.stopPropagation(); } }}
                      style={placement.height != null ? { height: placement.height } : undefined}
                      className={cn(
                        CARD_CLASS,
                        'group/card relative overflow-hidden cursor-grab active:cursor-grabbing',
                      )}
                    >
                      {editMode && (
                        <div className="absolute right-2 top-2 z-20 flex items-center gap-1 opacity-0 group-hover/card:opacity-100 transition-opacity" data-nodrag>
                          <span className="rounded-lg bg-background/80 border border-border/40 p-1 text-muted-foreground" title="Drag">
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
                          onPointerDown={(e) => onResizePointerDown(e, placement.id)}
                          className="absolute inset-x-0 bottom-0 h-3 cursor-ns-resize z-20 flex items-end justify-center opacity-0 group-hover/card:opacity-100 transition-opacity"
                          title="Drag to resize height"
                        >
                          <div className="mb-0.5 h-1 w-10 rounded-full bg-border" />
                        </div>
                      )}
                    </div>
                  ))}

                  {/* Empty-column drop target */}
                  {column.widgets.length === 0 && (
                    <div className={cn(
                      'flex min-h-[44px] flex-1 items-center justify-center rounded-xl border border-dashed border-border/30 text-[10px] font-semibold text-muted-foreground/50',
                      (drag || editMode) && 'border-primary/40 text-primary/70',
                    )}>
                      {drag ? 'Drop a widget here' : editMode ? 'Drop a widget here' : 'Empty column'}
                    </div>
                  )}
                </div>
              ))}

              {/* New-column drop zone (drag) */}
              {(editMode || drag) && (
                <div
                  data-wnewcol={section.id}
                  data-nodrag
                  className="hidden md:flex w-5 shrink-0 items-center justify-center rounded-xl border border-dashed border-border/30 text-muted-foreground/40 transition-all hover:border-primary/40 hover:text-primary"
                  title="Drop here to create a new column"
                >
                  <Plus size={12} />
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* New-section drop strip */}
      {(editMode || drag) && !isEmpty && (
        <div
          data-wnewsection
          data-nodrag
          className={cn(
            'mt-3 flex h-11 items-center justify-center gap-2 rounded-2xl border border-dashed text-[10px] font-bold uppercase tracking-widest transition-all',
            drag ? 'border-primary/50 text-primary animate-fade-in' : 'border-border/40 text-muted-foreground/50 hover:border-primary/50 hover:text-primary',
          )}
        >
          <Plus size={12} /> Drop here for a new section
        </div>
      )}

      <WorkspaceDrawer
        open={editMode && drawerOpen}
        onClose={() => setDrawerOpen(false)}
        workspace={workspace}
        widgets={widgets}
      />
    </div>
  );
}


