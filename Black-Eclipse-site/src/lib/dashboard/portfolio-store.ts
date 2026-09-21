'use client';

// ── Guest portfolio store ────────────────────────────────────────────────────
// Bridges the localStorage fund book (seeded demo funds + user transactions)
// into the Command Center without duplicating the portfolio engine. Live quotes
// are fetched from JDDS and cached per symbol-set so multiple portfolio widgets
// share one request. Never fabricates prices — holdings without a quote keep
// their last known cost basis and are flagged by the engine.

import { useEffect, useMemo, useState } from 'react';
import { loadFunds, FUNDS_CHANGED_EVENT } from '@/components/screens/portfolio/fund-store';
import { computePortfolioStats, usePortfolioEngine, type LiveAssetInput, type PortfolioStats } from '@/hooks/use-portfolio-engine';
import { usePriceHistories } from '@/hooks/use-price-histories';
import { marketHintFor } from '@/components/screens/portfolio/use-live-quotes';
import { computeRiskMetrics } from '@/lib/portfolio/risk';
import { buildPortfolioPerformance, type PerformanceSeries, type PriceHistorySeries } from './portfolio-performance';
import type { Fund } from '@/lib/portfolio/types';

export interface QuoteRow {
  symbol: string;
  name: string;
  price: number;
  changePercent: number;
  currency: string;
  marketId?: string;
  /** JDDS `Asset.sector`, when the instrument has one. */
  sector?: string;
  found: boolean;
}

/** A single line on a performance chart (nav indexed to ~1). */
export interface PerformanceLine {
  name: string;
  color: string;
  nav: number[];
  dates: string[];
  dashed: boolean;
}

/** Default comparison instruments, matching the Portfolio page. */
export const DEFAULT_BENCHMARKS: Array<{ symbol: string; name: string; color: string }> = [
  { symbol: 'SPY', name: 'S&P 500', color: '#94a3b8' },
  { symbol: 'QQQ', name: 'Nasdaq 100', color: '#64748b' },
  { symbol: 'BTC-USD', name: 'Bitcoin', color: '#fbbf24' },
];

const quoteCache = new Map<string, { t: number; data: QuoteRow[] }>();
const QUOTE_TTL = 60_000;

/** Reactive read of the guest fund book (same-tab + cross-tab). */
export function useGuestFunds(): Fund[] {
  const [funds, setFunds] = useState<Fund[]>([]);
  useEffect(() => {
    const sync = () => { try { setFunds(loadFunds().funds); } catch { setFunds([]); } };
    sync();
    window.addEventListener('storage', sync);
    window.addEventListener(FUNDS_CHANGED_EVENT, sync);
    return () => {
      window.removeEventListener('storage', sync);
      window.removeEventListener(FUNDS_CHANGED_EVENT, sync);
    };
  }, []);
  return funds;
}

/** Every symbol held across all funds (excludes the CASH pseudo-symbol). */
function heldSymbols(funds: Fund[]): string[] {
  return [...new Set(funds.flatMap(f => f.transactions.map(t => t.symbol.toUpperCase())))].filter(s => s && s !== 'CASH');
}

/** Fetch (and cache) quotes for a symbol set. */
async function loadQuotes(symbols: string[]): Promise<QuoteRow[]> {
  const key = symbols.join(',');
  const cached = quoteCache.get(key);
  if (cached && Date.now() - cached.t < QUOTE_TTL) return cached.data;
  const res = await fetch(`/api/quote?symbols=${encodeURIComponent(key)}`);
  const d = (await res.json()) as { quotes?: QuoteRow[] };
  const data = (d.quotes ?? []).filter(q => q.found && q.price > 0);
  quoteCache.set(key, { t: Date.now(), data });
  return data;
}

function toLiveAssets(quotes: QuoteRow[]): LiveAssetInput[] {
  return quotes.map(q => ({
    symbol: q.symbol,
    price: q.price,
    changePercent: q.changePercent,
    name: q.name,
    currency: q.marketId === 'PK' ? 'PKR' : 'USD',
  }));
}

function marketsFor(symbols: string[]): Record<string, string> {
  return Object.fromEntries(symbols.map(s => [s, marketHintFor(s)]));
}

function toHistoryMap(
  symbols: string[],
  closes: Record<string, number[]>,
  dates: Record<string, string[]>,
): Map<string, PriceHistorySeries> {
  const map = new Map<string, PriceHistorySeries>();
  for (const s of symbols) {
    const c = closes[s];
    const d = dates[s];
    if (c && c.length >= 2) map.set(s, { closes: c, dates: d ?? [] });
  }
  return map;
}

/** Aggregate portfolio across every fund, priced with live JDDS quotes. */
export function useAggregatePortfolio(): { funds: Fund[]; stats: PortfolioStats; quotes: QuoteRow[] } {
  const funds = useGuestFunds();
  const symbols = useMemo(() => heldSymbols(funds), [funds]);
  const key = symbols.join(',');
  const [quotes, setQuotes] = useState<QuoteRow[]>(() => quoteCache.get(key)?.data ?? []);

  useEffect(() => {
    if (!key) { setQuotes([]); return; }
    let cancelled = false;
    loadQuotes(symbols)
      .then(data => { if (!cancelled) setQuotes(data); })
      .catch(() => { /* keep last known */ });
    return () => { cancelled = true; };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  const transactions = useMemo(() => funds.flatMap(f => f.transactions), [funds]);
  const live = useMemo(() => toLiveAssets(quotes), [quotes]);
  const stats = usePortfolioEngine(transactions, live);
  return { funds, stats, quotes };
}

/**
 * Aggregate performance curve for ALL funds + user-selected comparison
 * benchmarks, computed from real price histories.
 */
export function usePortfolioPerformance(compare: string[]): PerformanceSeries | null {
  const funds = useGuestFunds();
  const { quotes } = useAggregatePortfolio();
  const symbols = useMemo(() => heldSymbols(funds), [funds]);
  const compareKey = useMemo(
    () => [...new Set(compare.map(s => s.toUpperCase().trim()).filter(Boolean))].slice(0, 6).join(','),
    [compare],
  );
  const compareList = useMemo(() => (compareKey ? compareKey.split(',') : []), [compareKey]);
  const allSymbols = useMemo(() => [...new Set([...symbols, ...compareList])], [symbols, compareList]);
  const histories = usePriceHistories(allSymbols, useMemo(() => marketsFor(allSymbols), [allSymbols]));

  const fx = useMemo(() => new Map(quotes.map(q => [q.symbol.toUpperCase(), q.marketId === 'PK' ? 1 / 278 : 1])), [quotes]);
  const livePrice = useMemo(() => new Map(quotes.map(q => [q.symbol.toUpperCase(), q.price])), [quotes]);

  return useMemo(() => {
    const holdingHist = toHistoryMap(symbols, histories.closes, histories.dates);
    const benchmarks = compareList.map(symbol => ({
      symbol,
      history: { closes: histories.closes[symbol] ?? [], dates: histories.dates[symbol] ?? [] },
    }));
    const transactions = funds.flatMap(f => f.transactions);
    const built = buildPortfolioPerformance(transactions, holdingHist, benchmarks, fx, livePrice);
    return built.dates.length >= 2 ? built : null;
  }, [funds, symbols, compareList, histories, fx, livePrice]);
}

/**
 * One indexed performance line per fund (against each other), plus the standard
 * benchmarks as dashed reference lines. Mirrors the Portfolio page overview.
 */
export function useFundComparison(): { lines: PerformanceLine[]; ready: boolean } {
  const funds = useGuestFunds();
  const { quotes } = useAggregatePortfolio();
  const symbols = useMemo(() => heldSymbols(funds), [funds]);
  const allSymbols = useMemo(
    () => [...new Set([...symbols, ...DEFAULT_BENCHMARKS.map(b => b.symbol)])],
    [symbols],
  );
  const histories = usePriceHistories(allSymbols, useMemo(() => marketsFor(allSymbols), [allSymbols]));
  const liveAssets = useMemo(() => toLiveAssets(quotes), [quotes]);

  const lines = useMemo(() => {
    const out: PerformanceLine[] = [];
    for (const f of funds) {
      const stats = computePortfolioStats(f.transactions, liveAssets);
      if (stats.holdings.length === 0) continue;
      const r = computeRiskMetrics(
        stats.holdings.map(h => ({ symbol: h.symbol, weight: h.valueUsd })),
        histories.closes,
        histories.dates,
        [],
      );
      if (r.nav.length >= 2) {
        out.push({ name: f.name, color: f.accent || '#34d399', nav: r.nav, dates: r.navDates, dashed: false });
      }
    }
    for (const b of DEFAULT_BENCHMARKS) {
      const r = computeRiskMetrics([{ symbol: b.symbol, weight: 1 }], histories.closes, histories.dates, []);
      if (r.nav.length >= 2) {
        out.push({ name: b.name, color: b.color, nav: r.nav, dates: r.navDates, dashed: true });
      }
    }
    return out;
  }, [funds, liveAssets, histories]);

  return { lines, ready: histories.ok };
}
