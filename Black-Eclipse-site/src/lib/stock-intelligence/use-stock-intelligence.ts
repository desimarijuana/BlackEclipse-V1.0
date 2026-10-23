'use client';

// Client-side reader for /api/stocks/[symbol]/intelligence. The route owns all
// retrieval (fundamentals providers + Yahoo price history); this hook only
// handles request state so the overlay can render provenance honestly.

import { useCallback, useEffect, useRef, useState } from 'react';
import type { StockIntelligenceResponse } from './types';

export interface StockIntelligenceState {
  data: StockIntelligenceResponse | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useStockIntelligence(
  symbol: string,
  market: string,
  enabled = true,
): StockIntelligenceState {
  const [data, setData] = useState<StockIntelligenceResponse | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);

  const load = useCallback(async () => {
    if (!enabled || !symbol) {
      setLoading(false);
      return;
    }
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams({ market });
      const res = await fetch(
        `/api/stocks/${encodeURIComponent(symbol)}/intelligence?${qs.toString()}`,
        { cache: 'no-store' },
      );
      const body = (await res.json()) as StockIntelligenceResponse;
      if (id !== requestId.current) return;
      if (!body.available) {
        setData(null);
        setError(body.reason ?? 'Stock intelligence is unavailable.');
      } else {
        setData(body);
      }
    } catch {
      if (id !== requestId.current) return;
      setData(null);
      setError('Stock intelligence request failed.');
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [symbol, market, enabled]);

  useEffect(() => {
    void load();
  }, [load]);

  return { data, loading, error, refresh: load };
}
