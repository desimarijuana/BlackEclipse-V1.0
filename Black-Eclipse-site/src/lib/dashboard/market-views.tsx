'use client';

// ── Market views — named workspace layouts for the Command Center ────────────
// A "view" is a NAMED LAYOUT the user can call anything ("US", "PK", "My Tech
// Sheet", …). Each one keeps its own persisted workspace of widgets. A view
// also carries a default `market` used by widgets that "follow the tab" — the
// user can still pin any individual widget to any market from its header.
//
// Persisted to localStorage; reactive across components/tabs.

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { HEATMAP_MARKETS } from '@/lib/heatmap';
import { registerTopic, jsonTopic, useTopic } from '@/lib/workspace/data-hub';
import { newId } from '@/lib/workspace/types';

export interface MarketView {
  /** Stable layout id (opaque for user-created views; market code for legacy). */
  id: string;
  /** Free-form name the user chose (e.g. "US", "Crypto", "My Sheet"). */
  name: string;
  /** Default market for widgets that follow the tab (US, PK, CRYPTO, …). */
  market: string;
  /**
   * Starting dashboard template chosen when the layout was created (a persona
   * preset like 'trader' / 'investor'). Seeds the layout's initial widgets the
   * first time it opens; absent = inherit the dashboard's own template.
   */
  templateId?: string;
}

const STORAGE_KEY = 'be_market_views_v3';
const ACTIVE_KEY = 'be_market_active_v1';
const EVENT = 'be:market-views-changed';

/** Top layouts every user starts with — one per major market. */
export const DEFAULT_MARKET_VIEWS: MarketView[] = [
  { id: 'US', name: 'US', market: 'US' },
  { id: 'CRYPTO', name: 'Crypto', market: 'CRYPTO' },
  { id: 'FOREX', name: 'Forex', market: 'FOREX' },
  { id: 'COMMODITIES', name: 'Commodities', market: 'COMMODITIES' },
  { id: 'PK', name: 'PK', market: 'PK' },
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

/** A market the user can pick as a layout's default data source. */
export interface MarketOption {
  id: string;
  /** Short label (US, PK, Crypto…). */
  name: string;
  /** Full country / market name, used for search + secondary display. */
  full: string;
}

/**
 * Every market a layout can default to (countries + global venues). Used for
 * search in the layout editor and as the widget config market list — NOT as a
 * tab list (tabs are named layouts the user creates).
 */
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

/**
 * Repair one stored view. Accepts the current shape ({id,name,market}) and the
 * legacy shape ({id,name} where the id WAS the market code) — the market
 * defaults to the id in that case. Legacy labels are normalised to short codes.
 */
function normalizeView(v: unknown): MarketView | null {
  if (!v || typeof v !== 'object') return null;
  const r = v as Record<string, unknown>;
  const rawId = typeof r.id === 'string' ? r.id.trim() : '';
  if (!rawId) return null;
  // Legacy market-code ids are upper-cased; user layout ids are opaque.
  const knownMarket = MARKET_OPTIONS.some(o => o.id === rawId.toUpperCase());
  const id = knownMarket ? rawId.toUpperCase() : rawId;
  const rawMarket = typeof r.market === 'string' ? r.market.trim().toUpperCase() : '';
  const market = rawMarket || (knownMarket ? id : 'US');
  const rawName = typeof r.name === 'string' && r.name.trim() ? r.name.trim() : '';
  const name = !rawName || LEGACY_NAMES.has(rawName.toLowerCase()) ? marketViewName(market) : rawName;
  const templateId = typeof r.templateId === 'string' && r.templateId.trim() ? r.templateId.trim() : undefined;
  return { id, name, market, templateId };
}

function safeParse(raw: string | null): MarketView[] | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return null;
    const views = parsed.map(normalizeView).filter((v): v is MarketView => v !== null);
    return views.length ? views : null;
  } catch {
    return null;
  }
}

/** One-time migration from the v2 key (market-code tabs) to the v3 layout key. */
function migrateLegacyViews(): MarketView[] | null {
  if (typeof window === 'undefined') return null;
  try {
    const legacy = safeParse(window.localStorage.getItem('be_market_views_v2'));
    if (!legacy) return null;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(legacy));
    return legacy;
  } catch {
    return null;
  }
}

function readViews(): MarketView[] {
  if (typeof window === 'undefined') return DEFAULT_MARKET_VIEWS;
  const views = safeParse(window.localStorage.getItem(STORAGE_KEY)) ?? migrateLegacyViews();
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
  try { return window.localStorage.getItem(ACTIVE_KEY) || 'US'; } catch { return 'US'; }
}

export interface MarketViewsContextValue {
  views: MarketView[];
  activeId: string;
  /** The active view record (never null while views exist). */
  active: MarketView | null;
  setActiveId: (id: string) => void;
  /**
   * Create a new named layout with an optional default market and starting
   * template (persona preset). Returns the new layout's id.
   */
  create: (name: string, market?: string, templateId?: string) => string;
  remove: (id: string) => void;
  /** Rename a layout (display label only). */
  rename: (id: string, name: string) => void;
  /** Change which market the layout's "follow the tab" widgets show. */
  setMarket: (id: string, market: string) => void;
}

const FALLBACK: MarketViewsContextValue = {
  views: DEFAULT_MARKET_VIEWS,
  activeId: 'US',
  active: DEFAULT_MARKET_VIEWS[0],
  setActiveId: () => {},
  create: () => 'US',
  remove: () => {},
  rename: () => {},
  setMarket: () => {},
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
    if (!id) return;
    setActiveIdState(id);
    try { window.localStorage.setItem(ACTIVE_KEY, id); } catch { /* ignore */ }
  }, []);

  // A layout is just a NAMED workspace — the user types any name they like and
  // may start from a persona preset (templateId).
  const create = useCallback((name: string, market?: string, templateId?: string) => {
    const label = name.trim() || 'New layout';
    const mkt = (market?.trim() || 'US').toUpperCase();
    const view: MarketView = { id: newId('layout'), name: label, market: mkt, templateId };
    setViews(prev => {
      const next = [...prev, view];
      writeViews(next);
      return next;
    });
    setActiveId(view.id);
    return view.id;
  }, [setActiveId]);

  const remove = useCallback((id: string) => {
    setViews(prev => {
      const next = prev.filter(v => v.id !== id);
      // Never leave the bar empty — keep at least one layout.
      if (next.length === 0) return prev;
      writeViews(next);
      return next;
    });
  }, []);

  const rename = useCallback((id: string, name: string) => {
    const label = name.trim();
    if (!id || !label) return;
    setViews(prev => {
      const next = prev.map(v => (v.id === id ? { ...v, name: label } : v));
      writeViews(next);
      return next;
    });
  }, []);

  const setMarket = useCallback((id: string, market: string) => {
    const mkt = market.trim().toUpperCase();
    if (!id || !mkt) return;
    setViews(prev => {
      const next = prev.map(v => (v.id === id ? { ...v, market: mkt } : v));
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

  const active = useMemo(() => views.find(v => v.id === activeId) ?? views[0] ?? null, [views, activeId]);

  const value: MarketViewsContextValue = {
    views,
    activeId,
    active,
    setActiveId,
    create,
    remove,
    rename,
    setMarket,
  };

  return <MarketViewsContext.Provider value={value}>{children}</MarketViewsContext.Provider>;
}

/** Access the market-views store. Safe outside the provider (returns defaults). */
export function useMarketViews(): MarketViewsContextValue {
  return useContext(MarketViewsContext) ?? FALLBACK;
}

/** The market a "follow the tab" widget should render. Defaults to US. */
export function useActiveMarket(): string {
  const ctx = useContext(MarketViewsContext);
  return ctx?.active?.market ?? 'US';
}

/** The active layout record (name + default market). */
export function useActiveView(): MarketView | null {
  return useContext(MarketViewsContext)?.active ?? null;
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
