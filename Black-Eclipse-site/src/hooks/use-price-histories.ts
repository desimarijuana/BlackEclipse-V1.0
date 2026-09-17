'use client';

import { useEffect, useState, useCallback, useRef } from 'react';

// ── Real price history per holding ──────────────────────────────────────────
// Fetches REAL daily OHLCV series for each tracked symbol from JDDS's
// /api/price-history endpoint (Yahoo chart API with PK .KA fallback), then:
//   · converts every close into the base currency (USD) using a single
//     fetched live FX rate (USDPKR=X) so mixed-currency portfolios chart
//     correctly;
//   · builds per-symbol sparkline data (last 30 closes);
//   · builds the portfolio NAV series by *aligned date* — each holding
//     contributes (closes_i / closes_0) × its CURRENT USD value, which is
//     the standard indexed-rebase aggregation. Every portfolio curve ends
//     exactly at today's NAV because today's term is value_i × 1.
//
// Real data only: symbols with no fetchable series are skipped (no seeded
// noise, no fabricated walk). If nothing is fetchable, series are empty and
// the UI shows an honest empty state.

export interface HistBar {
  date: string;
  close: number;
}

export interface HistoryState {
  /** symbol → ascending close series (native currency). */
  closes: Record<string, number[]>;
  /** symbol → ISO dates aligned with closes. */
  dates: Record<string, string[]>;
  /** Live FX: how many USD one PKR buys (≈1/278). USD assets = 1. */
  pkrToUsd: number;
  loading: boolean;
  /** True once at least one real series landed. */
  ok: boolean;
  /** True when the current paint came from the session cache. */
  cached?: boolean;
}

const DEFAULT_STATE: HistoryState = {
  closes: {},
  dates: {},
  pkrToUsd: 1 / 278,
  loading: true,
  ok: false,
};

// Number of dates (trading days) to request for portfolio-level charts.
const HISTORY_RANGE = '3mo';

// ── sessionStorage cache ──────────────────────────────────────────────────────
// Yahoo history fetches are slow (2–45s observed). Cache each symbol's series
// per browser session with a TTL so tab switches and re-mounts render the
// chart instantly and only refresh in the background after expiry.
const CACHE_KEY = 'eclipse_price_history_cache';
const CACHE_TTL_MS = 10 * 60 * 1000;

interface CacheEntry { closes: number[]; dates: string[]; t: number }

function readCache(): Record<string, CacheEntry> {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, CacheEntry>;
    // Purge expired entries lazily.
    const now = Date.now();
    for (const sym of Object.keys(parsed)) {
      if (!parsed[sym] || now - parsed[sym].t > CACHE_TTL_MS) delete parsed[sym];
    }
    return parsed;
  } catch {
    return {};
  }
}

function writeCache(sym: string, entry: { closes: number[]; dates: string[] }) {
  try {
    const cache = readCache();
    cache[sym] = { ...entry, t: Date.now() };
    sessionStorage.setItem(CACHE_KEY, JSON.stringify(cache));
  } catch { /* quota — cache is best-effort */ }
}

export function usePriceHistories(symbols: string[], marketsHint: Record<string, string> = {}): HistoryState {
  const key = symbols.join(',');

  // Stable state, updated by an async fetch loop below.
  const [state, setState] = useState<HistoryState>(DEFAULT_STATE);
  const runIdRef = useRef(0);

  const fetchFx = useCallback(async (): Promise<number> => {
    try {
      const res = await fetch('/api/forex', { signal: AbortSignal.timeout(9000) });
      const data = await res.json();
      const usdPkr = (data.pairs as Array<{ base: string; quote: string; price: number; found: boolean }> | undefined)
        ?.find(p => p.base === 'USD' && p.quote === 'PKR' && p.found);
      if (usdPkr && usdPkr.price > 0) return 1 / usdPkr.price;
    } catch { /* fall through */ }
    return 1 / 278;
  }, []);

  useEffect(() => {
    if (!key) {
      runIdRef.current += 1;
      setState({ closes: {}, dates: {}, pkrToUsd: 1 / 278, loading: false, ok: false });
      return;
    }
    const runId = ++runIdRef.current;
    let cancelled = false;

    const cache = readCache();
    const uniq = [...new Set(key.split(','))];
    const fresh = new Set(uniq.filter(sym => cache[sym] && cache[sym].closes.length >= 2));

    // Instant paint from cache: a full set renders immediately and only
    // background-refreshes; a partial set paints cached symbols now while the
    // missing ones load (avoids the "fetching…" blank on revisits).
    if (fresh.size > 0) {
      const closes: Record<string, number[]> = {};
      const dates: Record<string, string[]> = {};
      for (const sym of fresh) {
        closes[sym] = cache[sym].closes;
        dates[sym] = cache[sym].dates;
      }
      const allCached = fresh.size === uniq.length;
      setState(prev => ({
        closes: { ...closes, ...(allCached ? {} : {}) },
        dates: { ...dates },
        pkrToUsd: prev.pkrToUsd,
        loading: !allCached,
        ok: true,
        cached: true,
      }));
    }

    (async () => {
      // 1) FX rate first (parallel with history fetches would double-fetch forex
      //    cache; a single quick call here keeps maths consistent per run).
      const pkrToUsd = await fetchFx();
      if (cancelled || runId !== runIdRef.current) return;

      // 2) Fetch per-symbol in parallel — only symbols NOT freshly cached.
      const toFetch = uniq.filter(sym => !fresh.has(sym));
      const results = await Promise.all(
        toFetch.map(async sym => {
          try {
            const market = marketsHint[sym] ?? 'US';
            const res = await fetch(
              `/api/price-history?symbol=${encodeURIComponent(sym)}&market=${encodeURIComponent(market)}&range=${HISTORY_RANGE}`
            );
            const data = await res.json();
            const series = Array.isArray(data.series) ? data.series : [];
            // Filter date AND close TOGETHER. Filtering closes alone (as this
            // used to) desynchronizes the two arrays the moment a bar has a
            // non-finite or ≤0 close: every later date then labels the wrong
            // close, so any date-aligned maths (correlation, covariance) would
            // compare mismatched days. Pair them or drop the pair.
            const closes: number[] = [];
            const dates: string[] = [];
            for (const b of series as Array<{ close?: unknown; date?: unknown }>) {
              const c = Number(b?.close);
              const d = typeof b?.date === 'string' ? b.date : '';
              if (!d || !Number.isFinite(c) || c <= 0) continue;
              closes.push(c);
              dates.push(d);
            }
            const cleaned = { closes, dates };
            if (closes.length >= 2) writeCache(sym, cleaned);
            return [sym, cleaned] as const;
          } catch {
            // Network failure → fall back to a stale cache entry if present.
            if (cache[sym]) return [sym, { closes: cache[sym].closes, dates: cache[sym].dates }] as const;
            return [sym, { closes: [] as number[], dates: [] as string[] }] as const;
          }
        })
      );
      if (cancelled || runId !== runIdRef.current) return;

      const closes: Record<string, number[]> = {};
      const dates: Record<string, string[]> = {};
      let ok = false;
      // Seed with cached symbols first, then overwrite/extend with fetched.
      for (const sym of fresh) {
        closes[sym] = cache[sym].closes;
        dates[sym] = cache[sym].dates;
        ok = true;
      }
      for (const [sym, r] of results) {
        if (r.closes.length >= 2) {
          closes[sym] = r.closes;
          dates[sym] = r.dates;
          ok = true;
        }
      }
      setState({ closes, dates, pkrToUsd, loading: false, ok, cached: false });
    })();

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return state;
}

// ── Derived helpers (pure) ─────────────────────────────────────────────────

/** Normalize a close series so it starts at 1 (or any base) — indexed performance. */
export function toIndexed(closes: number[]): number[] {
  if (closes.length === 0) return [];
  const first = closes[0];
  return closes.map(c => c / first);
}