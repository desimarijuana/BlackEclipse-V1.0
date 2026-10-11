'use client';

// ── ResponseFinancialChart — wraps the EXISTING terminal chart ────────────────
// A `financial_chart` block carries only a symbol + optional view state; the
// widget fetches live OHLCV itself (via the existing chart/data layer), so it is
// never a stale snapshot and no market data is embedded in the response. Loaded
// lazily because the chart provider stack is heavy.

import { useMemo, useState } from 'react';
import { ChartWidget } from '@/components/chart/chart-widget';
import {
  defaultChartState,
  type ChartState,
  type ChartType,
  type Timeframe,
} from '@/lib/chart/types';
import type { FinancialChartBlock } from '@/lib/response/contract';

export interface ResponseFinancialChartProps {
  block: FinancialChartBlock;
  height?: number;
}

export function ResponseFinancialChart({ block, height = 440 }: ResponseFinancialChartProps) {
  const initialState = useMemo(
    () =>
      defaultChartState({
        symbol: block.symbol.toUpperCase(),
        ...(block.market ? { market: block.market } : {}),
        ...(block.timeframe ? { timeframe: block.timeframe as Timeframe } : {}),
        ...(block.chartType ? { chartType: block.chartType as ChartType } : {}),
      }),
    [block],
  );
  const [state, setState] = useState<ChartState>(initialState);

  return (
    <div className="w-full overflow-hidden rounded-xl border border-white/10" style={{ height }}>
      <ChartWidget state={state} onStateChange={setState} className="h-full" />
    </div>
  );
}

export default ResponseFinancialChart;
