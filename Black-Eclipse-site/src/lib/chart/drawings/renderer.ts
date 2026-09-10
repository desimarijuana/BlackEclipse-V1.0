'use client';

// ── Drawing Renderer ──────────────────────────────────────────────────────────
// Draws market-anchored drawings onto a 2D canvas overlay. The renderer is
// provider-independent: it only needs a CoordinateTransformer to convert market
// points to pixels. It also performs geometry-aware hit-testing and draws
// selection handles.

import type { ChartDrawing, ChartPoint } from '@/lib/chart/types';
import type { CoordinateTransformer } from './coordinate';

export interface RenderContext {
  ctx: CanvasRenderingContext2D;
  width: number;
  height: number;
  dpr: number;
  transform: CoordinateTransformer;
  selectedId: string | null;
}

/** Draw a single drawing. */
export function drawDrawing(ctx: RenderContext, drawing: ChartDrawing): void {
  if (!drawing.visible) return;
  const { ctx: c, transform } = ctx;
  const color = drawing.style.color;
  const width = drawing.style.width;
  const lineStyle = drawing.style.lineStyle ?? 'solid';

  c.save();
  c.strokeStyle = color;
  c.fillStyle = color;
  c.lineWidth = width;
  c.setLineDash(lineStyle === 'dashed' ? [6, 4] : lineStyle === 'dotted' ? [2, 3] : []);
  c.globalAlpha = drawing.style.opacity ?? 1;

  switch (drawing.type) {
    case 'trendline':
    case 'ray':
    case 'arrow': {
      const a = transform.marketToScreen(drawing.start);
      const b = transform.marketToScreen(drawing.end);
      if (!a || !b) break;
      c.beginPath();
      c.moveTo(a.x, a.y);
      c.lineTo(b.x, b.y);
      c.stroke();
      if (drawing.type === 'arrow') drawArrowHead(c, a, b);
      break;
    }
    case 'horizontal': {
      const p = transform.marketToScreen({ time: 0, price: drawing.price });
      if (!p) break;
      c.beginPath();
      c.moveTo(0, p.y);
      c.lineTo(ctx.width, p.y);
      c.stroke();
      break;
    }
    case 'vertical': {
      const p = transform.marketToScreen({ time: drawing.time, price: 0 });
      if (!p) break;
      c.beginPath();
      c.moveTo(p.x, 0);
      c.lineTo(p.x, ctx.height);
      c.stroke();
      break;
    }
    case 'rectangle': {
      const a = transform.marketToScreen(drawing.start);
      const b = transform.marketToScreen(drawing.end);
      if (!a || !b) break;
      const x = Math.min(a.x, b.x);
      const y = Math.min(a.y, b.y);
      const w = Math.abs(b.x - a.x);
      const h = Math.abs(b.y - a.y);
      if (drawing.fill) {
        c.globalAlpha = drawing.fillOpacity ?? 0.1;
        c.fillStyle = drawing.fill;
        c.fillRect(x, y, w, h);
        c.globalAlpha = drawing.style.opacity ?? 1;
      }
      c.strokeRect(x, y, w, h);
      break;
    }
    case 'fibonacci': {
      const a = transform.marketToScreen(drawing.start);
      const b = transform.marketToScreen(drawing.end);
      if (!a || !b) break;
      const high = Math.max(a.y, b.y);
      const low = Math.min(a.y, b.y);
      const range = high - low;
      for (const level of drawing.levels) {
        const y = high - range * level;
        c.beginPath();
        c.moveTo(0, y);
        c.lineTo(ctx.width, y);
        c.stroke();
        c.fillStyle = color;
        c.font = '10px monospace';
        c.fillText(`${(level * 100).toFixed(level === 0 || level === 1 ? 0 : 1)}%`, 4, y - 2);
      }
      break;
    }
    case 'text': {
      const p = transform.marketToScreen(drawing.point);
      if (!p) break;
      c.font = '12px monospace';
      c.fillText(drawing.text, p.x, p.y);
      break;
    }
    case 'measure': {
      const a = transform.marketToScreen(drawing.start);
      const b = transform.marketToScreen(drawing.end);
      if (!a || !b) break;
      c.beginPath();
      c.moveTo(a.x, a.y);
      c.lineTo(b.x, b.y);
      c.stroke();
      const dist = Math.abs(drawing.end.price - drawing.start.price);
      c.fillStyle = color;
      c.font = '10px monospace';
      c.fillText(dist.toFixed(2), (a.x + b.x) / 2, (a.y + b.y) / 2 - 4);
      break;
    }
    case 'long-position':
    case 'short-position': {
      const e = transform.marketToScreen(drawing.entry);
      const s = transform.marketToScreen(drawing.stop);
      const t = transform.marketToScreen(drawing.takeProfit);
      if (!e || !s || !t) break;
      // Entry line
      c.beginPath();
      c.moveTo(0, e.y);
      c.lineTo(ctx.width, e.y);
      c.stroke();
      // Stop line
      c.setLineDash([4, 4]);
      c.beginPath();
      c.moveTo(0, s.y);
      c.lineTo(ctx.width, s.y);
      c.stroke();
      // TP line
      c.beginPath();
      c.moveTo(0, t.y);
      c.lineTo(ctx.width, t.y);
      c.stroke();
      c.setLineDash([]);
      break;
    }
  }
  c.restore();
}

/** Draw selection handles for a drawing. */
export function drawHandles(ctx: RenderContext, drawing: ChartDrawing): void {
  const { ctx: c, transform } = ctx;
  const points = anchorPoints(drawing);
  c.save();
  c.fillStyle = '#ffffff';
  c.strokeStyle = drawing.style.color;
  c.lineWidth = 2;
  for (const p of points) {
    const s = transform.marketToScreen(p);
    if (!s) continue;
    c.beginPath();
    c.arc(s.x, s.y, 5, 0, Math.PI * 2);
    c.fill();
    c.stroke();
  }
  c.restore();
}

/** The anchor points of a drawing (for handles + hit testing). */
export function anchorPoints(drawing: ChartDrawing): ChartPoint[] {
  switch (drawing.type) {
    case 'trendline':
    case 'ray':
    case 'arrow':
    case 'rectangle':
    case 'fibonacci':
    case 'measure':
      return [drawing.start, drawing.end];
    case 'horizontal':
      return [{ time: 0, price: drawing.price }];
    case 'vertical':
      return [{ time: drawing.time, price: 0 }];
    case 'text':
      return [drawing.point];
    case 'long-position':
    case 'short-position':
      return [drawing.entry, drawing.stop, drawing.takeProfit];
  }
}

/** Hit-test a drawing at a screen point. Returns the drawing id or null. */
export function hitTest(
  drawings: ChartDrawing[],
  x: number,
  y: number,
  transform: CoordinateTransformer,
  tolerance = 8,
): string | null {
  // Handles first (larger hitbox).
  for (const d of drawings) {
    if (!d.visible) continue;
    for (const p of anchorPoints(d)) {
      const s = transform.marketToScreen(p);
      if (s && Math.hypot(s.x - x, s.y - y) <= tolerance + 4) return d.id;
    }
  }
  // Then the geometry.
  for (const d of drawings) {
    if (!d.visible) continue;
    if (hitDrawing(d, x, y, transform, tolerance)) return d.id;
  }
  return null;
}

function hitDrawing(d: ChartDrawing, x: number, y: number, t: CoordinateTransformer, tol: number): boolean {
  switch (d.type) {
    case 'trendline':
    case 'ray':
    case 'arrow':
    case 'measure': {
      const a = t.marketToScreen(d.start);
      const b = t.marketToScreen(d.end);
      if (!a || !b) return false;
      return distToSegment(x, y, a, b) <= tol;
    }
    case 'horizontal': {
      const p = t.marketToScreen({ time: 0, price: d.price });
      return p ? Math.abs(y - p.y) <= tol : false;
    }
    case 'vertical': {
      const p = t.marketToScreen({ time: d.time, price: 0 });
      return p ? Math.abs(x - p.x) <= tol : false;
    }
    case 'rectangle': {
      const a = t.marketToScreen(d.start);
      const b = t.marketToScreen(d.end);
      if (!a || !b) return false;
      const x0 = Math.min(a.x, b.x), x1 = Math.max(a.x, b.x);
      const y0 = Math.min(a.y, b.y), y1 = Math.max(a.y, b.y);
      return x >= x0 - tol && x <= x1 + tol && y >= y0 - tol && y <= y1 + tol;
    }
    case 'fibonacci': {
      const a = t.marketToScreen(d.start);
      const b = t.marketToScreen(d.end);
      if (!a || !b) return false;
      return distToSegment(x, y, a, b) <= tol;
    }
    case 'text': {
      const p = t.marketToScreen(d.point);
      return p ? Math.hypot(p.x - x, p.y - y) <= tol + 8 : false;
    }
    case 'long-position':
    case 'short-position': {
      const e = t.marketToScreen(d.entry);
      const s = t.marketToScreen(d.stop);
      const tp = t.marketToScreen(d.takeProfit);
      if (!e || !s || !tp) return false;
      return Math.abs(y - e.y) <= tol || Math.abs(y - s.y) <= tol || Math.abs(y - tp.y) <= tol;
    }
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

function drawArrowHead(c: CanvasRenderingContext2D, a: { x: number; y: number }, b: { x: number; y: number }): void {
  const angle = Math.atan2(b.y - a.y, b.x - a.x);
  const size = 8;
  c.beginPath();
  c.moveTo(b.x, b.y);
  c.lineTo(b.x - size * Math.cos(angle - Math.PI / 6), b.y - size * Math.sin(angle - Math.PI / 6));
  c.moveTo(b.x, b.y);
  c.lineTo(b.x - size * Math.cos(angle + Math.PI / 6), b.y - size * Math.sin(angle + Math.PI / 6));
  c.stroke();
}
