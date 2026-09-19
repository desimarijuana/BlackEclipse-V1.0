'use client';

// ── Fundamentals data hook ──────────────────────────────────────────────────
// Talks only to /api/fundamentals (the provider abstraction). The screen never
// imports Yahoo/SEC/FMP modules. Handles loading, unavailable and refresh.

import { useCallback, useEffect, useRef, useState } from 'react';
import type { FundamentalsSnapshot } from '@/lib/fundamentals/types';

export interface FundamentalsState {
  data: FundamentalsSnapshot | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  /** True when the provider layer had nothing for this symbol. */
  unavailable: boolean;
  refresh: () => void;
}

export function useFundamentals(symbol: string, market: string): FundamentalsState {
  const [data, setData] = useState<FundamentalsSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const requestId = useRef(0);

  const load = useCallback(
    async (force: boolean) => {
      const id = ++requestId.current;
      if (force) setRefreshing(true);
      else setLoading(true);
      setError(null);
      try {
        const qs = new URLSearchParams({ symbol, market });
        if (force) qs.set('refresh', '1');
        const res = await fetch(`/api/fundamentals?${qs.toString()}`, { cache: 'no-store' });
        const body = (await res.json()) as
          | ({ available: true } & FundamentalsSnapshot)
          | { available: false; reason?: string };
        if (id !== requestId.current) return;
        if (!body.available) {
          setData(null);
          setUnavailable(true);
          setError(body.reason ?? 'No fundamentals available.');
        } else {
          const { available: _available, ...snapshot } = body;
          setData(snapshot as FundamentalsSnapshot);
          setUnavailable(false);
        }
      } catch {
        if (id !== requestId.current) return;
        setUnavailable(false);
        setError('Fundamentals request failed.');
      } finally {
        if (id === requestId.current) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    },
    [symbol, market]
  );

  useEffect(() => {
    // An empty symbol means "not active" (e.g. the screener popup's lazy tab).
    // Clear loading so a caller that mounts us before a symbol exists never
    // shows a stuck spinner.
    if (!symbol) {
      setLoading(false);
      return;
    }
    void load(false);
  }, [symbol, load]);

  const refresh = useCallback(() => {
    void load(true);
  }, [load]);

  return { data, loading, refreshing, error, unavailable, refresh };
}
