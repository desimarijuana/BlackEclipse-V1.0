'use client';

// ── Drawing Tools ──────────────────────────────────────────────────────────────
// Registry of drawing tools. Each tool defines how many anchor points it needs
// and how a completed drawing is built from those points.

import type { ChartDrawing, ChartPoint, DrawingDefinition, DrawingType } from '@/lib/chart/types';
import { makeDrawing } from './manager';

const registry = new Map<DrawingType, DrawingDefinition>();

function register(def: DrawingDefinition) {
  registry.set(def.type, def);
}

register({ type: 'trendline', name: 'Trendline', description: 'Line between two points.', icon: 'trending-up', points: 2 });
register({ type: 'ray', name: 'Ray', description: 'Line extending from a point.', icon: 'move-diagonal', points: 2 });
register({ type: 'horizontal', name: 'Horizontal Line', description: 'Price level line.', icon: 'minus', points: 1 });
register({ type: 'vertical', name: 'Vertical Line', description: 'Time level line.', icon: 'move-vertical', points: 1 });
register({ type: 'rectangle', name: 'Rectangle', description: 'Box between two points.', icon: 'square', points: 2 });
register({ type: 'fibonacci', name: 'Fibonacci', description: 'Retracement levels.', icon: 'git-branch', points: 2 });
register({ type: 'text', name: 'Text', description: 'Label on the chart.', icon: 'type', points: 1, needsText: true });
register({ type: 'arrow', name: 'Arrow', description: 'Directional arrow.', icon: 'arrow-up-right', points: 2 });
register({ type: 'measure', name: 'Measure', description: 'Distance between two points.', icon: 'ruler', points: 2 });
register({ type: 'long-position', name: 'Long Position', description: 'Entry / stop / take-profit.', icon: 'trending-up', points: 3 });
register({ type: 'short-position', name: 'Short Position', description: 'Entry / stop / take-profit.', icon: 'trending-down', points: 3 });

export function getDrawingDef(type: DrawingType): DrawingDefinition | undefined {
  return registry.get(type);
}

export function getAllDrawingDefs(): DrawingDefinition[] {
  return Array.from(registry.values());
}

/** Build a completed drawing from the collected anchor points. */
export function buildDrawing(type: DrawingType, points: ChartPoint[], text?: string): ChartDrawing {
  const d = makeDrawing(type);
  switch (type) {
    case 'trendline':
    case 'ray':
    case 'arrow':
    case 'rectangle':
    case 'fibonacci':
    case 'measure':
      return { ...d, start: points[0], end: points[1] } as ChartDrawing;
    case 'horizontal':
      return { ...d, price: points[0].price } as ChartDrawing;
    case 'vertical':
      return { ...d, time: points[0].time } as ChartDrawing;
    case 'text':
      return { ...d, point: points[0], text: text ?? '' } as ChartDrawing;
    case 'long-position':
    case 'short-position':
      return { ...d, entry: points[0], stop: points[1], takeProfit: points[2] } as ChartDrawing;
  }
}
