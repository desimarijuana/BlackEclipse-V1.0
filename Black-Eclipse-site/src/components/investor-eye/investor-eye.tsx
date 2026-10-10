'use client';

// ── Investor Eye — main screen ───────────────────────────────────────────────
// The "God's Eye" workspace: a large interactive world, a layer controller, a
// timeline, and context panels. The map is the hero (spec §52) — chrome is kept
// minimal and dense, matching the BlackEclipse terminal language.
//
// Data flow: DataHub topics → `MapLayer[]` (pure builders) → <WorldMap>. All
// business logic lives in `lib/investor-eye/`; this component only wires.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ScanEye, Search, RefreshCw, X, Loader2, Maximize2 } from '@/lib/icons';
import { useTopic } from '@/lib/workspace/data-hub';
import { IE_COMPANIES_TOPIC, registerEconomyTopic, registerStateTopic } from '@/lib/investor-eye/topics';
import { buildAllLayers, type LayerId } from '@/lib/investor-eye/layers';
import { TIME_RANGES, timeRangeHours, useInvestorEyeStore } from '@/lib/investor-eye/store';
import { formatClock } from '@/lib/investor-eye/format';
import { useDisplayTimeZone } from '@/lib/timezone';
import { countryByIso2 } from '@/lib/investor-eye/countries';
import { conflictCoverage } from '@/lib/investor-eye/coverage';
import { cn } from '@/lib/utils';
import type {
  CompanyPoint, EconomicLayerData, InvestorEyeState, NormalizedEvent,
} from '@/lib/investor-eye/types';
import { WorldMap } from './world-map';
import { LayerController } from './layer-controller';
import { Timeline } from './timeline';
import { DataStatusChip } from './data-status';
import { DotGrid } from '@/components/ui/ascii-loader';
import { WhatChanged } from './what-changed';
import { CountryPanel } from './country-panel';
import { EventPanel } from './event-panel';
import { CompanyPanel } from './company-panel';
import { RiskPanel } from './risk-panel';
import { PortfolioPanel } from './portfolio-panel';
import { TransmissionsPanel } from './transmissions-panel';
import { GraphPanel } from './graph-panel';
import { FullPageMap } from './full-page-map';
import { MapViewControls } from './map-view-controls';
import { HeatmapToggle } from './heatmap-toggle';
import { LiveFeed } from './live-feed';
import { ConflictResearchPanel } from './conflict-research-panel';
import { EventDossierOverlay } from './event-dossier-overlay';
import { AlertsPanel } from './alerts-panel';
import { SourceHealthPanel } from './source-health-panel';
import { SavedViews } from './saved-views';
import { usePageShortcuts } from '@/hooks/use-page-shortcuts';
import { canHandleKeyboardEvent, matchesShortcut } from '@/lib/keyboard';

export function InvestorEyeScreen() {
  const selectedCountry = useInvestorEyeStore((s) => s.selectedCountry);
  const selectedEvent = useInvestorEyeStore((s) => s.selectedEvent);
  const dossierOpen = useInvestorEyeStore((s) => s.dossierOpen);
  const setDossierOpen = useInvestorEyeStore((s) => s.setDossierOpen);
  const selectedMarket = useInvestorEyeStore((s) => s.selectedMarket);
  const selectedCompany = useInvestorEyeStore((s) => s.selectedCompany);
  const activeLayers = useInvestorEyeStore((s) => s.activeLayers);
  const timeRange = useInvestorEyeStore((s) => s.timeRange);
  const economicMetric = useInvestorEyeStore((s) => s.economicMetric);
  const portfolioOverlay = useInvestorEyeStore((s) => s.portfolioOverlay);
  const mapMode = useInvestorEyeStore((s) => s.mapMode);
  const mapSkin = useInvestorEyeStore((s) => s.mapSkin);
  const showStars = useInvestorEyeStore((s) => s.showStars);
  const showCountryLabels = useInvestorEyeStore((s) => s.showCountryLabels);
  const fullPage = useInvestorEyeStore((s) => s.fullPage);
  const highlightedCountries = useInvestorEyeStore((s) => s.highlightedCountries);
  const highlightNote = useInvestorEyeStore((s) => s.highlightNote);

  const setSelectedCountry = useInvestorEyeStore((s) => s.setSelectedCountry);
  const setSelectedEvent = useInvestorEyeStore((s) => s.setSelectedEvent);
  const setSelectedMarket = useInvestorEyeStore((s) => s.setSelectedMarket);
  const setSelectedCompany = useInvestorEyeStore((s) => s.setSelectedCompany);
  const clearSelection = useInvestorEyeStore((s) => s.clearSelection);
  const toggleLayer = useInvestorEyeStore((s) => s.toggleLayer);
  const setTimeRange = useInvestorEyeStore((s) => s.setTimeRange);
  const setMapMode = useInvestorEyeStore((s) => s.setMapMode);
  const setFullPage = useInvestorEyeStore((s) => s.setFullPage);
  const setEconomicMetric = useInvestorEyeStore((s) => s.setEconomicMetric);
  const setPortfolioOverlay = useInvestorEyeStore((s) => s.setPortfolioOverlay);
  const applyHighlights = useInvestorEyeStore((s) => s.applyHighlights);
  const clearHighlights = useInvestorEyeStore((s) => s.clearHighlights);

  const hours = timeRangeHours(timeRange);
  const stateTopicId = useMemo(() => registerStateTopic(hours), [hours]);
  const stateEntry = useTopic<InvestorEyeState>(stateTopicId);
  const state = stateEntry.data;
  // The keyboard-nav handler reads the latest state without re-subscribing.
  const stateRef = useRef<InvestorEyeState | null>(null);
  stateRef.current = state ?? null;
  // A cold assembly takes ~15s. Distinguish "still loading" from "genuinely no
  // data": the hub's initial entry is `{data:null, source:'UNAVAILABLE'}`, so
  // `data === null` alone would flash UNAVAILABLE on every mount. `updatedAt` is
  // set only once a fetch has settled, so it is the honest "we tried" signal.
  const settled = stateEntry.updatedAt !== null;
  const loading = !state && !settled;
  const unavailable = !state && settled;
  // Pulled out before the guards so the banner text is readable without TS
  // narrowing `state` to `never` inside the `unavailable` branch.
  const lastKnownAt = state?.lastKnownAt ?? null;
  const staleGeneratedAt = state?.refreshing ? state.generatedAt : null;
  const displayTz = useDisplayTimeZone();
  // "Why can't I see conflicts?" — observed / quiet / degraded / unavailable.
  const coverage = useMemo(() => conflictCoverage(state), [state]);

  // Phase 2 inputs — only fetched when their layer is enabled.
  const needEconomy = activeLayers.includes('economy');
  const needCompanies = activeLayers.includes('companies');
  const needPortfolio = portfolioOverlay || activeLayers.includes('portfolio');

  const economyTopicId = useMemo(
    () => (needEconomy ? registerEconomyTopic(economicMetric) : null),
    [needEconomy, economicMetric],
  );
  const economyEntry = useTopic<EconomicLayerData>(economyTopicId ?? 'investor-eye:economy:__idle__');
  const companiesEntry = useTopic<{ companies: CompanyPoint[] }>(needCompanies ? IE_COMPANIES_TOPIC : 'investor-eye:companies:__idle__');

  const [portfolioExposure, setPortfolioExposure] = useState<Array<{ iso2: string; weight: number }>>([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchValue, setSearchValue] = useState('');
  const [searchBusy, setSearchBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // Resolve the selected event/country from the latest state so a market or
  // event clicked earlier keeps working after a refresh replaces the arrays.
  const liveEvent = useMemo(() => {
    if (!selectedEvent || !state) return selectedEvent;
    return state.events.find((e) => (e.id ?? e.dedupKey) === (selectedEvent.id ?? selectedEvent.dedupKey)) ?? selectedEvent;
  }, [selectedEvent, state]);

  // Panel selection is exclusive: opening one context closes the others
  // (otherwise a stale country/company panel would keep priority and a clicked
  // event would never render). Declared before `layers`, which consumes them.
  const handleSelectCountry = useCallback((iso2: string) => {
    setSelectedCountry(iso2);
    setSelectedMarket(null);
    setSelectedEvent(null);
    setSelectedCompany(null);
  }, [setSelectedCountry, setSelectedMarket, setSelectedEvent, setSelectedCompany]);

  const handleSelectEvent = useCallback((event: NormalizedEvent) => {
    setSelectedEvent(event);
    setSelectedCountry(null);
    setSelectedCompany(null);
    setSelectedMarket(null);
  }, [setSelectedEvent, setSelectedCountry, setSelectedCompany, setSelectedMarket]);

  const handleSelectCompany = useCallback((company: CompanyPoint) => {
    setSelectedCompany(company);
    setSelectedEvent(null);
    setSelectedMarket(null);
  }, [setSelectedCompany, setSelectedEvent, setSelectedMarket]);

  const layers = useMemo(() => {
    if (!state) return [];
    const economy = needEconomy && economyEntry.data?.values
      ? { metricLabel: economyEntry.data.metricLabel, values: economyEntry.data.values }
      : null;
    return buildAllLayers({
      state,
      economicValues: economy,
      companies: needCompanies ? companiesEntry.data?.companies : undefined,
      portfolioExposure: (portfolioOverlay || activeLayers.includes('portfolio')) ? portfolioExposure : undefined,
      onSelectEvent: handleSelectEvent,
      onSelectMarket: (m) => setSelectedMarket({ ...m }),
      onSelectCompany: handleSelectCompany,
    }).map((layer) => ({
      ...layer,
      // The store owns visibility; the layer builders own data/behavior.
      enabled: activeLayers.includes(layer.id as LayerId)
        // Event Density is the spatial component of the risk layer.
        || (layer.id === 'density' && activeLayers.includes('risk')),
    }));
  }, [state, activeLayers, needEconomy, economyEntry.data, needCompanies, companiesEntry.data, portfolioOverlay, portfolioExposure, handleSelectEvent, setSelectedMarket, handleSelectCompany]);

  const availableLayers = useMemo(() => {
    const set = new Set<string>(['events', 'markets']);
    if (!state) return set;
    if (state.events.some((e) => ['conflict', 'military', 'protest'].includes(e.eventType))) set.add('conflict');
    // Domain layers match type OR channel, so availability follows the same rule
    // (a `conflict` event transmitting through Shipping makes the layer useful).
    if (state.events.some((e) => e.eventType === 'shipping' || e.channels.includes('Shipping & Logistics'))) set.add('shipping');
    if (state.events.some((e) => e.eventType === 'energy' || e.channels.includes('Energy'))) set.add('energy');
    if (state.events.some((e) => ['trade', 'tariff', 'shipping'].includes(e.eventType) || e.channels.includes('Trade & Tariffs'))) set.add('trade');
    if (state.events.some((e) => e.commodities.length > 0)) set.add('commodities');
    // The weather layer is earthquakes only (fires have their own layer).
    if (state.events.some((e) => e.eventType === 'natural_disaster' && e.category !== 'fire')) set.add('weather');
    if (state.events.some((e) => e.eventType === 'natural_disaster' && e.category === 'fire')) set.add('fires');
    if (economyEntry.data?.values && Object.keys(economyEntry.data.values).length > 0) set.add('economy');
    if (companiesEntry.data?.companies?.length) set.add('companies');
    if (portfolioExposure.length > 0) set.add('portfolio');
    set.add('risk');
    // The heatmap draws from the same geolocated events as `events`, so it is
    // available whenever there is at least one event to weigh. Omitting it left
    // the chip dimmed as "no data" and made the layer look broken.
    if (state.events.length > 0) set.add('event-heatmap');
    return set;
  }, [state, economyEntry.data, companiesEntry.data, portfolioExposure]);

  const highlightPoints = useMemo(
    () =>
      highlightedCountries
        .map((iso2) => countryByIso2(iso2))
        .filter((c): c is NonNullable<typeof c> => Boolean(c))
        .map((c) => ({ iso2: c.iso2, name: c.name, lon: c.lon, lat: c.lat })),
    [highlightedCountries],
  );

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await fetch(`/api/investor-eye/state?hours=${hours}&refresh=1`);
      // The hub refetches the topic; force it to pick up the rebuilt state.
      const { dataHub } = await import('@/lib/workspace/data-hub');
      dataHub.refresh(stateTopicId);
    } catch {
      /* the topic keeps its previous data — the status chip stays honest */
    } finally {
      setRefreshing(false);
    }
  }, [hours, stateTopicId]);

  const runSearch = useCallback(async () => {
    const q = searchValue.trim();
    if (!q) return;
    setSearchBusy(true);
    try {
      const res = await fetch(`/api/investor-eye/query?q=${encodeURIComponent(q)}`);
      const json = (await res.json()) as {
        plan: { activateLayers: string[]; explanation: string } | null;
        matches: NormalizedEvent[];
      };
      if (json.plan) {
        const ids = new Set<LayerId>([...activeLayers, ...(json.plan.activateLayers as LayerId[])]);
        useInvestorEyeStore.getState().setLayers([...ids]);
        const countries = [...new Set((json.matches ?? []).flatMap((m) => m.countries))].slice(0, 12);
        applyHighlights(countries, json.plan.explanation);
      }
      setSearchOpen(false);
    } catch {
      applyHighlights([], 'Search failed — no results applied.');
    } finally {
      setSearchBusy(false);
    }
  }, [searchValue, activeLayers, applyHighlights]);

  const rootRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  usePageShortcuts(rootRef, [
    { id: 'investor-eye.search', label: 'Ask the map', keys: 'S', run: () => { setSearchOpen(true); searchRef.current?.focus(); }, enabled: !fullPage },
    { id: 'investor-eye.refresh', label: 'Refresh Investor Eye', keys: 'R', run: handleRefresh, enabled: !fullPage && !refreshing && !searchOpen },
  ]);

  // Escape clears the current selection anywhere on the screen. Full-page mode
  // and the full event dossier own Escape first (they close themselves), so this
  // stands down while either is open.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const s = useInvestorEyeStore.getState();
      if (!canHandleKeyboardEvent(e, rootRef.current) || s.fullPage || s.dossierOpen || searchOpen) return;
      if (matchesShortcut(e, 'Escape')) {
        e.preventDefault();
        clearSelection();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [clearSelection, searchOpen]);

  // Keyboard navigation over the event feed (spec §34): j/k or ↓/↑ step through
  // the newest-first event list and open each one, so the map is usable without
  // a mouse. Ignored while typing or when a modifier is held.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const s = useInvestorEyeStore.getState();
      if (!canHandleKeyboardEvent(e, rootRef.current) || s.fullPage || s.dossierOpen || searchOpen) return;

      const dir = matchesShortcut(e, 'J') || matchesShortcut(e, 'ArrowDown') ? 1 : matchesShortcut(e, 'K') || matchesShortcut(e, 'ArrowUp') ? -1 : 0;
      if (dir === 0) return;

      const events = (stateRef.current?.events ?? []);
      if (events.length === 0) return;
      e.preventDefault();

      const ordered = [...events].sort(
        (a, b) => Date.parse(b.publishedAt) - Date.parse(a.publishedAt),
      );
      const current = useInvestorEyeStore.getState().selectedEvent;
      const curKey = current ? (current.id ?? current.dedupKey) : null;
      const idx = curKey ? ordered.findIndex((x) => (x.id ?? x.dedupKey) === curKey) : -1;
      const next = idx < 0 ? (dir > 0 ? 0 : ordered.length - 1) : Math.min(ordered.length - 1, Math.max(0, idx + dir));
      handleSelectEvent(ordered[next]);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [handleSelectEvent, searchOpen]);


  if (fullPage) {
    return (
      <>
        <FullPageMap
          layers={layers}
          highlightPoints={highlightPoints}
          availableLayers={availableLayers}
          onSelectCountry={handleSelectCountry}
          eventCount={state?.events.length ?? 0}
          marketCount={state?.markets.length ?? 0}
          dataUnavailable={unavailable}
          lastKnownAt={state?.lastKnownAt ?? undefined}
          onExit={() => setFullPage(false)}
        />
        {dossierOpen && <EventDossierOverlay />}
      </>
    );
  }


  return (
    // MAP-FIRST LAYOUT: the whole screen scrolls. The map is the hero at full
    // width, with the layer/timeline controls directly beneath it, and all the
    // detail panels stacked below the fold where they never squeeze the map.
    <div ref={rootRef} data-keyboard-scope="Investor Eye" className="flex h-full min-h-0 w-full flex-col overflow-y-auto p-2 md:p-3">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-primary/25 bg-primary/15">
            <ScanEye className="text-primary" size={18} />
          </div>
          <div>
            <h1 className="font-serif text-base font-semibold leading-none tracking-tight text-foreground">
              Investor Eye
            </h1>
            <p className="mt-0.5 text-[10px] text-muted-foreground">
              World events → economic channels → markets → your exposure
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {state && <DataStatusChip status={state.status} />}
          <SavedViews />
          <MapViewControls />
          <HeatmapToggle />
          {/* Immersive map-only mode. */}
          <button
            onClick={() => setFullPage(true)}
            className="glass-button flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[10px] font-semibold text-muted-foreground hover:text-foreground cursor-pointer"
            title="Full-page map (map only)"
          >
            <Maximize2 size={12} /> <span className="hidden sm:inline">Full page</span>
          </button>
          <div className="relative">
            <button
              onClick={() => setSearchOpen((v) => !v)}
              className="glass-button flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[10px] font-semibold text-muted-foreground hover:text-foreground cursor-pointer"
            >
              <Search size={12} /> Ask the map
            </button>
            {searchOpen && (
              <div className="absolute right-0 top-full z-40 mt-1 w-72 glass-card-strong rounded-xl border border-white/10 p-2">
                <div className="flex items-center gap-1.5">
                  <input
                    ref={searchRef}
                    autoFocus
                    value={searchValue}
                    onChange={(e) => setSearchValue(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') void runSearch(); }}
                    placeholder="What is affecting oil?"
                    className="min-w-0 flex-1 rounded-lg border border-border/40 bg-background/60 px-2 py-1.5 text-[11px] text-foreground outline-none focus:border-primary/40"
                  />
                  <button
                    onClick={() => void runSearch()}
                    disabled={searchBusy}
                    className="rounded-lg border border-primary/30 bg-primary/15 px-2 py-1.5 text-[10px] font-semibold text-foreground disabled:opacity-50 cursor-pointer"
                  >
                    {searchBusy ? <Loader2 size={12} className="animate-spin" /> : 'Run'}
                  </button>
                </div>
                <div className="mt-1.5 text-[9px] leading-relaxed text-muted-foreground/70">
                  Deterministic search: activates matching layers and highlights countries. No AI on the query path.
                </div>
              </div>
            )}
          </div>
          <button
            onClick={() => void handleRefresh()}
            className="glass-button flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[10px] font-semibold text-muted-foreground hover:text-foreground cursor-pointer"
            title="Refresh from sources"
          >
            {refreshing ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
          </button>
        </div>
      </div>

      {highlightNote && (
        <div className="flex items-center justify-between gap-2 rounded-lg border border-primary/20 bg-primary/5 px-2.5 py-1 text-[10px] text-foreground">
          <span className="truncate">{highlightNote}</span>
          <button onClick={clearHighlights} className="shrink-0 text-muted-foreground hover:text-foreground cursor-pointer">
            <X size={11} />
          </button>
        </div>
      )}

      {/* ── HERO: the map plus a live intelligence rail ──────────────────── */}
      {/* The rail is why a click "tells you what it is about": the selection
          panel sits BESIDE the map, not below the fold, so clicking a pin
          immediately shows its intelligence without scrolling. */}
      <div className="mt-2 grid min-h-0 shrink-0 grid-cols-1 items-stretch gap-2 lg:h-[62vh] lg:grid-cols-[minmax(0,1fr)_440px] xl:grid-cols-[minmax(0,1fr)_460px]">
        <div className="relative h-[52vh] min-h-[320px] w-full overflow-hidden rounded-2xl border border-white/10 dark:border-white/5 glass-card lg:h-full lg:min-h-0">
          {loading && (
            <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-background/40">
              <DotGrid size={44} />
              <div className="flex flex-col items-center gap-1">
                <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                  Loading world state
                </span>
                <span className="font-mono text-[9px] text-muted-foreground/60">
                  {TIME_RANGES.find((r) => r.id === timeRange)?.label ?? ''} window · events, markets, sources
                </span>
              </div>
            </div>
          )}
          {unavailable && (
            <div className="absolute left-1/2 top-2 z-20 -translate-x-1/2">
              <div className="glass-card-subtle rounded-lg border border-red-500/20 px-3 py-1 text-[10px] text-foreground">
                DATA UNAVAILABLE{lastKnownAt ? ` · LAST KNOWN ${formatClock(lastKnownAt, displayTz)}` : ''}
              </div>
            </div>
          )}
          {!loading && !unavailable && staleGeneratedAt && (
            <div className="pointer-events-none absolute left-1/2 top-2 z-20 -translate-x-1/2">
              <div className="glass-card-subtle rounded-lg border border-sky-500/20 px-3 py-1 text-[10px] text-sky-200">
                LAST KNOWN {formatClock(staleGeneratedAt, displayTz)} · REFRESHING
              </div>
            </div>
          )}
          <WorldMap
            className="absolute inset-0"
            layers={layers}
            highlightPoints={highlightPoints}
            selectedEventKey={selectedEvent ? (selectedEvent.id ?? selectedEvent.dedupKey) : null}
            onSelectCountry={handleSelectCountry}
            mode={mapMode}
            skin={mapSkin}
            showStars={showStars}
            showCountryLabels={showCountryLabels}
            onModeUnavailable={() => setMapMode('2d')}
          />
          {/* Coverage honesty: when no conflicts are plotted, say WHETHER that
              is an observed quiet, a source coverage gap, or no feed at all —
              an empty conflict layer must never read as proof of calm. */}
          {state && !unavailable && coverage.status !== 'observed' && (
            <div className="pointer-events-none absolute bottom-7 left-2 z-10 max-w-[64%] rounded-md border border-amber-500/20 bg-black/45 px-2 py-0.5 text-[9px] font-mono text-amber-200/90 backdrop-blur-sm">
              {coverage.explanation}
            </div>
          )}
          {/* Map is the hero; a subtle frame label keeps provenance in view. */}
          <div className="pointer-events-none absolute bottom-2 left-2 z-10 text-[9px] font-mono text-muted-foreground/50">
            NATURAL EARTH · BLACKECLIPSE{mapMode === 'globe' ? ' · 3D GLOBE' : ''}{mapSkin === 'black' ? ' · BLACK' : ' · GLOW'}
          </div>
          {/* Immersive map-only affordance, on the map surface itself. */}
          <button
            onClick={() => setFullPage(true)}
            className="absolute right-2 top-2 z-10 flex items-center gap-1 rounded-lg border border-white/10 glass-card-subtle px-2 py-1 text-[9px] font-semibold text-muted-foreground hover:text-foreground cursor-pointer"
            title="Full-page map only"
          >
            <Maximize2 size={11} /> Map only
          </button>
          {/* Live counts, so the map has an at-a-glance figure. */}
          {state && (
            <div className="pointer-events-none absolute bottom-2 right-2 z-10 rounded-md border border-white/10 bg-black/30 px-2 py-0.5 text-[9px] font-mono text-muted-foreground backdrop-blur-sm">
              {state.events.length} events · {state.markets.length} markets
              {/* Retained observations: real, within-window events from an
                  earlier cycle. Surfaced so a rolled-up window is not read as
                  "everything was fetched just now". */}
              {state.events.some((e) => e.replayed) && (
                <span className="text-amber-300/80">
                  {' '}· {state.events.filter((e) => e.replayed).length} retained
                </span>
              )}
            </div>
          )}
        </div>

        {/* Right rail: selection intelligence, then the live stream. */}
        <div className="flex min-h-0 flex-col gap-2 overflow-hidden">
          {selectedCompany ? (
            <PanelShell className="h-[420px] shrink-0 lg:h-[50%]">
              <CompanyPanel
                company={selectedCompany}
                onClose={() => setSelectedCompany(null)}
                onSelectCountry={(iso2) => { setSelectedCompany(null); handleSelectCountry(iso2); }}
              />
            </PanelShell>
          ) : liveEvent ? (
            <PanelShell className="h-[460px] shrink-0 lg:h-[56%]">
              <EventPanel
                event={liveEvent}
                onClose={() => setSelectedEvent(null)}
                onSelectCountry={handleSelectCountry}
                onOpen={() => setDossierOpen(true)}
              />
            </PanelShell>
          ) : selectedCountry ? (
            <PanelShell className="h-[420px] shrink-0 lg:h-[50%]">
              <CountryPanel
                iso2={selectedCountry}
                name={countryByIso2(selectedCountry)?.name ?? selectedCountry}
                hours={hours}
                onClose={() => setSelectedCountry(null)}
                onSelectEvent={handleSelectEvent}
              />
            </PanelShell>
          ) : selectedMarket ? (
            <PanelShell className="shrink-0">
              <div className="px-4 py-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="text-sm font-semibold text-foreground">
                    {selectedMarket.name} — {selectedMarket.symbol}
                  </div>
                  <button
                    onClick={() => setSelectedMarket(null)}
                    className="shrink-0 rounded-lg p-1 text-muted-foreground hover:bg-accent hover:text-foreground cursor-pointer"
                    aria-label="Close market panel"
                  >
                    <X size={13} />
                  </button>
                </div>
                <div className="mt-2 flex items-baseline gap-2">
                  <span className="text-lg font-semibold text-foreground">
                    {selectedMarket.price.toFixed(2)}
                    <span className="ml-1 text-[10px] text-muted-foreground">{selectedMarket.currency ?? ''}</span>
                  </span>
                  <span className={cn('text-xs font-mono', selectedMarket.changePct >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                    {selectedMarket.changePct >= 0 ? '+' : ''}{selectedMarket.changePct.toFixed(2)}%
                  </span>
                </div>
                <div className="mt-2 text-[10px] text-muted-foreground">
                  Index observation for {selectedMarket.iso2 ?? selectedMarket.marketId}, via the existing JDDS
                  index path. Markets are observations only — not signals.
                </div>
                {selectedMarket.iso2 && (
                  <button
                    onClick={() => handleSelectCountry(selectedMarket.iso2 as string)}
                    className="mt-2 rounded-lg border border-primary/30 bg-primary/15 px-2 py-1 text-[10px] font-semibold text-foreground cursor-pointer"
                  >
                    Open country intelligence
                  </button>
                )}
              </div>
            </PanelShell>
          ) : null}

          <LiveFeed
            className="min-h-[240px] flex-1 lg:min-h-0"
            events={state?.events ?? []}
            onSelect={handleSelectEvent}
            loading={loading}
            selectedKey={selectedEvent ? (selectedEvent.id ?? selectedEvent.dedupKey) : undefined}
          />
        </div>
      </div>

      {/* Controls sit directly under the map, still above the fold. */}
      <div className="mt-2 shrink-0 space-y-2">
        <LayerController active={activeLayers} onToggle={toggleLayer} available={availableLayers} />
        <Timeline value={timeRange} onChange={setTimeRange} events={state?.events ?? []} windowHours={hours} />
      </div>

      {/* ── DETAIL — the standing analysis panels ────────────────────────── */}
      {/* CSS multi-column "masonry": a 3-track grid reserves the height of its
          TALLEST child in every track, which left a large dead gap under the
          short panels. Columns pack independently, so each panel sits directly
          beneath the previous one. `break-inside-avoid` keeps panels intact. */}
      <div className="mt-2 shrink-0 lg:columns-3 lg:gap-2 [&>*]:mb-2 [&>*]:break-inside-avoid">
        {needEconomy && (
          <div className="glass-card rounded-xl border border-white/10 dark:border-white/5 px-3 py-2">
            <div className="mb-1.5 text-[9px] font-bold uppercase tracking-widest text-muted-foreground">Economic Metric</div>
            <select
              value={economicMetric}
              onChange={(e) => setEconomicMetric(e.target.value)}
              className="w-full rounded-lg border border-border/40 bg-background/60 px-2 py-1.5 text-[11px] text-foreground outline-none focus:border-primary/40"
            >
              {ECONOMIC_METRIC_OPTIONS.map((m) => (
                <option key={m.id} value={m.id}>{m.label}</option>
              ))}
            </select>
          </div>
        )}
        {state && <WhatChanged events={state.events} markets={state.markets} windowHours={hours} />}
        <AlertsPanel />
        <RiskPanel />
        <TransmissionsPanel />
        {/* "Use AI to find conflicts": cited research findings, not fake map pins. */}
        {state && <ConflictResearchPanel windowHours={hours} />}
        {activeLayers.includes('portfolio') && (
          <label className="glass-card flex cursor-pointer items-center justify-between rounded-xl border border-white/10 px-3 py-2 text-[10px]">
            <span className="text-muted-foreground">Portfolio overlay</span>
            <input
              type="checkbox"
              checked={portfolioOverlay}
              onChange={(e) => setPortfolioOverlay(e.target.checked)}
              className="h-3.5 w-3.5 accent-[color:var(--primary)]"
            />
          </label>
        )}
        {needPortfolio && <PortfolioPanel onExposureReady={setPortfolioExposure} />}
        <SourceHealthPanel />
      </div>

      {/* The graph wants width, so it gets its own full-width row. */}
      <div className="mt-2 shrink-0">
        <GraphPanel />
      </div>

      {/* Sources strip, kept honest and at the bottom of the scroll. */}
      {state && state.status.sources.length > 0 && (
        <div className="mt-2 shrink-0 rounded-lg border border-border/20 px-2.5 py-2 text-[9px] leading-relaxed text-muted-foreground/60">
          Sources: {state.status.sources.map((s) => `${s.name} (${s.state === 'rate_limited' ? 'throttled' : s.lastError ? 'error' : s.lastSuccess ? 'ok' : 'idle'})`).join(' · ')}
          {' — '}layers without data are disabled rather than faked.
        </div>
      )}

      {/* Full event dossier. Portaled; rendered only while an event is selected
          and the user has asked to open it (rail peek → "Open dossier"). */}
      {dossierOpen && <EventDossierOverlay />}
    </div>
  );
}

/**
 * Frosted frame for a selection panel.
 *
 * Deliberately renders NO close button: every panel inside (Event, Country,
 * Company) already owns one in its header, and the inline market card below has
 * its own. A button here produced TWO overlapping crosses in the corner.
 * `children` is responsible for its own dismiss affordance.
 */
function PanelShell({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('relative overflow-hidden rounded-2xl border border-white/10 dark:border-white/5 glass-card', className ?? 'max-h-[420px]')}>
      {children}
    </div>
  );
}


const ECONOMIC_METRIC_OPTIONS = [
  { id: 'inflation', label: 'Inflation (YoY)' },
  { id: 'unemployment', label: 'Unemployment' },
  { id: 'gdp', label: 'Real GDP (YoY)' },
  { id: 'rate', label: 'Policy Rate' },
  { id: 'yield10y', label: '10Y Yield' },
  { id: 'money', label: 'M2 Money Supply' },
];
