'use client';

// ── useFundData — one bundle of computed data per fund ───────────────────────
// Wires the pure engines: usePortfolioEngine (FIFO/LIFO) + usePriceHistories
// (real OHLCV) + portfolio-analysis (health, brief, attribution, stress…).

import { useMemo } from 'react';
import { usePortfolioEngine, type LiveAssetInput } from '@/hooks/use-portfolio-engine';
import { usePriceHistories, type HistoryState } from '@/hooks/use-price-histories';
import {
  computeAttribution, computeHealthScore, buildBrief, buildChanges,
  type AttributionRow, type ChangeItem, type HealthScore,
} from '@/lib/portfolio-analysis';
import { buildHoldingMeta, computeRiskMetrics, type RiskMetrics } from '@/lib/portfolio/risk';
import { marketHintFor, useLiveQuotes, type LiveQuote } from './use-live-quotes';
import { computeCash } from './fund-store';
import type { Fund } from '@/lib/portfolio/types';

export interface FundData {
  loading: boolean;
  /** True once any live quote / history landed. */
  ready: boolean;
  quotes: Record<string, LiveQuote>;
  histories: HistoryState;
  stats: ReturnType<typeof usePortfolioEngine>;
  cash: number;
  risk: RiskMetrics;
  health: HealthScore | null;
  brief: string[];
  changes: ChangeItem[];
  attribution: AttributionRow[];
  /** Symbol series missing from the price-history source (honest reporting). */
  missingSeries: string[];
}

const BENCHMARK = 'SPY';

export function useFundData(fund: Fund, taxMethod: 'FIFO' | 'LIFO' = 'FIFO'): FundData {
  const symbols = useMemo(
    () => [...new Set(fund.transactions.map(t => t.symbol.toUpperCase()))].filter(s => s && s !== 'CASH'),
    [fund.transactions],
  );
  const { quotes, loading: quotesLoading } = useLiveQuotes(symbols);
  const histories = usePriceHistories(symbols, Object.fromEntries(symbols.map(s => [s, marketHintFor(s)])));
  const bench = usePriceHistories([BENCHMARK], { [BENCHMARK]: 'GLOB' });

  const liveAssets: LiveAssetInput[] = useMemo(
    () => symbols.map(sym => {
      const q = quotes[sym];
      return {
        symbol: sym,
        price: q?.price,
        changePercent: q?.changePercent,
        currency: q?.currency ?? (marketHintFor(sym) === 'PK' ? 'PKR' : 'USD'),
        name: q?.name,
      };
    }),
    [symbols, quotes],
  );

  const stats = usePortfolioEngine(fund.transactions, liveAssets, taxMethod);
  const cash = useMemo(() => computeCash(fund.transactions), [fund.transactions]);

  const missingSeries = useMemo(
    () => symbols.filter(s => !histories.closes[s] || histories.closes[s].length < 2),
    [symbols, histories],
  );

  const risk = useMemo(() => {
    if (!stats.holdings.length) {
      return { nav: [], navDates: [], benchmarkNav: [], vol: null, beta: null, sharpe: null, mdd: null };
    }
    return computeRiskMetrics(
      stats.holdings.map(h => ({ symbol: h.symbol, weight: h.valueUsd })),
      histories.closes,
      histories.dates,
      bench.closes[BENCHMARK] ?? [],
    );
  }, [stats.holdings, histories, bench]);

  const meta = useMemo(
    () => buildHoldingMeta(
      stats.holdings.map(h => ({ symbol: h.symbol, dayPct: h.dayPct, value: h.valueUsd })),
      stats.totalValue,
      histories.closes,
      bench.closes[BENCHMARK] ?? [],
      s => marketHintFor(s) === 'CRYPTO',
    ),
    [stats.holdings, stats.totalValue, histories, bench],
  );

  const health = useMemo(
    () => (stats.holdings.length ? computeHealthScore(
      stats.holdings.map(h => ({
        symbol: h.symbol, quantity: h.quantity, avgCost: h.avgCost,
        currentPrice: h.currentPrice, value: h.valueUsd,
        unrealizedPnL: h.unrealizedPnLUsd, allocation: h.allocation, realizedPnL: h.realizedPnLUsd,
      })),
      meta,
    ) : null),
    [stats.holdings, meta],
  );

  const brief = useMemo(() => buildBrief(stats, stats.holdings.map(h => ({
    symbol: h.symbol, quantity: h.quantity, avgCost: h.avgCost,
    currentPrice: h.currentPrice, value: h.valueUsd,
    unrealizedPnL: h.unrealizedPnLUsd, allocation: h.allocation, realizedPnL: h.realizedPnLUsd,
  })), meta), [stats, meta]);

  const changes = useMemo(() => buildChanges(stats.holdings.map(h => ({
    symbol: h.symbol, quantity: h.quantity, avgCost: h.avgCost,
    currentPrice: h.currentPrice, value: h.valueUsd,
    unrealizedPnL: h.unrealizedPnLUsd, allocation: h.allocation, realizedPnL: h.realizedPnLUsd,
  })), meta), [stats.holdings, meta]);

  const attribution = useMemo(
    () => computeAttribution(stats.holdings.map(h => ({
      symbol: h.symbol, quantity: h.quantity, avgCost: h.avgCost,
      currentPrice: h.currentPrice, value: h.valueUsd,
      unrealizedPnL: h.unrealizedPnLUsd, allocation: h.allocation, realizedPnL: h.realizedPnLUsd,
    })), stats.costBasis),
    [stats.holdings, stats.costBasis],
  );

  const loading = quotesLoading || histories.loading;
  const ready = Object.keys(quotes).length > 0 || histories.ok;

  return {
    loading, ready, quotes, histories, stats, cash, risk, health, brief, changes, attribution, missingSeries,
  };
}
