'use client';

// ── Drawing Overlay ───────────────────────────────────────────────────────────
// A transparent canvas layered over the ECharts chart. It renders all drawings
// (market-anchored) and handles pointer events for the DrawingController.
//
// The canvas itself is `pointer-events: none` so it NEVER blocks ECharts
// pan/zoom. Instead we attach capture-phase listeners to the chart container:
// when a drawing/handle is under the cursor (or a drawing tool is active) we
// consume the event before ECharts sees it; otherwise the event falls through
// to ECharts so wheel-zoom and drag-pan work natively.

import React, { useEffect, useRef } from 'react';
import type { ECharts } from 'echarts';
import type { ChartDrawing, DrawingToolMode } from '@/lib/chart/types';
import { DrawingManager } from '@/lib/chart/drawings/manager';
import { DrawingController } from '@/lib/chart/drawings/controller';
import { createCoordinateTransformer, type CoordinateTransformer } from '@/lib/chart/drawings/coordinate';
import { drawDrawing, drawHandles } from '@/lib/chart/drawings/renderer';

interface DrawingOverlayProps {
  getChart: () => ECharts | null;
  manager: DrawingManager;
  controller: DrawingController;
  tool: DrawingToolMode;
}

export function DrawingOverlay({ getChart, manager, controller, tool }: DrawingOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const transformRef = useRef<CoordinateTransformer | null>(null);
  const rafRef = useRef<number | null>(null);
  const pointerRef = useRef<{ x: number; y: number } | null>(null);
  const captureRef = useRef(false);

  // Rebuild the transformer whenever the chart instance changes.
  useEffect(() => {
    const chart = getChart();
    transformRef.current = createCoordinateTransformer(chart);
    controller.setTransform(transformRef.current);
    scheduleDraw();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [getChart]);

  // Redraw on manager changes.
  useEffect(() => {
    const unsub = manager.subscribe(scheduleDraw);
    return unsub;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [manager]);

  // Redraw on tool change + reflect the active tool in the cursor.
  useEffect(() => {
    const parent = canvasRef.current?.parentElement;
    if (parent) parent.style.cursor = tool === 'cursor' ? '' : 'crosshair';
    scheduleDraw();
    return () => { if (parent) parent.style.cursor = ''; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tool]);

  // Listen to ECharts dataZoom / resize events to redraw.
  useEffect(() => {
    const chart = getChart();
    if (!chart) return;
    const onZoom = () => scheduleDraw();
    const onResize = () => scheduleDraw();
    chart.on('datazoom', onZoom);
    chart.on('finished', onResize);
    return () => {
      chart.off('datazoom', onZoom);
      chart.off('finished', onResize);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [getChart]);

  // Capture-phase pointer routing on the chart container. Consuming an event
  // (stopPropagation + preventDefault) prevents ECharts from panning; letting
  // it through enables native pan/zoom.
  useEffect(() => {
    const parent = canvasRef.current?.parentElement;
    if (!parent) return;

    const local = (e: PointerEvent): { x: number; y: number } => {
      const rect = parent.getBoundingClientRect();
      return { x: e.clientX - rect.left, y: e.clientY - rect.top };
    };

    const onDown = (e: PointerEvent) => {
      const { x, y } = local(e);
      pointerRef.current = { x, y };
      if (controller.wantsPointer(x, y)) {
        captureRef.current = true;
        e.stopPropagation();
        e.preventDefault();
        controller.pointerDown(x, y);
        scheduleDraw();
      }
    };

    const onMove = (e: PointerEvent) => {
      const { x, y } = local(e);
      pointerRef.current = { x, y };
      if (captureRef.current) {
        e.stopPropagation();
        e.preventDefault();
        controller.pointerMove(x, y);
      }
      scheduleDraw();
    };

    const onUp = (e: PointerEvent) => {
      if (captureRef.current) {
        captureRef.current = false;
        e.stopPropagation();
        e.preventDefault();
        controller.pointerUp();
        scheduleDraw();
      }
    };

    const onLeave = () => {
      pointerRef.current = null;
      scheduleDraw();
    };

    parent.addEventListener('pointerdown', onDown, true);
    parent.addEventListener('pointermove', onMove, true);
    parent.addEventListener('pointerup', onUp, true);
    parent.addEventListener('pointerleave', onLeave, true);
    return () => {
      parent.removeEventListener('pointerdown', onDown, true);
      parent.removeEventListener('pointermove', onMove, true);
      parent.removeEventListener('pointerup', onUp, true);
      parent.removeEventListener('pointerleave', onLeave, true);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [controller, tool]);

  function scheduleDraw() {
    if (rafRef.current != null) return;
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      draw();
    });
  }

  function draw() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const transform = transformRef.current;
    if (!transform) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(1, Math.round(rect.width));
    const height = Math.max(1, Math.round(rect.height));
    if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
      canvas.width = width * dpr;
      canvas.height = height * dpr;
    }
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const renderCtx = { ctx, width, height, dpr, transform, selectedId: manager.getSelected()?.id ?? null };

    // Live preview of an in-progress drawing.
    const pending = controller.getPendingDrawing();
    if (pending && pending.points.length > 0) {
      const preview = buildPreview(pending.tool, pending.points, pointerRef.current);
      if (preview) drawDrawing(renderCtx, preview);
    }

    for (const d of manager.getAll()) {
      drawDrawing(renderCtx, d);
    }

    const selected = manager.getSelected();
    if (selected && tool === 'cursor') {
      drawHandles(renderCtx, selected);
    }
  }

  function buildPreview(tool: DrawingToolMode, points: { time: number; price: number }[], cursor: { x: number; y: number } | null): ChartDrawing | null {
    const transform = transformRef.current;
    if (!transform) return null;
    const market = cursor ? transform.screenToMarket(cursor.x, cursor.y) : null;
    const base = {
      id: 'preview',
      type: tool as never,
      visible: true,
      locked: false,
      style: { color: '#7aff78', width: 1.5, lineStyle: 'solid' as const, opacity: 0.6 },
      createdAt: 0,
      updatedAt: 0,
    };
    const p1 = market ?? points[points.length - 1];
    switch (tool) {
      case 'trendline':
      case 'ray':
      case 'arrow':
      case 'rectangle':
      case 'fibonacci':
      case 'measure':
        return { ...base, start: points[0], end: p1 } as ChartDrawing;
      case 'horizontal':
        return { ...base, price: points[0].price } as ChartDrawing;
      case 'vertical':
        return { ...base, time: points[0].time } as ChartDrawing;
      case 'text':
        return { ...base, point: points[0], text: '' } as ChartDrawing;
      case 'long-position':
      case 'short-position':
        return { ...base, entry: points[0], stop: points[1] ?? p1, takeProfit: p1 } as ChartDrawing;
      default:
        return null;
    }
  }

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none absolute inset-0 z-10 h-full w-full"
      style={{ touchAction: 'none' }}
    />
  );
}
