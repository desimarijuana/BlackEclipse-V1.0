'use client';

// ── Live quotes hook ─────────────────────────────────────────────────────────
// Pulls live prices for a fund's symbols from JDDS /api/quote (same source as
// the rest of the app). The API returns each instrument's REAL market id and
// currency, and this hook keeps them: it used to re-derive a USD/PKR binary from
// a hardcoded symbol allowlist, which silently mislabelled an Indian or UK
// holding as USD (and mis-valued it 1:1 against the dollar).

import { useEffect, useRef, useState } from 'react';
import { MARKET_CURRENCY } from '@/lib/markets';

export interface LiveQuote {
  symbol: string;
  name: string;
  price: number;
  changePercent: number;
  /** ISO display/quote currency code for the instrument (USD, PKR, INR, …). */
  currency: string;
  /** JDDS market id the quote resolved to (US, PK, IN, …). */
  marketId: string;
  found: boolean;
}

/**
 * Best-effort market hint for a symbol, used only to disambiguate the HISTORY
 * request. The authoritative market comes back on the quote itself; this list
 * just avoids a wasted first lookup for the well-known names.
 */
export const MARKET_HINT: Record<string, string> = {
  BTC: 'CRYPTO', ETH: 'CRYPTO', SOL: 'CRYPTO', BNB: 'CRYPTO', XRP: 'CRYPTO',
  DOGE: 'CRYPTO', ADA: 'CRYPTO',
  UBL: 'PK', MEBL: 'PK', SAZEW: 'PK', OGDC: 'PK', LUCK: 'PK', HBL: 'PK',
  PSO: 'PK', ENGRO: 'PK', SYS: 'PK',
};

export const marketHintFor = (symbol: string) => MARKET_HINT[symbol.toUpperCase()] ?? 'US';

export function useLiveQuotes(symbols: string[]): { quotes: Record<string, LiveQuote>; loading: boolean } {
  const key = [...new Set(symbols.map(s => s.toUpperCase()))].sort().join(',');
  const [quotes, setQuotes] = useState<Record<string, LiveQuote>>({});
  const [loading, setLoading] = useState(true);
  const runRef = useRef(0);

  useEffect(() => {
    const runId = ++runRef.current;
    if (!key) { setLoading(false); return; }
    setLoading(true);
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/quote?symbols=${encodeURIComponent(key.split(',').join(','))}`, {
          signal: AbortSignal.timeout(20000),
        });
        const data = await res.json();
        if (cancelled || runId !== runRef.current) return;
        const next: Record<string, LiveQuote> = {};
        for (const q of Array.isArray(data.quotes) ? data.quotes : []) {
          if (!q || !q.symbol) continue;
          // Trust the server's market id; fall back to the hint, then to the
          // currency table, so an unknown market still labels honestly.
          const marketId = String(q.marketId || marketHintFor(q.symbol));
          const currency = String(q.currency || MARKET_CURRENCY[marketId] || 'USD');
          next[q.symbol] = {
            symbol: q.symbol,
            name: q.name || q.symbol,
            price: Number(q.price) || 0,
            changePercent: Number(q.changePercent) || 0,
            currency,
            marketId,
            found: Boolean(q.found),
          };
        }
        setQuotes(next);
      } catch {
        if (!cancelled) setQuotes({});
      } finally {
        if (!cancelled && runId === runRef.current) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [key]);

  return { quotes, loading };
}
