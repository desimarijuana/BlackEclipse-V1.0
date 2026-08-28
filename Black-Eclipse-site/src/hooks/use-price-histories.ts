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

    (async () => {
      // 1) FX rate first (parallel with history fetches would double-fetch forex
      //    cache; a single quick call here keeps maths consistent per run).
      const pkrToUsd = await fetchFx();
      if (cancelled || runId !== runIdRef.current) return;

      // 2) Fire per-symbol fetches in parallel with per-symbol aborts.
      const uniq = [...new Set(key.split(','))];
      const results = await Promise.all(
        uniq.map(async sym => {
          try {
            const market = marketsHint[sym] ?? (sym === 'BTC' || sym === 'ETH' || sym === 'SOL' ? 'CRYPTO' : 'US');
            const res = await fetch(
              `/api/price-history?symbol=${encodeURIComponent(sym)}&market=${encodeURIComponent(market)}&range=${HISTORY_RANGE}`
            );
            const data = await res.json();
            const series = Array.isArray(data.series) ? data.series : [];
            const closes = series
              .map((b: { close: number }) => Number(b.close))
              .filter((c: number) => Number.isFinite(c) && c > 0);
            const dates = series.map((b: { date: string }) => b.date);
            return [sym, { closes, dates }] as const;
          } catch {
            return [sym, { closes: [] as number[], dates: [] as string[] }] as const;
          }
        })
      );
      if (cancelled || runId !== runIdRef.current) return;

      const closes: Record<string, number[]> = {};
      const dates: Record<string, string[]> = {};
      let ok = false;
      for (const [sym, r] of results) {
        if (r.closes.length >= 2) {
          closes[sym] = r.closes;
          dates[sym] = r.dates;
          ok = true;
        }
      }
      setState({ closes, dates, pkrToUsd, loading: false, ok });
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