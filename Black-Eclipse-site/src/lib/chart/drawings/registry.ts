'use client';

// ── Drawing Registry (Phase 3) ────────────────────────────────────────────────
// Registry-driven drawing tools. Each tool defines how many anchor points it
// needs and how it's rendered. The EclipseChartProvider renders drawings as
// ECharts markLine/markPoint/markArea overlays.

import type { ChartDrawing, ChartPoint, DrawingDefinition, DrawingType } from '@/lib/chart/types';

const registry = new Map<DrawingType, DrawingDefinition>();

function register(def: DrawingDefinition) {
  registry.set(def.type, def);
}

register({ type: 'trendline', name: 'Trendline', description: 'Line between two points.', icon: 'trending-up', points: 2 });
register({ type: 'ray', name: 'Ray', description: 'Line extending from a point.', icon: 'arrow-right', points: 2 });
register({ type: 'horizontal', name: 'Horizontal Line', description: 'Price level line.', icon: 'minus', points: 1 });
register({ type: 'vertical', name: 'Vertical Line', description: 'Time level line.', icon: 'move-vertical', points: 1 });
register({ type: 'rectangle', name: 'Rectangle', description: 'Box between two points.', icon: 'square', points: 2 });
register({ type: 'fibonacci', name: 'Fibonacci', description: 'Retracement levels.', icon: 'git-branch', points: 2 });
register({ type: 'text', name: 'Text', description: 'Label on the chart.', icon: 'type', points: 1, needsText: true });

/** Get a drawing tool definition by type. */
export function getDrawingDef(type: DrawingType): DrawingDefinition | undefined {
  return registry.get(type);
}

/** All registered drawing tools. */
export function getAllDrawingDefs(): DrawingDefinition[] {
  return Array.from(registry.values());
}

/** Create a new drawing with a fresh id. */
export function createDrawing(type: DrawingType, points: ChartPoint[], text?: string): ChartDrawing {
  return {
    type,
    id: `drawing-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    points,
    text,
    style: { color: '#7aff78', lineWidth: 1.5, lineStyle: 'solid' },
  };
}

/** Convert a drawing to ECharts markLine/markPoint/markArea config. */
export function drawingToMark(drawing: ChartDrawing): {
  markLine?: Record<string, unknown>;
  markPoint?: Record<string, unknown>;
  markArea?: Record<string, unknown>;
} {
  const color = drawing.style?.color ?? '#7aff78';
  const lineStyle = drawing.style?.lineStyle ?? 'solid';
  const lineWidth = drawing.style?.lineWidth ?? 1.5;
  const [p0, p1] = drawing.points;

  switch (drawing.type) {
    case 'horizontal':
      return {
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color, width: lineWidth, type: lineStyle },
          label: { show: true, position: 'end', color, fontSize: 9, fontFamily: 'monospace', formatter: (p: { value: number }) => p.value.toFixed(2) },
          data: [{ yAxis: p0.y }],
        },
      };
    case 'vertical':
      return {
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color, width: lineWidth, type: lineStyle },
          label: { show: false },
          data: [{ xAxis: p0.x }],
        },
      };
    case 'trendline':
    case 'ray':
      return {
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color, width: lineWidth, type: lineStyle },
          label: { show: false },
          data: [
            { xAxis: p0.x, yAxis: p0.y },
            { xAxis: p1.x, yAxis: p1.y },
          ],
        },
      };
    case 'rectangle':
      return {
        markArea: {
          silent: true,
          itemStyle: { color: color + '18', borderColor: color, borderWidth: 1 },
          data: [
            [
              { xAxis: p0.x, yAxis: p0.y },
              { xAxis: p1.x, yAxis: p1.y },
            ],
          ],
        },
      };
    case 'fibonacci':
      return {
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color, width: lineWidth, type: lineStyle },
          label: { show: true, position: 'insideEndTop', color, fontSize: 8, fontFamily: 'monospace' },
          data: fibLevels(p0, p1).map((l) => ({ yAxis: l.price, label: { formatter: l.label } })),
        },
      };
    case 'text':
      return {
        markPoint: {
          silent: true,
          symbol: 'circle',
          symbolSize: 0,
          label: { show: true, position: 'top', color, fontSize: 11, fontFamily: 'monospace', formatter: drawing.text ?? '' },
          data: [{ coord: [p0.x, p0.y] }],
        },
      };
    default:
      return {};
  }
}

/** Fibonacci retracement levels between two prices. */
function fibLevels(p0: ChartPoint, p1: ChartPoint): Array<{ price: number; label: string }> {
  const levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];
  const high = Math.max(p0.y, p1.y);
  const low = Math.min(p0.y, p1.y);
  const range = high - low;
  return levels.map((l) => ({
    price: high - range * l,
    label: `${(l * 100).toFixed(l === 0 || l === 1 ? 0 : 1)}%`,
  }));
}
