'use client';

// ── Drawing Manager ───────────────────────────────────────────────────────────
// Owns the drawing collection, selection, and a command-based undo/redo history.
// Drawings are pure market objects (time + price) — the manager never touches
// pixels or ECharts. Rendering is delegated to the renderer.

import type { ChartDrawing, DrawingType } from '@/lib/chart/types';

export type DrawingCommand =
  | { kind: 'create'; drawing: ChartDrawing }
  | { kind: 'delete'; drawing: ChartDrawing }
  | { kind: 'update'; id: string; before: ChartDrawing; after: ChartDrawing }
  | { kind: 'duplicate'; drawing: ChartDrawing };

const HISTORY_LIMIT = 100;

export class DrawingManager {
  private drawings: ChartDrawing[] = [];
  private selectedId: string | null = null;
  private undoStack: DrawingCommand[] = [];
  private redoStack: DrawingCommand[] = [];
  private listeners = new Set<() => void>();

  constructor(initial: ChartDrawing[] = []) {
    this.drawings = initial.map((d) => ({ ...d }));
  }

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private emit() {
    for (const fn of this.listeners) fn();
  }

  getAll(): ChartDrawing[] {
    return this.drawings;
  }

  getById(id: string): ChartDrawing | undefined {
    return this.drawings.find((d) => d.id === id);
  }

  getSelected(): ChartDrawing | null {
    return this.selectedId ? this.getById(this.selectedId) ?? null : null;
  }

  select(id: string | null): void {
    this.selectedId = id;
    this.emit();
  }

  /** Create a drawing (records undo). */
  create(drawing: ChartDrawing): void {
    this.drawings = [...this.drawings, drawing];
    this.selectedId = drawing.id;
    this.pushUndo({ kind: 'create', drawing });
    this.redoStack = [];
    this.emit();
  }

  /** Delete a drawing (records undo). */
  delete(id: string): void {
    const drawing = this.getById(id);
    if (!drawing) return;
    this.drawings = this.drawings.filter((d) => d.id !== id);
    if (this.selectedId === id) this.selectedId = null;
    this.pushUndo({ kind: 'delete', drawing });
    this.redoStack = [];
    this.emit();
  }

  /** Update a drawing in place (records undo). */
  update(id: string, patch: Partial<ChartDrawing>): void {
    const before = this.getById(id);
    if (!before) return;
    const after = { ...before, ...patch, updatedAt: Date.now() } as ChartDrawing;
    this.drawings = this.drawings.map((d) => (d.id === id ? after : d));
    this.pushUndo({ kind: 'update', id, before, after });
    this.redoStack = [];
    this.emit();
  }

  /** Duplicate a drawing (records undo). */
  duplicate(id: string): void {
    const src = this.getById(id);
    if (!src) return;
    const copy = { ...src, id: newDrawingId(), createdAt: Date.now(), updatedAt: Date.now() } as ChartDrawing;
    this.drawings = [...this.drawings, copy];
    this.selectedId = copy.id;
    this.pushUndo({ kind: 'duplicate', drawing: copy });
    this.redoStack = [];
    this.emit();
  }

  /** Toggle lock / visibility. */
  setLocked(id: string, locked: boolean): void {
    this.update(id, { locked } as Partial<ChartDrawing>);
  }
  setVisible(id: string, visible: boolean): void {
    this.update(id, { visible } as Partial<ChartDrawing>);
  }

  clear(): void {
    for (const d of this.drawings) this.undoStack.push({ kind: 'delete', drawing: d });
    this.drawings = [];
    this.selectedId = null;
    this.redoStack = [];
    this.emit();
  }

  undo(): void {
    const cmd = this.undoStack.pop();
    if (!cmd) return;
    this.applyInverse(cmd);
    this.redoStack.push(cmd);
    this.emit();
  }

  redo(): void {
    const cmd = this.redoStack.pop();
    if (!cmd) return;
    this.apply(cmd);
    this.undoStack.push(cmd);
    this.emit();
  }

  canUndo(): boolean {
    return this.undoStack.length > 0;
  }
  canRedo(): boolean {
    return this.redoStack.length > 0;
  }

  private pushUndo(cmd: DrawingCommand): void {
    this.undoStack.push(cmd);
    if (this.undoStack.length > HISTORY_LIMIT) this.undoStack.shift();
  }

  private apply(cmd: DrawingCommand): void {
    switch (cmd.kind) {
      case 'create':
      case 'duplicate':
        this.drawings = [...this.drawings, cmd.drawing];
        this.selectedId = cmd.drawing.id;
        break;
      case 'delete':
        this.drawings = this.drawings.filter((d) => d.id !== cmd.drawing.id);
        if (this.selectedId === cmd.drawing.id) this.selectedId = null;
        break;
      case 'update':
        this.drawings = this.drawings.map((d) => (d.id === cmd.id ? cmd.after : d));
        break;
    }
  }

  private applyInverse(cmd: DrawingCommand): void {
    switch (cmd.kind) {
      case 'create':
      case 'duplicate':
        this.drawings = this.drawings.filter((d) => d.id !== cmd.drawing.id);
        if (this.selectedId === cmd.drawing.id) this.selectedId = null;
        break;
      case 'delete':
        this.drawings = [...this.drawings, cmd.drawing];
        this.selectedId = cmd.drawing.id;
        break;
      case 'update':
        this.drawings = this.drawings.map((d) => (d.id === cmd.id ? cmd.before : d));
        break;
    }
  }

  /** Serialize all drawings (for persistence). */
  serialize(): ChartDrawing[] {
    return this.drawings.map((d) => JSON.parse(JSON.stringify(d)));
  }

  /** Replace the whole collection (restore). */
  restore(drawings: ChartDrawing[]): void {
    this.drawings = drawings.map((d) => ({ ...d }));
    this.selectedId = null;
    this.undoStack = [];
    this.redoStack = [];
    this.emit();
  }
}

export function newDrawingId(): string {
  return `drawing-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
}

/** Create a fresh drawing of a given type with default style. */
export function makeDrawing(type: DrawingType, color = '#7aff78'): ChartDrawing {
  const base = {
    id: newDrawingId(),
    type,
    visible: true,
    locked: false,
    style: { color, width: 1.5, lineStyle: 'solid' as const, opacity: 1 },
    createdAt: Date.now(),
    updatedAt: Date.now(),
  };
  switch (type) {
    case 'trendline':
    case 'ray':
    case 'arrow':
      return { ...base, type, start: { time: 0, price: 0 }, end: { time: 0, price: 0 } };
    case 'horizontal':
      return { ...base, type, price: 0 };
    case 'vertical':
      return { ...base, type, time: 0 };
    case 'rectangle':
      return { ...base, type, start: { time: 0, price: 0 }, end: { time: 0, price: 0 }, fillOpacity: 0.1 };
    case 'fibonacci':
      return { ...base, type, start: { time: 0, price: 0 }, end: { time: 0, price: 0 }, levels: [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1] };
    case 'text':
      return { ...base, type, point: { time: 0, price: 0 }, text: '' };
    case 'measure':
      return { ...base, type, start: { time: 0, price: 0 }, end: { time: 0, price: 0 } };
    case 'long-position':
    case 'short-position':
      return { ...base, type, entry: { time: 0, price: 0 }, stop: { time: 0, price: 0 }, takeProfit: { time: 0, price: 0 } };
  }
}
