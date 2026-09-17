// ── Investor Eye — client state ──────────────────────────────────────────────
// One Zustand store for all Investor Eye UI state (selection, layers, timeline,
// filters, search, portfolio overlay). Data fetching stays in DataHub topics;
// this store holds only view state and is persisted to localStorage — matching
// the repo's existing store convention.

'use client';

import { create } from 'zustand';
import { ALL_LAYER_IDS, type LayerId } from './layers';
import type { CompanyPoint, MapLayerType, NormalizedEvent } from './types';

export const TIME_RANGES = [
  { id: '1h', label: '1H', hours: 1 },
  { id: '6h', label: '6H', hours: 6 },
  { id: '24h', label: '24H', hours: 24 },
  { id: '7d', label: '7D', hours: 168 },
  { id: '30d', label: '30D', hours: 720 },
] as const;
export type TimeRangeId = (typeof TIME_RANGES)[number]['id'];

/** Phase 2 layers are registered but off by default (Phase 1 enables 2). */
export const DEFAULT_LAYERS: Record<LayerId, boolean> = {
  events: true,
  markets: true,
  conflict: false,
  shipping: false,
  trade: false,
  energy: false,
  commodities: false,
  economy: false,
  weather: false,
  fires: false,
  companies: false,
  risk: false,
  portfolio: false,
};

export interface SelectedMarket {
  marketId: string;
  iso2?: string;
  name: string;
  symbol: string;
  price: number;
  changePct: number;
  currency?: string;
}

/** Presentation of the world visualization. */
export type MapMode = '2d' | 'globe';

/**
 * Surface skin. `black` is the first-draft flat terminal look; `glow` is the
 * blue "lit planet" look (translucent blue continents, cyan coastlines, globe
 * bloom, starfield showing through). A pure view preference.
 */
export type MapSkin = 'black' | 'glow';

export const MAP_SKINS: Array<{ id: MapSkin; label: string; hint: string }> = [
  { id: 'black', label: 'BLACK', hint: 'Flat terminal surface — no glow' },
  { id: 'glow', label: 'GLOW', hint: 'Blue lit planet — coastlines, bloom, stars' },
];

interface InvestorEyeStore {
  selectedCountry: string | null;
  selectedEvent: NormalizedEvent | null;
  selectedMarket: SelectedMarket | null;
  selectedCompany: CompanyPoint | null;

  activeLayers: LayerId[];
  timeRange: TimeRangeId;
  /** Flat map or 3D globe (globe is lazy-loaded; falls back to `2d`). */
  mapMode: MapMode;
  /** Blue "lit planet" surface vs the plain black terminal surface. */
  mapSkin: MapSkin;
  /** Draw the animated starfield behind the map. Purely decorative. */
  showStars: boolean;
  /**
   * Immersive full-page mode: the world fills the viewport and only a minimal
   * control strip remains. View state, not a preference — deliberately NOT
   * persisted, so reopening the app never traps the user in full screen.
   */
  fullPage: boolean;

  /** Economic metric for the economy layer. */
  economicMetric: string;
  searchQuery: string;
  portfolioOverlay: boolean;

  /** Countries highlighted by a natural-language search (ISO2). */
  highlightedCountries: string[];
  highlightNote: string | null;

  /** Saved intelligence postures (persisted). */
  views: SavedView[];

  setSelectedCountry: (iso2: string | null) => void;
  setSelectedEvent: (event: NormalizedEvent | null) => void;
  setSelectedMarket: (market: SelectedMarket | null) => void;
  setSelectedCompany: (company: CompanyPoint | null) => void;
  clearSelection: () => void;

  toggleLayer: (id: LayerId) => void;
  setLayers: (ids: LayerId[]) => void;
  setTimeRange: (id: TimeRangeId) => void;
  setMapMode: (mode: MapMode) => void;
  setMapSkin: (skin: MapSkin) => void;
  setShowStars: (on: boolean) => void;
  setFullPage: (on: boolean) => void;
  setEconomicMetric: (id: string) => void;
  setSearchQuery: (q: string) => void;
  setPortfolioOverlay: (on: boolean) => void;
  applyHighlights: (countries: string[], note: string | null) => void;
  clearHighlights: () => void;

  /** Snapshot the current view state as a named preset. */
  saveView: (name: string) => SavedView | null;
  /** Apply a saved preset. */
  applyView: (id: string) => void;
  deleteView: (id: string) => void;
}

const STORAGE_KEY = 'be_investor_eye_v1';

/** Cap on saved postures — a palette, not a database. */
export const MAX_VIEWS = 20;

interface Persisted {
  activeLayers: LayerId[];
  timeRange: TimeRangeId;
  economicMetric: string;
  portfolioOverlay: boolean;
  mapMode: MapMode;
  mapSkin: MapSkin;
  showStars: boolean;
  /** Operator-saved intelligence postures (layer + window + metric presets). */
  views?: SavedView[];
}

/**
 * A saved "intelligence posture": the layer/window/metric combination a user
 * wants to return to. Only view state — never data — so restoring one is
 * instant and cannot resurrect stale observations.
 */
export interface SavedView {
  id: string;
  name: string;
  activeLayers: LayerId[];
  timeRange: TimeRangeId;
  mapMode: MapMode;
  mapSkin: MapSkin;
  showStars: boolean;
  economicMetric: string;
  portfolioOverlay: boolean;
  createdAt: string;
}

function loadPersisted(): Partial<Persisted> {
  if (typeof window === 'undefined') return {};
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Partial<Persisted>;
    // Reconcile with the canonical layer list: drop retired ids. A saved list
    // that survives reconciliation wins; otherwise fall back to the defaults
    // (so a brand-new layer is never silently lost, and an empty save is
    // indistinguishable from "never customized").
    const known = new Set<string>(ALL_LAYER_IDS);
    const saved = Array.isArray(parsed.activeLayers)
      ? parsed.activeLayers.filter((id): id is LayerId => known.has(id))
      : [];
    const allIds = Object.keys(DEFAULT_LAYERS) as LayerId[];
    return {
      activeLayers: saved.length > 0 ? allIds.filter((id) => saved.includes(id)) : undefined,
      timeRange: TIME_RANGES.some((r) => r.id === parsed.timeRange) ? (parsed.timeRange as TimeRangeId) : '24h',
      economicMetric: parsed.economicMetric ?? 'inflation',
      portfolioOverlay: parsed.portfolioOverlay ?? false,
      mapMode: parsed.mapMode === 'globe' ? 'globe' : '2d',
      mapSkin: parsed.mapSkin === 'black' ? 'black' : 'glow',
      showStars: typeof parsed.showStars === 'boolean' ? parsed.showStars : true,
      views: Array.isArray(parsed.views)
        ? parsed.views.filter((v): v is SavedView => Boolean(v && typeof v.name === 'string')).slice(0, MAX_VIEWS)
        : undefined,
    };
  } catch {
    return {};
  }
}

function persist(state: InvestorEyeStore) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        activeLayers: state.activeLayers,
        timeRange: state.timeRange,
        economicMetric: state.economicMetric,
        portfolioOverlay: state.portfolioOverlay,
        mapMode: state.mapMode,
        mapSkin: state.mapSkin,
        showStars: state.showStars,
        views: state.views,
      } satisfies Persisted),
    );
  } catch {
    /* quota / private mode — in-memory only */
  }
}

const defaultActive = (Object.keys(DEFAULT_LAYERS) as LayerId[]).filter((id) => DEFAULT_LAYERS[id]);

export const useInvestorEyeStore = create<InvestorEyeStore>((set, get) => {
  const persisted = loadPersisted();
  return {
    selectedCountry: null,
    selectedEvent: null,
    selectedMarket: null,
    selectedCompany: null,
    activeLayers: persisted.activeLayers ?? defaultActive,
    timeRange: persisted.timeRange ?? '24h',
    mapMode: persisted.mapMode ?? '2d',
    mapSkin: persisted.mapSkin ?? 'glow',
    showStars: persisted.showStars ?? true,
    fullPage: false,
    economicMetric: persisted.economicMetric ?? 'inflation',
    searchQuery: '',
    portfolioOverlay: persisted.portfolioOverlay ?? false,
    highlightedCountries: [],
    highlightNote: null,
    views: persisted.views ?? [],

    setSelectedCountry: (iso2) => set({ selectedCountry: iso2 }),
    setSelectedEvent: (event) => set({ selectedEvent: event }),
    setSelectedMarket: (market) =>
      set({ selectedMarket: market, selectedCountry: market?.iso2 ?? get().selectedCountry }),
    // A company carries its HQ country, so select both — the panel can pivot.
    setSelectedCompany: (company) =>
      set({ selectedCompany: company, selectedCountry: company?.iso2 ?? get().selectedCountry }),
    clearSelection: () =>
      set({ selectedCountry: null, selectedEvent: null, selectedMarket: null, selectedCompany: null }),

    toggleLayer: (id) => {
      const current = get().activeLayers;
      const next = current.includes(id) ? current.filter((l) => l !== id) : [...current, id];
      set({ activeLayers: next });
      persist(get());
    },
    setLayers: (ids) => {
      set({ activeLayers: ids });
      persist(get());
    },
    setTimeRange: (id) => {
      set({ timeRange: id });
      persist(get());
    },
    setMapMode: (mode) => {
      set({ mapMode: mode });
      persist(get());
    },
    setMapSkin: (skin) => {
      set({ mapSkin: skin });
      persist(get());
    },
    setShowStars: (on) => {
      set({ showStars: on });
      persist(get());
    },
    setFullPage: (on) => set({ fullPage: on }),
    setEconomicMetric: (id) => {
      set({ economicMetric: id });
      persist(get());
    },
    setSearchQuery: (q) => set({ searchQuery: q }),
    setPortfolioOverlay: (on) => {
      set({ portfolioOverlay: on });
      persist(get());
    },
    applyHighlights: (countries, note) => set({ highlightedCountries: countries, highlightNote: note }),
    clearHighlights: () => set({ highlightedCountries: [], highlightNote: null }),

    saveView: (name) => {
      const trimmed = name.trim().slice(0, 40);
      if (!trimmed) return null;
      const s = get();
      const view: SavedView = {
        id: `view-${Date.now().toString(36)}`,
        name: trimmed,
        activeLayers: [...s.activeLayers],
        timeRange: s.timeRange,
        mapMode: s.mapMode,
        mapSkin: s.mapSkin,
        showStars: s.showStars,
        economicMetric: s.economicMetric,
        portfolioOverlay: s.portfolioOverlay,
        createdAt: new Date().toISOString(),
      };
      // Re-saving the same name replaces it, so the list stays a set of
      // postures rather than accumulating duplicates.
      const rest = s.views.filter((v) => v.name !== trimmed);
      set({ views: [view, ...rest].slice(0, MAX_VIEWS) });
      persist(get());
      return view;
    },
    applyView: (id) => {
      const view = get().views.find((v) => v.id === id);
      if (!view) return;
      // Reconcile layers against the canonical registry so a view saved before a
      // layer existed/retired never restores a dead id.
      const known = new Set<string>(ALL_LAYER_IDS);
      set({
        activeLayers: view.activeLayers.filter((l) => known.has(l)),
        timeRange: view.timeRange,
        mapMode: view.mapMode,
        mapSkin: view.mapSkin ?? 'glow',
        showStars: view.showStars ?? true,
        economicMetric: view.economicMetric,
        portfolioOverlay: view.portfolioOverlay,
      });
      persist(get());
    },
    deleteView: (id) => {
      set({ views: get().views.filter((v) => v.id !== id) });
      persist(get());
    },
  };
});

export function timeRangeHours(id: TimeRangeId): number {
  return TIME_RANGES.find((r) => r.id === id)?.hours ?? 24;
}

/** Phase 1 layer ids (used to label the controller honestly). */
export const PHASE1_LAYERS: LayerId[] = ['events', 'markets'];

export type { LayerId, MapLayerType };
