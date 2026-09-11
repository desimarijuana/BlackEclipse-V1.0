'use client';

// ── Drawing Interaction Controller ────────────────────────────────────────────
// Centralized pointer-interaction state machine. Handles tool selection,
// drawing creation (click-to-place with live preview), selection, moving, and
// handle resizing. All coordinates are converted to market space immediately —
// the controller never stores pixels.

import type { ChartDrawing, ChartPoint, DrawingToolMode } from '@/lib/chart/types';
import type { DrawingManager } from './manager';
import { buildDrawing, getDrawingDef } from './tools';
import type { CoordinateTransformer } from './coordinate';
import { anchorPoints } from './renderer';

type InteractionState =
  | { phase: 'idle' }
  | { phase: 'drawing'; tool: DrawingToolMode; points: ChartPoint[] }
  | { phase: 'moving'; id: string; start: ChartPoint; orig: ChartPoint[] }
  | { phase: 'resizing'; id: string; handleIndex: number; orig: ChartPoint[] };

export class DrawingController {
  private state: InteractionState = { phase: 'idle' };
  private tool: DrawingToolMode = 'cursor';
  private transform: CoordinateTransformer | null = null;
  private manager: DrawingManager;
  private onPreview: (() => void) | null = null;

  constructor(manager: DrawingManager) {
    this.manager = manager;
  }

  setTransform(t: CoordinateTransformer | null): void {
    this.transform = t;
  }

  setTool(tool: DrawingToolMode): void {
    this.tool = tool;
    // Switching tools cancels any incomplete drawing.
    if (this.state.phase === 'drawing') this.state = { phase: 'idle' };
    if (tool === 'cursor') this.manager.select(null);
    this.onPreview?.();
  }

  getTool(): DrawingToolMode {
    return this.tool;
  }

  setPreviewCallback(fn: () => void): void {
    this.onPreview = fn;
  }

  /** Cancel the current interaction (Escape). */
  cancel(): void {
    if (this.state.phase === 'drawing') {
      this.state = { phase: 'idle' };
      this.onPreview?.();
    }
  }

  /** Handle a pointer-down event. Returns true if consumed (no chart pan). */
  pointerDown(x: number, y: number): boolean {
    if (!this.transform) return false;
    const market = this.transform.screenToMarket(x, y);
    if (!market) return false;

    // Drawing tool active → place an anchor.
    if (this.tool !== 'cursor') {
      const def = getDrawingDef(this.tool as never);
      if (!def) return true;
      if (this.state.phase !== 'drawing') {
        this.state = { phase: 'drawing', tool: this.tool, points: [market] };
      } else {
        const points = [...this.state.points, market];
        if (points.length >= def.points) {
          const drawing = buildDrawing(this.tool as never, points);
          this.manager.create(drawing);
          this.state = { phase: 'idle' };
        } else {
          this.state = { phase: 'drawing', tool: this.tool, points };
        }
      }
      this.onPreview?.();
      return true;
    }

    // Cursor mode → hit test.
    const hit = this.hitTest(x, y);
    if (hit) {
      this.manager.select(hit.id);
      const drawing = this.manager.getById(hit.id);
      if (drawing && !drawing.locked) {
        if (hit.handleIndex != null) {
          this.state = { phase: 'resizing', id: hit.id, handleIndex: hit.handleIndex, orig: anchorPoints(drawing) };
        } else {
          this.state = { phase: 'moving', id: hit.id, start: market, orig: anchorPoints(drawing) };
        }
      }
      this.onPreview?.();
      return true;
    }

    // Empty click → deselect.
    this.manager.select(null);
    this.onPreview?.();
    return false;
  }

  /** Handle pointer-move. Returns true if consumed. */
  pointerMove(x: number, y: number): boolean {
    if (!this.transform) return false;
    const market = this.transform.screenToMarket(x, y);
    if (!market) return false;

    if (this.state.phase === 'drawing') {
      // Live preview handled by renderer reading the pending points.
      this.onPreview?.();
      return true;
    }

    if (this.state.phase === 'moving') {
      const drawing = this.manager.getById(this.state.id);
      if (!drawing) return false;
      const dx = market.time - this.state.start.time;
      const dy = market.price - this.state.start.price;
      const moved = this.state.orig.map((p) => ({ time: p.time + dx, price: p.price + dy }));
      this.applyAnchors(drawing, moved);
      this.onPreview?.();
      return true;
    }

    if (this.state.phase === 'resizing') {
      const drawing = this.manager.getById(this.state.id);
      if (!drawing) return false;
      const moved = [...this.state.orig];
      moved[this.state.handleIndex] = market;
      this.applyAnchors(drawing, moved);
      this.onPreview?.();
      return true;
    }

    return false;
  }

  /** Handle pointer-up. Returns true if consumed. */
  pointerUp(): boolean {
    if (this.state.phase === 'moving' || this.state.phase === 'resizing') {
      this.state = { phase: 'idle' };
      this.onPreview?.();
      return true;
    }
    return false;
  }

  /** The pending anchor points during an active drawing (for live preview). */
  getPendingDrawing(): { tool: DrawingToolMode; points: ChartPoint[] } | null {
    if (this.state.phase !== 'drawing') return null;
    return { tool: this.state.tool, points: this.state.points };
  }

  /**
   * True when the given screen point should be captured by the overlay (i.e.
   * a drawing/handle is under the cursor, or a drawing tool is active). When
   * false the overlay yields pointer events to ECharts so pan/zoom work.
   */
  wantsPointer(x: number, y: number): boolean {
    if (this.tool !== 'cursor') return true;
    if (this.state.phase !== 'idle') return true;
    return this.hitTest(x, y) != null;
  }

  /** True while an interaction is in progress (drawing/moving/resizing). */
  isInteracting(): boolean {
    return this.state.phase !== 'idle';
  }

  private hitTest(x: number, y: number): { id: string; handleIndex: number | null } | null {    const drawings = this.manager.getAll();
    // Handles of the selected drawing first.
    const selected = this.manager.getSelected();
    if (selected) {
      const anchors = anchorPoints(selected);
      for (let i = 0; i < anchors.length; i++) {
        const s = this.transform?.marketToScreen(anchors[i]);
        if (s && Math.hypot(s.x - x, s.y - y) <= 12) return { id: selected.id, handleIndex: i };
      }
    }
    // Then geometry of all drawings.
    for (const d of drawings) {
      if (!d.visible) continue;
      if (this.hitGeometry(d, x, y)) return { id: d.id, handleIndex: null };
    }
    return null;
  }

  private hitGeometry(d: ChartDrawing, x: number, y: number): boolean {
    const t = this.transform;
    if (!t) return false;
    const tol = 8;
    const pts = anchorPoints(d);
    if (pts.length === 1) {
      const s = t.marketToScreen(pts[0]);
      return s ? Math.hypot(s.x - x, s.y - y) <= tol + 6 : false;
    }
    // For multi-point drawings, check distance to each segment.
    for (let i = 0; i < pts.length - 1; i++) {
      const a = t.marketToScreen(pts[i]);
      const b = t.marketToScreen(pts[i + 1]);
      if (a && b && distToSegment(x, y, a, b) <= tol) return true;
    }
    return false;
  }

  private applyAnchors(drawing: ChartDrawing, points: ChartPoint[]): void {
    const patch: Record<string, unknown> = {};
    switch (drawing.type) {
      case 'trendline':
      case 'ray':
      case 'arrow':
      case 'rectangle':
      case 'fibonacci':
      case 'measure':
        patch.start = points[0];
        patch.end = points[1];
        break;
      case 'horizontal':
        patch.price = points[0].price;
        break;
      case 'vertical':
        patch.time = points[0].time;
        break;
      case 'text':
        patch.point = points[0];
        break;
      case 'long-position':
      case 'short-position':
        patch.entry = points[0];
        patch.stop = points[1];
        patch.takeProfit = points[2];
        break;
    }
    this.manager.update(drawing.id, patch as Partial<ChartDrawing>);
  }
}

function distToSegment(px: number, py: number, a: { x: number; y: number }, b: { x: number; y: number }): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const lenSq = dx * dx + dy * dy;
  if (lenSq === 0) return Math.hypot(px - a.x, py - a.y);
  let t = ((px - a.x) * dx + (py - a.y) * dy) / lenSq;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (a.x + t * dx), py - (a.y + t * dy));
}
