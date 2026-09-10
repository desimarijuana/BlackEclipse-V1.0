'use client';

// ── Coordinate Transformer ────────────────────────────────────────────────────
// Converts between market coordinates (time + price) and screen pixels using the
// ECharts instance. ECharts' convertToPixel/convertFromPixel already account for
// grid position, zoom, pan, and device pixel ratio — we wrap them with pane
// awareness so drawings anchored to the price pane never use the volume/RSI
// coordinate system.

import type { ECharts } from 'echarts';
import type { ChartPoint } from '@/lib/chart/types';

export interface PaneInfo {
  id: string;
  type: 'price' | 'volume' | 'indicator';
  gridIndex: number;
}

/** The price pane is always grid 0 in the Eclipse provider. */
export const PRICE_PANE: PaneInfo = { id: 'price', type: 'price', gridIndex: 0 };

export interface CoordinateTransformer {
  /** Convert a market point to screen pixels within a pane. */
  marketToScreen(point: ChartPoint, pane?: PaneInfo): { x: number; y: number } | null;
  /** Convert screen pixels to a market point within a pane. */
  screenToMarket(x: number, y: number, pane?: PaneInfo): ChartPoint | null;
  /** The pixel rect of a pane's grid (for clipping). */
  paneRect(pane?: PaneInfo): { x: number; y: number; width: number; height: number } | null;
}

/**
 * Build a coordinate transformer bound to a live ECharts instance.
 * Returns null when the instance is not ready.
 */
export function createCoordinateTransformer(chart: ECharts | null): CoordinateTransformer | null {
  if (!chart) return null;

  return {
    marketToScreen(point, pane = PRICE_PANE) {
      try {
        const px = chart.convertToPixel({ gridIndex: pane.gridIndex }, [point.time, point.price]);
        if (px == null || !Array.isArray(px) || !Number.isFinite(px[0]) || !Number.isFinite(px[1])) return null;
        return { x: px[0], y: px[1] };
      } catch {
        return null;
      }
    },

    screenToMarket(x, y, pane = PRICE_PANE) {
      try {
        const m = chart.convertFromPixel({ gridIndex: pane.gridIndex }, [x, y]);
        if (m == null || !Array.isArray(m) || !Number.isFinite(m[0]) || !Number.isFinite(m[1])) return null;
        return { time: m[0], price: m[1] };
      } catch {
        return null;
      }
    },

    paneRect(pane = PRICE_PANE) {
      try {
        // Use convertToPixel at the grid corners to derive the pane rect.
        const topLeft = chart.convertToPixel({ gridIndex: pane.gridIndex }, [0, 0]);
        const bottomRight = chart.convertToPixel({ gridIndex: pane.gridIndex }, [1, 1]);
        if (!topLeft || !bottomRight || !Array.isArray(topLeft) || !Array.isArray(bottomRight)) return null;
        return {
          x: topLeft[0],
          y: topLeft[1],
          width: bottomRight[0] - topLeft[0],
          height: bottomRight[1] - topLeft[1],
        };
      } catch {
        return null;
      }
    },
  };
}
