'use client';

// ── Chart provider factory ────────────────────────────────────────────────────
// Creates a ChartProvider instance for a given provider id. The ChartWidget
// uses this so it never constructs a concrete provider directly.

import type { ChartProvider, ChartProviderId, ChartState } from '@/lib/chart/types';
import { EclipseChartProvider } from '@/lib/chart/providers/eclipse-provider';
import { TradingViewProvider } from '@/lib/chart/providers/tradingview-provider';

export function createChartProvider(id: ChartProviderId, state: ChartState): ChartProvider {
  switch (id) {
    case 'eclipse':
      return new EclipseChartProvider(state);
    case 'tradingview':
      return new TradingViewProvider(state);
  }
}
