'use client';

// ── useFundData — one bundle of computed data per fund ───────────────────────
// Wires the pure engines: usePortfolioEngine (FIFO/LIFO) + usePriceHistories
// (real OHLCV) + portfolio-analysis (health, brief, attribution, stress…) +
// portfolio/matrix (correlation + risk decomposition).

import { useEffect, useMemo, useState } from 'react';
import { usePortfolioEngine, type LiveAssetInput } from '@/hooks/use-portfolio-engine';
import { usePriceHistories, type HistoryState } from '@/hooks/use-price-histories';
import {
  computeAttribution, computeHealthScore, buildBrief, buildChanges,
  type AttributionRow, type ChangeItem, type HealthScore,
} from '@/lib/portfolio-analysis';
import { buildHoldingMeta, computeRiskMetrics, type RiskMetrics } from '@/lib/portfolio/risk';
import { computeCorrelation, computeRiskMatrix, type CorrelationMatrix, type RiskMatrix, type Series } from '@/lib/portfolio/matrix';
import { fetchFxMatrix } from '@/lib/currency';
import { MARKET_CURRENCY } from '@/lib/markets';
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
  /** Pairwise correlation of holding returns (null until ≥2 usable series). */
  correlation: CorrelationMatrix | null;
  /** Per-holding risk + each position's share of total portfolio risk. */
  riskMatrix: RiskMatrix | null;
  health: HealthScore | null;
  brief: string[];
  changes: ChangeItem[];
  attribution: AttributionRow[];
  /** Symbol series missing from the price-history source (honest reporting). */
  missingSeries: string[];
  /** Non-USD holdings with no live FX rate — their USD value is a 1:1 estimate. */
  fxMissing: string[];
}

const BENCHMARK = 'SPY';

/** Currencies a fund can hold, derived from the symbols in its ledger. */
function currenciesOf(symbols: string[], quotes: Record<string, LiveQuote>): string[] {
  const set = new Set<string>();
  for (const s of symbols) {
    const q = quotes[s];
    if (q?.currency) set.add(q.currency);
  }
  return [...set];
}

export function useFundData(fund: Fund, taxMethod: 'FIFO' | 'LIFO' = 'FIFO'): FundData {
  const symbols = useMemo(
    () => [...new Set(fund.transactions.map(t => t.symbol.toUpperCase()))].filter(s => s && s !== 'CASH'),
    [fund.transactions],
  );
  const { quotes, loading: quotesLoading } = useLiveQuotes(symbols);
  const histories = usePriceHistories(symbols, Object.fromEntries(symbols.map(s => [s, marketHintFor(s)])));
  const bench = usePriceHistories([BENCHMARK], { [BENCHMARK]: 'GLOB' });

  // Live USD→X rates, so a non-USD holding converts at its real rate instead of
  // a hardcoded PKR constant. Only fetched when the book actually holds one.
  const currencies = currenciesOf(symbols, quotes);
  const currencyKey = currencies.join(',');
  const needsFx = currencies.some(c => c !== 'USD');
  const [rates, setRates] = useState<Record<string, number>>({ USD: 1 });
  useEffect(() => {
    if (!needsFx) { setRates({ USD: 1 }); return; }
    let cancelled = false;
    fetchFxMatrix().then(fx => { if (!cancelled) setRates(fx.rates); }).catch(() => { /* keep USD-only */ });
    return () => { cancelled = true; };
  }, [needsFx, currencyKey]);

  const liveAssets: LiveAssetInput[] = useMemo(
    () => symbols.map(sym => {
      const q = quotes[sym];
      const market = q?.marketId ?? marketHintFor(sym);
      const currency = q?.currency ?? MARKET_CURRENCY[market] ?? 'USD';
      // 1 unit of `currency` = fxToUsd USD. rates are USD→X, so invert; USD is 1.
      const rate = currency === 'USD' ? 1 : rates[currency];
      return {
        symbol: sym,
        price: q?.price,
        changePercent: q?.changePercent,
        currency,
        fxToUsd: currency === 'USD' ? 1 : (rate && rate > 0 ? 1 / rate : undefined),
        name: q?.name,
      };
    }),
    [symbols, quotes, rates],
  );

  const stats = usePortfolioEngine(fund.transactions, liveAssets, taxMethod);
  const cash = useMemo(() => computeCash(fund.transactions), [fund.transactions]);

  const missingSeries = useMemo(
    () => symbols.filter(s => !histories.closes[s] || histories.closes[s].length < 2),
    [symbols, histories],
  );

  const fxMissing = useMemo(
    () => stats.holdings.filter(h => h.fxMissing).map(h => h.symbol),
    [stats.holdings],
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

  // Series for the matrix widgets: holdings that actually have ≥2 closes, with
  // their dates. Weight and vol are read from the engine so the risk matrix
  // reflects real position sizes, not equal weights.
  const matrixSeries = useMemo<Series[]>(
    () => stats.holdings
      .filter(h => (histories.closes[h.symbol]?.length ?? 0) >= 2)
      .map(h => ({
        symbol: h.symbol,
        closes: histories.closes[h.symbol],
        dates: histories.dates[h.symbol] ?? [],
      })),
    [stats.holdings, histories],
  );

  const correlation = useMemo(
    () => (matrixSeries.length >= 2 ? computeCorrelation(matrixSeries) : null),
    [matrixSeries],
  );

  const riskMatrix = useMemo(() => {
    if (!correlation || !stats.holdings.length) return null;
    // Weights aligned to the correlation symbols (which exclude series-less rows).
    const weights = correlation.symbols.map(sym =>
      stats.holdings.find(h => h.symbol === sym)?.valueUsd ?? 0,
    );
    return computeRiskMatrix(matrixSeries, weights, correlation);
  }, [correlation, matrixSeries, stats.holdings]);

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
    loading, ready, quotes, histories, stats, cash, risk, correlation, riskMatrix,
    health, brief, changes, attribution, missingSeries, fxMissing,
  };
}
