'use client';

// ── Compare data hook ─────────────────────────────────────────────────────────
// Resolves each compare symbol's OHLCV series to the PRIMARY chart's bar axis so
// they can be overlaid as relative-performance (% change) lines. Comparison
// always rebases to the first bar of the compare series, matching TradingView.
//
// All data flows through JDdS (/api/price-history) — never a third-party API.

import { useEffect, useState } from 'react';
import type { ChartCompareItem, ChartCompareSeries, ChartData, Timeframe } from '@/lib/chart/types';
import { timeframeToYahoo } from '@/lib/chart/types';

interface CompareBar { date: string; close: number }

async function fetchSeries(symbol: string, market: string, timeframe: Timeframe, signal: AbortSignal): Promise<CompareBar[] | null> {
  const { interval, range } = timeframeToYahoo(timeframe);
  const params = new URLSearchParams({ symbol, market, range, interval });
  const res = await fetch(`/api/price-history?${params.toString()}`, { signal });
  if (!res.ok) return null;
  const json = (await res.json()) as { series?: CompareBar[] };
  return json.series ?? [];
}

/**
 * Fetch + rebase compare series against the primary chart's bars. Returns an
 * empty array until both the primary bars and all compare fetches are ready.
 */
export function useCompareData(primary: ChartData | null, items: ChartCompareItem[], timeframe: Timeframe): ChartCompareSeries[] {
  const [series, setSeries] = useState<ChartCompareSeries[]>([]);

  useEffect(() => {
    if (!primary || primary.bars.length === 0 || items.length === 0) {
      setSeries([]);
      return;
    }
    const controller = new AbortController();
    const primaryDates = primary.bars.map((b) => b.date);

    Promise.all(
      items.map(async (item): Promise<ChartCompareSeries | null> => {
        const bars = await fetchSeries(item.symbol, item.market, timeframe, controller.signal);
        if (!bars || bars.length === 0) return null;
        const byDate = new Map(bars.map((b) => [b.date, b.close]));
        const base = bars[0]?.close ?? 0;
        if (!base) return null;
        // Align each compare close to the primary bar dates (null = no data).
        const values = primaryDates.map((d) => byDate.get(d) ?? null);
        const last = [...values].reverse().find((v): v is number => v != null) ?? base;
        return {
          id: item.id,
          symbol: item.symbol,
          color: item.color,
          values,
          changePercent: +(((last - base) / base) * 100).toFixed(2),
        };
      }),
    )
      .then((res) => {
        if (controller.signal.aborted) return;
        setSeries(res.filter((s): s is ChartCompareSeries => s != null));
      })
      .catch(() => { /* keep the previous series on failure */ });

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [primary, timeframe, JSON.stringify(items.map((i) => `${i.id}:${i.color}`))]);

  return series;
}
