'use client';

// ── Live quotes hook ─────────────────────────────────────────────────────────
// Pulls live prices for a fund's symbols from JDDS /api/quote (same source as
// the rest of the app). Currency is inferred from the market hint map.

import { useEffect, useRef, useState } from 'react';

export interface LiveQuote {
  symbol: string;
  name: string;
  price: number;
  changePercent: number;
  currency: 'USD' | 'PKR';
  found: boolean;
}

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
          const market = marketHintFor(q.symbol);
          next[q.symbol] = {
            symbol: q.symbol,
            name: q.name || q.symbol,
            price: Number(q.price) || 0,
            changePercent: Number(q.changePercent) || 0,
            currency: market === 'PK' ? 'PKR' : 'USD',
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
