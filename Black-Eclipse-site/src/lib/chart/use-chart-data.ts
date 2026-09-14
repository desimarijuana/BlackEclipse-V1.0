'use client';

// ── Chart data hook ────────────────────────────────────────────────────────────
// Fetches normalized OHLCV bars from the JDdS-backed /api/price-history route.
// The chart never talks to a random API directly — all data flows through JDdS.
//
// Delegates to the process-wide DataSubscriptionManager so MULTIPLE charts of
// the same symbol|market|timeframe share ONE request + cache + poll (spec §9).
// A workspace with three AAPL panels makes one upstream call, not three.

import type { ChartData, Timeframe } from '@/lib/chart/types';
import { useChartBars } from './subscription-manager';

export interface UseChartDataResult {
  data: ChartData | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useChartData(symbol: string, market: string, timeframe: Timeframe): UseChartDataResult {
  const { data, loading, error, refresh } = useChartBars(symbol, market, timeframe);
  return { data, loading, error, refresh };
}
