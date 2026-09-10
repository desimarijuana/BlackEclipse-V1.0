'use client';

// ── Chart data hook ────────────────────────────────────────────────────────────
// Fetches normalized OHLCV bars from the JDdS-backed /api/price-history route.
// The chart never talks to a random API directly — all data flows through JDdS.

import { useEffect, useRef, useState } from 'react';
import type { ChartData, PriceBar, Timeframe } from '@/lib/chart/types';
import { timeframeToYahoo } from '@/lib/chart/types';

interface PriceHistoryResponse {
  symbol: string;
  currency: string;
  series: PriceBar[];
  source: string;
}

export interface UseChartDataResult {
  data: ChartData | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useChartData(symbol: string, market: string, timeframe: Timeframe): UseChartDataResult {
  const [data, setData] = useState<ChartData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const { interval, range } = timeframeToYahoo(timeframe);
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setError(null);

    const params = new URLSearchParams({
      symbol,
      market,
      range,
      interval,
    });

    fetch(`/api/price-history?${params.toString()}`, { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((json: PriceHistoryResponse) => {
        if (controller.signal.aborted) return;
        setData({
          symbol: json.symbol || symbol,
          market,
          currency: json.currency || '$',
          bars: json.series ?? [],
          source: json.source || 'none',
        });
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : 'Failed to load chart data');
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [symbol, market, timeframe, nonce]);

  return { data, loading, error, refresh: () => setNonce((n) => n + 1) };
}
