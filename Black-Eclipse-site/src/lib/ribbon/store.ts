'use client';

// ── Header price ribbon — symbol store ───────────────────────────────────────
// The user's chosen ribbon instruments, persisted to localStorage and reactive
// across components/tabs (same storage-event pattern as the guest watchlist).
//
// Symbols are free-form: the ribbon resolves each one through the same server
// endpoints the rest of the app uses (`/api/quote` for indices/stocks/crypto,
// plus the commodity + forex feeds). Anything the upstream cannot price is
// omitted from the ribbon rather than shown with a placeholder.
//
// Imperative helpers (`addRibbonSymbol` / `removeRibbonSymbol`) exist so the
// command palette or an event handler can edit the ribbon outside React.

import { useCallback, useEffect, useState } from 'react';
import { isCatalogSymbol } from '@/lib/market-catalog';

const STORAGE_KEY = 'be_price_ribbon_v1';
const EVENT = 'be:price-ribbon-changed';

/** Cap keeps one poll bounded and the strip from being unusable. */
export const RIBBON_MAX_SYMBOLS = 24;

/**
 * Sensible starting ribbon: US benchmarks, crypto majors, key commodities, and
 * the headline FX pairs. Every one is resolvable by an existing endpoint today.
 */
export const DEFAULT_RIBBON_SYMBOLS: string[] = [
  '^GSPC', '^IXIC', '^DJI',
  'BTC', 'ETH',
  'GC=F', 'CL=F',
  'EURUSD=X', 'USDJPY=X', 'GBPUSD=X',
];

/** Display label for a symbol (drop Yahoo decorations: ^GSPC→GSPC, BTC-USD→BTC). */
export function ribbonLabel(symbol: string): string {
  return symbol.replace(/^\^/, '').replace(/-USD$/, '').replace(/=.$/, '');
}

function normalize(symbol: string): string {
  return symbol.trim().toUpperCase();
}

function safeParse(raw: string | null): string[] | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return null;
    const out: string[] = [];
    const seen = new Set<string>();
    for (const v of parsed) {
      if (typeof v !== 'string') continue;
      const s = normalize(v);
      if (!s || seen.has(s)) continue;
      seen.add(s);
      out.push(s);
      if (out.length >= RIBBON_MAX_SYMBOLS) break;
    }
    return out;
  } catch {
    return null;
  }
}

/** Read the configured symbols. An empty list is honoured (user cleared it). */
export function readRibbonSymbols(): string[] {
  if (typeof window === 'undefined') return DEFAULT_RIBBON_SYMBOLS;
  const parsed = safeParse(window.localStorage.getItem(STORAGE_KEY));
  if (parsed) return parsed;
  try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(DEFAULT_RIBBON_SYMBOLS)); } catch { /* ignore */ }
  return DEFAULT_RIBBON_SYMBOLS;
}

function write(symbols: string[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(symbols));
    window.dispatchEvent(new CustomEvent(EVENT));
  } catch { /* ignore */ }
}

/** Add a symbol to the ribbon. Returns the normalised symbol, or null if rejected. */
export function addRibbonSymbol(symbol: string): string | null {
  if (typeof window === 'undefined') return null;
  const sym = normalize(symbol);
  if (!sym) return null;
  const current = readRibbonSymbols();
  if (current.includes(sym) || current.length >= RIBBON_MAX_SYMBOLS) return null;
  write([...current, sym]);
  return sym;
}

/** Remove a symbol from the ribbon. */
export function removeRibbonSymbol(symbol: string): void {
  if (typeof window === 'undefined') return;
  const sym = normalize(symbol);
  write(readRibbonSymbols().filter((s) => s !== sym));
}

/** Restore the shipped default selection. */
export function resetRibbonSymbols(): void {
  if (typeof window === 'undefined') return;
  write([...DEFAULT_RIBBON_SYMBOLS]);
}

/** True when the configured list differs from the shipped default. */
export function isRibbonCustomized(symbols: string[]): boolean {
  if (symbols.length !== DEFAULT_RIBBON_SYMBOLS.length) return true;
  return symbols.some((s, i) => s !== DEFAULT_RIBBON_SYMBOLS[i]);
}

/** Subscribe to the ribbon symbol list. Reactive across components/tabs. */
export function useRibbonSymbols() {
  const [symbols, setSymbols] = useState<string[]>(DEFAULT_RIBBON_SYMBOLS);

  useEffect(() => {
    const sync = () => setSymbols(readRibbonSymbols());
    sync();
    window.addEventListener('storage', sync);
    window.addEventListener(EVENT, sync);
    return () => {
      window.removeEventListener('storage', sync);
      window.removeEventListener(EVENT, sync);
    };
  }, []);

  const add = useCallback((symbol: string) => {
    const sym = normalize(symbol);
    if (!sym) return;
    setSymbols(prev => {
      if (prev.includes(sym) || prev.length >= RIBBON_MAX_SYMBOLS) return prev;
      const next = [...prev, sym];
      write(next);
      return next;
    });
  }, []);

  const remove = useCallback((symbol: string) => {
    const sym = normalize(symbol);
    setSymbols(prev => {
      const next = prev.filter(s => s !== sym);
      write(next);
      return next;
    });
  }, []);

  const reset = useCallback(() => {
    write([...DEFAULT_RIBBON_SYMBOLS]);
    setSymbols([...DEFAULT_RIBBON_SYMBOLS]);
  }, []);

  return { symbols, add, remove, reset };
}

/** Split a symbol list into the catalog feeds vs. everything else. */
export function splitRibbonSymbols(symbols: string[]): {
  catalog: string[];
  quotes: string[];
} {
  const catalog: string[] = [];
  const quotes: string[] = [];
  for (const s of symbols) (isCatalogSymbol(s) ? catalog : quotes).push(s);
  return { catalog, quotes };
}
