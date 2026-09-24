'use client';

// ── Market Workspace — DataSubscriptionManager ───────────────────────────────
// One process-wide manager for every chart/quote subscription in the terminal.
//
// WHY: a workspace can hold 6–12 charts. Three panels showing AAPL must NOT
// each fire their own /api/price-history request (that triples upstream load
// and makes upstream rate-limit us). This manager keys every subscription by
// its DATA IDENTITY (symbol|market|timeframe for bars, symbol|market for a
// quote) so N consumers share ONE fetch + ONE cache entry + ONE poll timer.
//
// Consumers subscribe through hooks (useChartBars / useLiveQuote) which only
// re-render when the data they subscribe to actually changes.

import { useEffect, useState } from 'react';
import type { ChartData, PriceBar, Timeframe } from '@/lib/chart/types';
import { timeframeToYahoo } from '@/lib/chart/types';
import { ttlForInterval } from '@/lib/chart/price-history-ttl';
export type DataSource = 'LIVE' | 'DELAYED' | 'DEMO' | 'CLOSED' | 'UNAVAILABLE';

export interface BarsEntry {
  data: ChartData | null;
  loading: boolean;
  error: string | null;
  source: DataSource;
  updatedAt: number | null;
}

export interface QuoteEntry {
  price: number | null;
  changePercent: number;
  currency: string;
  found: boolean;
  updatedAt: string | null;
  at: number | null;
}

const QUOTE_POLL_MS = 30_000;

/**
 * Bars cache lifetime for a timeframe. Intraday candles go stale within
 * seconds, so a flat 10-minute TTL made the candle chart visibly lag the live
 * price. The interval mapping is shared with the server cache
 * (`price-history-ttl.ts`) so both sides agree. Daily/weekly/monthly keep the
 * long TTL (a day bar does not change intraday).
 */
export function barsTtl(timeframe: Timeframe): number {
  return ttlForInterval(timeframeToYahoo(timeframe).interval);
}

/**
 * Silent auto-refresh cadence for intraday timeframes (0 = none). Bounded below
 * by the bar size so we never poll faster than the series can change; daily and
 * above need no timer (the market-open refresh below covers them).
 */
export function barsRefreshMs(timeframe: Timeframe): number {
  switch (timeframe) {
    case '1m':
    case '3m': return 60_000;
    case '5m': return 2 * 60_000;
    case '15m':
    case '30m': return 5 * 60_000;
    case '1H':
    case '2H':
    case '4H': return 10 * 60_000;
    default: return 0;
  }
}

interface PriceHistoryResponse {
  symbol: string;
  currency: string;
  series: PriceBar[];
  source: string;
}

export interface QuoteRow {
  symbol: string;
  name: string;
  price: number;
  changePercent: number;
  currency: string;
  marketId?: string;
  found: boolean;
}

export interface BatchEntry {
  rows: QuoteRow[];
  at: number | null;
}

type BarsListener = (entry: BarsEntry) => void;
type QuoteListener = (entry: QuoteEntry) => void;
type BatchListener = (entry: BatchEntry) => void;

interface BatchState {
  entry: BatchEntry;
  listeners: Set<BatchListener>;
  timer: ReturnType<typeof setInterval> | null;
  inFlight: boolean;
  symbols: string[];
}

const EMPTY_BATCH: BatchEntry = { rows: [], at: null };

interface BarsState {
  entry: BarsEntry;
  listeners: Set<BarsListener>;
  lastFetch: number;
  inFlight: Promise<void> | null;
  nonce: number;
  /** Intraday auto-refresh timer (0/none for daily+). */
  timer: ReturnType<typeof setInterval> | null;
  timeframe: Timeframe;
}

interface QuoteState {
  entry: QuoteEntry;
  listeners: Set<QuoteListener>;
  timer: ReturnType<typeof setInterval> | null;
  inFlight: boolean;
}

export class DataSubscriptionManager {
  private bars = new Map<string, BarsState>();
  private quotes = new Map<string, QuoteState>();

  // ── Bars (OHLCV history) ───────────────────────────────────────────────────
  private barsKey(symbol: string, market: string, timeframe: Timeframe): string {
    return `${symbol.toUpperCase()}|${market.toUpperCase()}|${timeframe}`;
  }

  subscribeBars(symbol: string, market: string, timeframe: Timeframe, listener: BarsListener): () => void {
    const key = this.barsKey(symbol, market, timeframe);
    let state = this.bars.get(key);
    if (!state) {
      state = {
        entry: { data: null, loading: false, error: null, source: 'UNAVAILABLE', updatedAt: null },
        listeners: new Set(),
        lastFetch: 0,
        inFlight: null,
        nonce: 0,
        timer: null,
        timeframe,
      };
      this.bars.set(key, state);
    }
    state.listeners.add(listener);
    if (state.entry.data) listener(state.entry);
    // Fetch when empty or stale; dedup via the inFlight promise.
    if (!state.entry.data || Date.now() - state.lastFetch > barsTtl(timeframe)) {
      this.fetchBars(key, symbol, market, timeframe);
    }
    // Intraday candles must keep updating even while the panel sits open —
    // previously the candle series was only re-fetched on a 10-minute TTL, so
    // it silently drifted behind the live quote.
    if (!state.timer) {
      const refreshMs = barsRefreshMs(timeframe);
      if (refreshMs > 0) {
        state.timer = setInterval(() => this.fetchBars(key, symbol, market, timeframe), refreshMs);
      }
    }
    return () => this.unsubscribeBars(key, listener);
  }

  private unsubscribeBars(key: string, listener: BarsListener): void {
    const state = this.bars.get(key);
    if (!state) return;
    state.listeners.delete(listener);
    // Stop the intraday timer when the last listener leaves (no background burn).
    if (state.listeners.size === 0 && state.timer) {
      clearInterval(state.timer);
      state.timer = null;
    }
    // Keep the entry after the last listener leaves so a remount reuses the
    // cache AND so an in-flight fetch can still land in a live state object.
    // Only prune a never-fetched, already-settled, empty entry.
    if (state.listeners.size === 0 && !state.entry.data && !state.inFlight) {
      this.bars.delete(key);
    }
  }

  /** Force-refresh one identity (bypasses TTL). */
  refreshBars(symbol: string, market: string, timeframe: Timeframe): void {
    const key = this.barsKey(symbol, market, timeframe);
    this.fetchBars(key, symbol, market, timeframe);
  }

  private fetchBars(key: string, symbol: string, market: string, timeframe: Timeframe): void {
    const state = this.bars.get(key);
    if (!state || state.inFlight) return;
    const { interval, range } = timeframeToYahoo(timeframe);
    const params = new URLSearchParams({ symbol, market, range, interval });
    // Only surface a loading state when there is nothing to show yet. A silent
    // background refresh keeps the current candles on screen instead of
    // flashing the chart back to a loader every poll.
    if (!state.entry.data) {
      state.entry = { ...state.entry, loading: true, error: null };
      this.emitBars(key);
    }

    const run = (async () => {
      try {
        const res = await fetch(`/api/price-history?${params.toString()}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = (await res.json()) as PriceHistoryResponse;
        const bars = json.series ?? [];
        if (bars.length === 0) {
          this.setBars(key, { data: null, loading: false, error: null, source: 'UNAVAILABLE', updatedAt: Date.now() });
          return;
        }
        const source: DataSource = json.source === 'yfinance' ? 'LIVE' : json.source === 'snapshot' ? 'DELAYED' : json.source === 'demo' ? 'DEMO' : 'LIVE';
        this.setBars(key, {
          data: { symbol: json.symbol || symbol, market, currency: json.currency || '$', bars, source: json.source || 'none' },
          loading: false,
          error: null,
          source,
          updatedAt: Date.now(),
        });
      } catch (err) {
        // Keep any previous data; surface the error on the entry.
        const prev = this.bars.get(key);
        this.setBars(key, {
          data: prev?.entry.data ?? null,
          loading: false,
          error: err instanceof Error ? err.message : 'Failed to load chart data',
          source: prev?.entry.data ? prev.entry.source : 'UNAVAILABLE',
          updatedAt: prev?.entry.updatedAt ?? null,
        });
      } finally {
        const s = this.bars.get(key);
        if (s) { s.inFlight = null; s.lastFetch = Date.now(); }
      }
    })();
    state.inFlight = run;
  }

  private setBars(key: string, entry: BarsEntry): void {
    const state = this.bars.get(key);
    if (!state) return;
    state.entry = entry;
    this.emitBars(key);
  }

  private emitBars(key: string): void {
    const state = this.bars.get(key);
    if (!state) return;
    for (const l of state.listeners) l(state.entry);
  }

  // ── Quotes (live last price) ───────────────────────────────────────────────
  private quoteKey(symbol: string, market: string): string {
    return `${symbol.toUpperCase()}|${market.toUpperCase()}`;
  }

  subscribeQuote(symbol: string, market: string, listener: QuoteListener, intervalMs = QUOTE_POLL_MS): () => void {
    const key = this.quoteKey(symbol, market);
    let state = this.quotes.get(key);
    if (!state) {
      state = {
        entry: { price: null, changePercent: 0, currency: '$', found: false, updatedAt: null, at: null },
        listeners: new Set(),
        timer: null,
        inFlight: false,
      };
      this.quotes.set(key, state);
    }
    state.listeners.add(listener);
    if (state.entry.at) listener(state.entry);
    this.fetchQuote(key, symbol, market);
    if (!state.timer && intervalMs > 0) {
      state.timer = setInterval(() => this.fetchQuote(key, symbol, market), intervalMs);
    }
    return () => this.unsubscribeQuote(key, listener);
  }

  private unsubscribeQuote(key: string, listener: QuoteListener): void {
    const state = this.quotes.get(key);
    if (!state) return;
    state.listeners.delete(listener);
    if (state.listeners.size === 0) {
      // Stop the poll but KEEP the entry: a StrictMode remount (or a panel that
      // quickly re-subscribes) then reuses the last quote instead of re-fetching,
      // and an in-flight request still lands in a live state object.
      if (state.timer) { clearInterval(state.timer); state.timer = null; }
      if (!state.inFlight) this.quotes.delete(key);
    }
  }

  private async fetchQuote(key: string, symbol: string, market: string): Promise<void> {
    const state = this.quotes.get(key);
    if (!state || state.inFlight) return;
    state.inFlight = true;
    try {
      const params = new URLSearchParams({ symbols: symbol, market });
      const res = await fetch(`/api/quote?${params.toString()}`);
      if (!res.ok) return;
      const json = (await res.json()) as {
        quotes?: Array<{ price?: number; changePercent?: number; currency?: string; updatedAt?: string; found?: boolean }>;
      };
      const q = json.quotes?.[0];
      const s = this.quotes.get(key);
      if (!s) return;
      if (q?.found && typeof q.price === 'number' && q.price > 0) {
        s.entry = {
          price: q.price,
          changePercent: q.changePercent ?? 0,
          currency: q.currency ?? '$',
          found: true,
          updatedAt: q.updatedAt ?? null,
          at: Date.now(),
        };
      } else {
        s.entry = { ...s.entry, found: false, at: Date.now() };
      }
      for (const l of s.listeners) l(s.entry);
    } catch {
      // Network hiccup — keep the last known quote.
    } finally {
      state.inFlight = false;
    }
  }

  // ── Batch quotes (watchlist / strip panels) ────────────────────────────────
  // One request for a whole symbol set, keyed by the sorted symbol list so two
  // watchlist panels with the same symbols share a single poll.

  private batches = new Map<string, BatchState>();

  subscribeBatch(symbols: string[], listener: BatchListener, intervalMs = QUOTE_POLL_MS): () => void {
    const uniq = [...new Set(symbols.map(s => s.toUpperCase()).filter(Boolean))].sort();
    if (uniq.length === 0) { listener(EMPTY_BATCH); return () => {}; }
    const key = uniq.join(',');
    let state = this.batches.get(key);
    if (!state) {
      state = { entry: EMPTY_BATCH, listeners: new Set(), timer: null, inFlight: false, symbols: uniq };
      this.batches.set(key, state);
    }
    state.listeners.add(listener);
    if (state.entry.at) listener(state.entry);
    this.fetchBatch(key);
    if (!state.timer && intervalMs > 0) {
      state.timer = setInterval(() => this.fetchBatch(key), intervalMs);
    }
    return () => {
      const s = this.batches.get(key);
      if (!s) return;
      s.listeners.delete(listener);
      if (s.listeners.size === 0) {
        if (s.timer) { clearInterval(s.timer); s.timer = null; }
        this.batches.delete(key);
      }
    };
  }

  private async fetchBatch(key: string): Promise<void> {
    const state = this.batches.get(key);
    if (!state || state.inFlight) return;
    state.inFlight = true;
    try {
      const res = await fetch(`/api/quote?symbols=${encodeURIComponent(state.symbols.join(','))}`);
      if (!res.ok) return;
      const json = (await res.json()) as { quotes?: QuoteRow[] };
      const s = this.batches.get(key);
      if (!s) return;
      s.entry = { rows: json.quotes ?? [], at: Date.now() };
      for (const l of s.listeners) l(s.entry);
    } catch {
      // keep previous
    } finally {
      state.inFlight = false;
    }
  }

  /** Number of distinct bars identities currently cached (diagnostics). */
  stats(): { bars: number; quotes: number; batches: number } {
    return { bars: this.bars.size, quotes: this.quotes.size, batches: this.batches.size };
  }
}

/** Singleton — shared by every chart panel in the app. */
export const dataManager = new DataSubscriptionManager();

// ── React hooks ──────────────────────────────────────────────────────────────

const EMPTY_BARS: BarsEntry = { data: null, loading: true, error: null, source: 'UNAVAILABLE', updatedAt: null };

/** Shared OHLCV subscription. N panels on the same identity share one fetch. */
export function useChartBars(symbol: string, market: string, timeframe: Timeframe): BarsEntry & { refresh: () => void } {
  const [entry, setEntry] = useState<BarsEntry>(() => EMPTY_BARS);
  const sym = symbol.toUpperCase();
  useEffect(() => {
    const unsub = dataManager.subscribeBars(sym, market, timeframe, setEntry);
    return unsub;
  }, [sym, market, timeframe]);
  return { ...entry, refresh: () => dataManager.refreshBars(sym, market, timeframe) };
}

const EMPTY_QUOTE: QuoteEntry = { price: null, changePercent: 0, currency: '$', found: false, updatedAt: null, at: null };

/** Shared live-quote subscription (dedup per symbol|market). */
export function useLiveQuote(symbol: string, market: string, intervalMs?: number): QuoteEntry {
  const [entry, setEntry] = useState<QuoteEntry>(EMPTY_QUOTE);
  const sym = symbol.toUpperCase();
  useEffect(() => {
    const unsub = dataManager.subscribeQuote(sym, market, setEntry, intervalMs);
    return unsub;
  }, [sym, market, intervalMs]);
  return entry;
}

/**
 * Shared BATCH quote subscription for a symbol set (watchlist panels). Keyed by
 * the sorted symbol list, so duplicate watchlists share one poll.
 */
export function useQuoteBatch(symbols: string[], intervalMs?: number): BatchEntry {
  const [entry, setEntry] = useState<BatchEntry>(EMPTY_BATCH);
  const key = [...new Set(symbols.map(s => s.toUpperCase()))].sort().join(',');
  useEffect(() => {
    if (!key) { setEntry(EMPTY_BATCH); return; }
    const list = key.split(',');
    const unsub = dataManager.subscribeBatch(list, setEntry, intervalMs);
    return unsub;
  }, [key, intervalMs]);
  return entry;
}

/** Stable identity used by chart-panel keys / linked-chart coordination. */
export function chartIdentity(symbol: string, market: string, timeframe: Timeframe): string {
  return `${symbol.toUpperCase()}|${market.toUpperCase()}|${timeframe}`;
}
