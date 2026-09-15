'use client';

// ── Guest watchlist store ────────────────────────────────────────────────────
// The user's own watchlist, persisted to localStorage so it is shared across the
// Command Center widget and the News page's "My Stocks" filter. Symbols can be
// flagged as favourites (shown first, with an optional favourites-only view).

import { useCallback, useEffect, useState } from 'react';

export interface WatchlistItem {
  symbol: string;
  favorite?: boolean;
}

const STORAGE_KEY = 'watchlist_guest';
const EVENT = 'be:watchlist-changed';

const DEFAULT_ITEMS: WatchlistItem[] = ['AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMZN'].map(symbol => ({ symbol }));

function safeParse(raw: string | null): WatchlistItem[] | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return null;
    const items = parsed
      .map((v): WatchlistItem | null => {
        if (typeof v === 'string') return { symbol: v.toUpperCase() };
        if (v && typeof v === 'object' && typeof (v as { symbol?: unknown }).symbol === 'string') {
          return { symbol: (v as { symbol: string }).symbol.toUpperCase(), favorite: Boolean((v as { favorite?: unknown }).favorite) };
        }
        return null;
      })
      .filter((v): v is WatchlistItem => v !== null && v.symbol.length > 0);
    return items.slice(0, 50);
  } catch {
    return null;
  }
}

function read(): WatchlistItem[] {
  if (typeof window === 'undefined') return DEFAULT_ITEMS;
  const items = safeParse(window.localStorage.getItem(STORAGE_KEY));
  if (items) return items;
  // First run — persist the sensible defaults so the News "My Stocks" filter
  // and any other watchlist consumer share the same starting list.
  try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(DEFAULT_ITEMS)); } catch { /* ignore */ }
  return DEFAULT_ITEMS;
}

function write(items: WatchlistItem[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
    window.dispatchEvent(new CustomEvent(EVENT));
  } catch { /* ignore */ }
}

// ── Imperative API (for non-React callers: command palette, event handlers) ──
// These write the same storage key and fire the same event, so every
// `useWatchlist()` subscriber re-syncs automatically.

/** Add a symbol to the guest watchlist. Returns the symbol, or null if rejected. */
export function addToWatchlist(symbol: string): string | null {
  if (typeof window === 'undefined') return null;
  const sym = symbol.trim().toUpperCase();
  if (!sym) return null;
  const items = read();
  if (items.some(i => i.symbol === sym) || items.length >= 50) return null;
  write([...items, { symbol: sym }]);
  return sym;
}

/** Remove a symbol from the guest watchlist. */
export function removeFromWatchlist(symbol: string): void {
  if (typeof window === 'undefined') return;
  const sym = symbol.trim().toUpperCase();
  write(read().filter(i => i.symbol !== sym));
}

/** True when the symbol is already on the guest watchlist. */
export function isInWatchlist(symbol: string): boolean {
  const sym = symbol.trim().toUpperCase();
  return read().some(i => i.symbol === sym);
}

/** Subscribe to the guest watchlist. Reactive across components/tabs. */
export function useWatchlist() {
  const [items, setItems] = useState<WatchlistItem[]>(DEFAULT_ITEMS);

  useEffect(() => {
    const sync = () => setItems(read());
    sync();
    window.addEventListener('storage', sync);
    window.addEventListener(EVENT, sync);
    return () => {
      window.removeEventListener('storage', sync);
      window.removeEventListener(EVENT, sync);
    };
  }, []);

  const add = useCallback((symbol: string) => {
    const sym = symbol.trim().toUpperCase();
    if (!sym) return;
    setItems(prev => {
      if (prev.some(i => i.symbol === sym) || prev.length >= 50) return prev;
      const next = [...prev, { symbol: sym }];
      write(next);
      return next;
    });
  }, []);

  const remove = useCallback((symbol: string) => {
    setItems(prev => {
      const next = prev.filter(i => i.symbol !== symbol);
      write(next);
      return next;
    });
  }, []);

  const toggleFavorite = useCallback((symbol: string) => {
    setItems(prev => {
      const next = prev.map(i => (i.symbol === symbol ? { ...i, favorite: !i.favorite } : i));
      write(next);
      return next;
    });
  }, []);

  return { items, add, remove, toggleFavorite };
}
