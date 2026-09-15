'use client';

// ── Market views — country tabs for the Command Center ───────────────────────
// The user's favourite markets ("tabs") plus custom-added countries/markets.
// Each view drives which market the market-aware widgets show AND gets its own
// persisted workspace layout, so every country can arrange its own widgets.
//
// Persisted to localStorage; reactive across components/tabs. The active view
// is tracked here too so widgets can read it via useActiveMarket().

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { HEATMAP_MARKETS } from '@/lib/heatmap';
import { registerTopic, jsonTopic, useTopic } from '@/lib/workspace/data-hub';

export interface MarketView {
  /** Canonical market id (US, PK, FOREX, COMMODITIES, …). */
  id: string;
  /** Display name shown on the tab (e.g. "PSX", "United States"). */
  name: string;
}

const STORAGE_KEY = 'be_market_views_v2';
const ACTIVE_KEY = 'be_market_active_v1';
const EVENT = 'be:market-views-changed';

/** Top markets every user starts with — US + the global venues + Pakistan. */
export const DEFAULT_MARKET_VIEWS: MarketView[] = [
  { id: 'US', name: 'US' },
  { id: 'CRYPTO', name: 'Crypto' },
  { id: 'FOREX', name: 'Forex' },
  { id: 'COMMODITIES', name: 'Commodities' },
  { id: 'PK', name: 'PK' },
];

/** Friendlier short labels for the non-country markets (everything else = id). */
const GLOBAL_VENUE_LABEL: Record<string, string> = {
  CRYPTO: 'Crypto',
  FOREX: 'Forex',
  COMMODITIES: 'Commodities',
};

/**
 * Short display label for a market id — the code itself for countries (US, PK,
 * IN, CN, …), a friendly word for the global venues (Crypto / Forex /
 * Commodities). Full country names live in MARKET_FULL_NAME for search only.
 */
export function marketViewName(id: string): string {
  const code = id.trim().toUpperCase();
  return GLOBAL_VENUE_LABEL[code] || code;
}

/** A market that can be added as a tab: short code + full name (for search). */
export interface MarketOption {
  id: string;
  /** Short label shown on the tab (US, PK, Crypto…). */
  name: string;
  /** Full country / market name, used for search + secondary display. */
  full: string;
}

/** Everything a user can add as a market tab (countries + global venues). */
export const MARKET_OPTIONS: MarketOption[] = [
  { id: 'US', name: 'US', full: 'United States' },
  { id: 'CRYPTO', name: 'Crypto', full: 'Global Crypto' },
  { id: 'FOREX', name: 'Forex', full: 'Forex' },
  { id: 'COMMODITIES', name: 'Commodities', full: 'Commodities' },
  ...HEATMAP_MARKETS
    .filter(m => m.id !== 'US' && m.id !== 'CRYPTO' && m.id !== 'FOREX' && m.id !== 'COMMODITIES')
    .map(m => ({ id: m.id, name: m.id, full: m.country })),
];

// Old default labels (full country names / "PSX") that should be migrated to
// the short code. A name the user customised is left untouched.
const LEGACY_NAMES = new Set(
  [
    ...HEATMAP_MARKETS.map(m => m.country),
    'United States', 'Global Crypto', 'PSX', 'Pakistan',
  ].map(n => n.toLowerCase()),
);

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
        const stored = typeof rawName === 'string' && rawName.trim() ? rawName.trim() : '';
        // Migrate a legacy full-name default to the short code; keep a rename.
        const name = !stored || LEGACY_NAMES.has(stored.toLowerCase())
          ? marketViewName(id)
          : stored;
        return { id, name };
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
  setActiveId: (id: string) => void;
  add: (id: string, name?: string) => void;
  remove: (id: string) => void;
  /** Rename a tab (display label only — the market id is unchanged). */
  rename: (id: string, name: string) => void;
}

const FALLBACK: MarketViewsContextValue = {
  views: DEFAULT_MARKET_VIEWS,
  activeId: 'US',
  setActiveId: () => {},
  add: () => {},
  remove: () => {},
  rename: () => {},
};

const MarketViewsContext = createContext<MarketViewsContextValue | null>(null);

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

  // Tabs show SHORT codes by default (US, PK, IN, CN…); `name` is only used
  // when a caller explicitly wants a custom label (e.g. a user rename).
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

  const rename = useCallback((id: string, name: string) => {
    const code = id.trim().toUpperCase();
    const label = name.trim();
    if (!code || !label) return;
    setViews(prev => {
      const next = prev.map(v => (v.id === code ? { ...v, name: label } : v));
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
    setActiveId,
    add,
    remove,
    rename,
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

/** Sentinel stored in a widget's config to mean "follow the active market tab". */
export const MARKET_FOLLOW = '';

/**
 * The market a widget should render: its per-instance `config.market` when set
 * (empty/undefined = follow the active tab), else the active market tab.
 */
export function useWidgetMarket(placement?: { config?: Record<string, unknown> }): string {
  const active = useActiveMarket();
  const override = placement?.config?.market;
  return typeof override === 'string' && override ? override.toUpperCase() : active;
}

/**
 * Config field every market-aware widget exposes so the user can pin a widget
 * to a specific market (or leave it following the active tab). Rendered by the
 * shared WidgetConfigPanel.
 */
export const MARKET_CONFIG_FIELD = {
  key: 'market',
  label: 'Market',
  type: 'select' as const,
  options: [
    { value: MARKET_FOLLOW, label: 'Follow active tab' },
    ...MARKET_OPTIONS.map(o => ({ value: o.id, label: o.name })),
  ],
  default: MARKET_FOLLOW,
};

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

type PlacementLike = { config?: Record<string, unknown> } | undefined;

/** Live index quotes for a widget's market (config-pinned or the active tab). */
export function useMarketIndices(placement?: PlacementLike): { market: string; rows: MarketIndexRow[] } {
  const market = useWidgetMarket(placement);
  const id = useMemo(() => ensureMarketIndicesTopic(market), [market]);
  const t = useTopic<{ indices: MarketIndexRow[] }>(id);
  return { market, rows: t.data?.indices ?? [] };
}

/** Sector performance for a widget's market (rides the indices payload). */
export function useMarketSectors(placement?: PlacementLike): { market: string; sectors: { name: string; change: number }[] } {
  const market = useWidgetMarket(placement);
  const id = useMemo(() => ensureMarketIndicesTopic(market), [market]);
  const t = useTopic<{ sectors?: { name: string; change: number }[] }>(id);
  return { market, sectors: t.data?.sectors ?? [] };
}

/** The global-overview group (top constituents) for a widget's market. */
export function useMarketGroup(placement?: PlacementLike): { market: string; group: MarketGroup | null; stocks: MarketStockRow[] } {
  const market = useWidgetMarket(placement);
  const overview = useTopic<{ groups: MarketGroup[] }>('market:overview');
  const group = useMemo(
    () => overview.data?.groups?.find(g => g.id === market) ?? null,
    [overview.data, market],
  );
  return { market, group, stocks: group?.stocks ?? [] };
}

/** Global venues whose lead instrument doesn't come from the overview feed. */
const GLOBAL_LEAD_SYMBOL: Record<string, string> = {
  FOREX: 'EURUSD=X',
  COMMODITIES: 'GC=F',
};

/**
 * The default chart symbol for a market — its most prominent instrument (the
 * top constituent by market cap, or the headline index). Lets a market tab's
 * chart open on that market's own asset instead of always AAPL.
 */
export function useMarketLeadSymbol(placement?: PlacementLike): { market: string; symbol: string } {
  const market = useWidgetMarket(placement);
  const { group } = useMarketGroup(placement);
  const indices = useTopic<{ indices?: MarketIndexRow[] }>(
    useMemo(() => ensureMarketIndicesTopic(market), [market]),
  );
  const symbol = useMemo(() => {
    if (group?.stocks?.length) return group.stocks[0].symbol;
    if (GLOBAL_LEAD_SYMBOL[market]) return GLOBAL_LEAD_SYMBOL[market];
    if (market === 'CRYPTO') return 'BTC';
    const idx = indices.data?.indices ?? [];
    if (idx.length) return idx[0].symbol;
    return 'AAPL';
  }, [group, market, indices.data]);
  return { market, symbol };
}
