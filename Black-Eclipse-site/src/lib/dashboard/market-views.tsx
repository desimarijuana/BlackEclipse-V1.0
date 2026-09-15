'use client';

// ── Market views — country tabs for the Command Center ───────────────────────
// The user's favourite markets ("tabs") plus custom-added countries/markets.
// Each view drives which market the market-aware widgets show AND gets its own
// persisted workspace layout, so every country can arrange its own widgets.
//
// Persisted to localStorage; reactive across components/tabs. The active view
// is tracked here too so widgets can read it via useActiveMarket().

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { MARKET_FULL_NAME } from '@/lib/markets';
import { HEATMAP_MARKETS } from '@/lib/heatmap';
import { registerTopic, jsonTopic, useTopic } from '@/lib/workspace/data-hub';

export interface MarketView {
  /** Canonical market id (US, PK, FOREX, COMMODITIES, …). */
  id: string;
  /** Display name shown on the tab (e.g. "PSX", "United States"). */
  name: string;
  /** Pinned to the front of the bar. */
  favorite?: boolean;
}

const STORAGE_KEY = 'be_market_views_v1';
const ACTIVE_KEY = 'be_market_active_v1';
const EVENT = 'be:market-views-changed';

/** Top markets every user starts with — US + the two global venues + PSX. */
export const DEFAULT_MARKET_VIEWS: MarketView[] = [
  { id: 'US', name: 'US', favorite: true },
  { id: 'FOREX', name: 'Forex' },
  { id: 'COMMODITIES', name: 'Commodities' },
  { id: 'PK', name: 'PSX' },
];

/** Everything a user can add as a market tab (countries + global venues). */
export const MARKET_OPTIONS: { id: string; name: string }[] = [
  { id: 'US', name: 'United States' },
  { id: 'FOREX', name: 'Forex' },
  { id: 'COMMODITIES', name: 'Commodities' },
  { id: 'CRYPTO', name: 'Global Crypto' },
  ...HEATMAP_MARKETS
    .filter(m => m.id !== 'US' && m.id !== 'CRYPTO')
    .map(m => ({ id: m.id, name: m.country })),
];

/** Human-readable name for a market id (market map, then any override). */
export function marketViewName(id: string): string {
  return MARKET_FULL_NAME[id] || id;
}

function safeParse(raw: string | null): MarketView[] | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return null;
    const views = parsed
      .map((v): MarketView | null => {
        if (!v || typeof v !== 'object') return null;
        const id = typeof (v as { id?: unknown }).id === 'string' ? (v as { id: string }).id.trim().toUpperCase() : '';
        if (!id) return null;
        const rawName = (v as { name?: unknown }).name;
        const name = typeof rawName === 'string' && rawName.trim() ? rawName.trim() : id;
        return { id, name, favorite: Boolean((v as { favorite?: unknown }).favorite) };
      })
      .filter((v): v is MarketView => v !== null);
    return views.length ? views : null;
  } catch {
    return null;
  }
}

function readViews(): MarketView[] {
  if (typeof window === 'undefined') return DEFAULT_MARKET_VIEWS;
  const views = safeParse(window.localStorage.getItem(STORAGE_KEY));
  if (views) return views;
  try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(DEFAULT_MARKET_VIEWS)); } catch { /* ignore */ }
  return DEFAULT_MARKET_VIEWS;
}

function writeViews(views: MarketView[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(views));
    window.dispatchEvent(new CustomEvent(EVENT));
  } catch { /* ignore */ }
}

function readActiveId(): string {
  if (typeof window === 'undefined') return 'US';
  try { return (window.localStorage.getItem(ACTIVE_KEY) || 'US').toUpperCase(); } catch { return 'US'; }
}

export interface MarketViewsContextValue {
  views: MarketView[];
  activeId: string;
  /** Views with favourites pinned to the front (stable otherwise). */
  orderedViews: MarketView[];
  setActiveId: (id: string) => void;
  add: (id: string, name?: string) => void;
  remove: (id: string) => void;
  toggleFavorite: (id: string) => void;
}

const FALLBACK: MarketViewsContextValue = {
  views: DEFAULT_MARKET_VIEWS,
  activeId: 'US',
  orderedViews: DEFAULT_MARKET_VIEWS,
  setActiveId: () => {},
  add: () => {},
  remove: () => {},
  toggleFavorite: () => {},
};

const MarketViewsContext = createContext<MarketViewsContextValue | null>(null);

function orderFavoritesFirst(views: MarketView[]): MarketView[] {
  return [...views.filter(v => v.favorite), ...views.filter(v => !v.favorite)];
}

export function MarketViewsProvider({ children }: { children: React.ReactNode }) {
  const [views, setViews] = useState<MarketView[]>(DEFAULT_MARKET_VIEWS);
  const [activeId, setActiveIdState] = useState<string>('US');

  // Hydrate from storage after mount (SSR-safe).
  useEffect(() => {
    const stored = readViews();
    setViews(stored);
    const active = readActiveId();
    setActiveIdState(stored.some(v => v.id === active) ? active : (stored[0]?.id ?? 'US'));
  }, []);

  const setActiveId = useCallback((id: string) => {
    const next = id.trim().toUpperCase();
    if (!next) return;
    setActiveIdState(next);
    try { window.localStorage.setItem(ACTIVE_KEY, next); } catch { /* ignore */ }
  }, []);

  const add = useCallback((id: string, name?: string) => {
    const code = id.trim().toUpperCase();
    if (!code) return;
    setViews(prev => {
      if (prev.some(v => v.id === code)) return prev;
      const label = name?.trim() || marketViewName(code);
      const next = [...prev, { id: code, name: label }];
      writeViews(next);
      return next;
    });
    setActiveId(code);
  }, [setActiveId]);

  const remove = useCallback((id: string) => {
    const code = id.trim().toUpperCase();
    setViews(prev => {
      const next = prev.filter(v => v.id !== code);
      // Never leave the bar empty — keep at least one market.
      if (next.length === 0) return prev;
      writeViews(next);
      return next;
    });
  }, []);

  const toggleFavorite = useCallback((id: string) => {
    const code = id.trim().toUpperCase();
    setViews(prev => {
      const next = prev.map(v => (v.id === code ? { ...v, favorite: !v.favorite } : v));
      writeViews(next);
      return next;
    });
  }, []);

  // If the active view was removed, fall back to the first remaining one.
  useEffect(() => {
    if (views.length > 0 && !views.some(v => v.id === activeId)) {
      setActiveId(views[0].id);
    }
  }, [views, activeId, setActiveId]);

  const value: MarketViewsContextValue = {
    views,
    activeId,
    orderedViews: orderFavoritesFirst(views),
    setActiveId,
    add,
    remove,
    toggleFavorite,
  };

  return <MarketViewsContext.Provider value={value}>{children}</MarketViewsContext.Provider>;
}

/** Access the market-views store. Safe outside the provider (returns defaults). */
export function useMarketViews(): MarketViewsContextValue {
  return useContext(MarketViewsContext) ?? FALLBACK;
}

/** The market every market-aware widget should render. Defaults to US. */
export function useActiveMarket(): string {
  return useContext(MarketViewsContext)?.activeId ?? 'US';
}

/** DataHub topic id for a market's index payload. */
export function marketIndicesTopicId(market: string): string {
  return `market:indices:${market}`;
}

/**
 * Register (idempotently) and return the index topic id for a market. Every
 * market tab calls this so switching to a brand-new market kicks off its fetch
 * immediately instead of waiting for the topic to be registered elsewhere.
 */
export function ensureMarketIndicesTopic(market: string): string {
  const id = marketIndicesTopicId(market);
  registerTopic(jsonTopic(id, `/api/indices?market=${encodeURIComponent(market)}`, { ttl: 120_000, interval: 60_000 }));
  return id;
}

export interface MarketIndexRow {
  name: string;
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
  sparkline?: number[];
}

export interface MarketStockRow {
  symbol: string;
  name: string;
  price: number;
  changePct: number;
}

export interface MarketGroup {
  id: string;
  country: string;
  name?: string;
  exchange?: string;
  currency?: string;
  indexName?: string;
  stocks: MarketStockRow[];
}

/** Live index quotes for the active market (registered on demand). */
export function useMarketIndices(): { market: string; rows: MarketIndexRow[] } {
  const market = useActiveMarket();
  const id = useMemo(() => ensureMarketIndicesTopic(market), [market]);
  const t = useTopic<{ indices: MarketIndexRow[] }>(id);
  return { market, rows: t.data?.indices ?? [] };
}

/** Sector performance for the active market (rides the indices payload). */
export function useMarketSectors(): { market: string; sectors: { name: string; change: number }[] } {
  const market = useActiveMarket();
  const id = useMemo(() => ensureMarketIndicesTopic(market), [market]);
  const t = useTopic<{ sectors?: { name: string; change: number }[] }>(id);
  return { market, sectors: t.data?.sectors ?? [] };
}

/** The global-overview group (top constituents) for the active market. */
export function useMarketGroup(): { market: string; group: MarketGroup | null; stocks: MarketStockRow[] } {
  const market = useActiveMarket();
  const overview = useTopic<{ groups: MarketGroup[] }>('market:overview');
  const group = useMemo(
    () => overview.data?.groups?.find(g => g.id === market) ?? null,
    [overview.data, market],
  );
  return { market, group, stocks: group?.stocks ?? [] };
}
