'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { StockVerificationResponse } from './verification';

export interface StockVerificationState {
  data: StockVerificationResponse | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useStockVerification({
  symbol,
  market,
  name,
  price,
  enabled = true,
}: {
  symbol: string;
  market: string;
  name?: string | null;
  price?: number | null;
  enabled?: boolean;
}): StockVerificationState {
  const [data, setData] = useState<StockVerificationResponse | null>(null);
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
      if (name) qs.set('name', name);
      if (price != null && Number.isFinite(price) && price > 0) qs.set('price', String(price));
      const res = await fetch(
        `/api/stocks/${encodeURIComponent(symbol)}/verification?${qs.toString()}`,
        { cache: 'no-store' },
      );
      const body = (await res.json()) as StockVerificationResponse;
      if (id !== requestId.current) return;
      if (!body.available) {
        setData(null);
        setError(body.reason ?? 'Eclipse could not verify a source for this symbol.');
      } else {
        setData(body);
      }
    } catch {
      if (id !== requestId.current) return;
      setData(null);
      setError('Source verification request failed.');
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [symbol, market, name, price, enabled]);

  useEffect(() => {
    void load();
  }, [load]);

  return { data, loading, error, refresh: load };
}
