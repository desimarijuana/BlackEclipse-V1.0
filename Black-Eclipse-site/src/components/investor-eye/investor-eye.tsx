'use client';

// ── Investor Eye — main screen ───────────────────────────────────────────────
// The "God's Eye" workspace: a large interactive world, a layer controller, a
// timeline, and context panels. The map is the hero (spec §52) — chrome is kept
// minimal and dense, matching the BlackEclipse terminal language.
//
// Data flow: DataHub topics → `MapLayer[]` (pure builders) → <WorldMap>. All
// business logic lives in `lib/investor-eye/`; this component only wires.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Globe2, Search, RefreshCw, X, Loader2 } from 'lucide-react';
import { useTopic } from '@/lib/workspace/data-hub';
import { IE_COMPANIES_TOPIC, registerEconomyTopic, registerStateTopic } from '@/lib/investor-eye/topics';
import { buildAllLayers, type LayerId } from '@/lib/investor-eye/layers';
import { timeRangeHours, useInvestorEyeStore } from '@/lib/investor-eye/store';
import { countryByIso2 } from '@/lib/investor-eye/countries';
import { cn } from '@/lib/utils';
import type {
  CompanyPoint, EconomicLayerData, InvestorEyeState, NormalizedEvent,
} from '@/lib/investor-eye/types';
import { WorldMap } from './world-map';
import { LayerController } from './layer-controller';
import { Timeline } from './timeline';
import { DataStatusChip } from './data-status';
import { WhatChanged } from './what-changed';
import { CountryPanel } from './country-panel';
import { EventPanel } from './event-panel';
import { CompanyPanel } from './company-panel';
import { RiskPanel } from './risk-panel';
import { PortfolioPanel } from './portfolio-panel';
import { TransmissionsPanel } from './transmissions-panel';
import { GraphPanel } from './graph-panel';

export function InvestorEyeScreen() {
  const selectedCountry = useInvestorEyeStore((s) => s.selectedCountry);
  const selectedEvent = useInvestorEyeStore((s) => s.selectedEvent);
  const selectedMarket = useInvestorEyeStore((s) => s.selectedMarket);
  const selectedCompany = useInvestorEyeStore((s) => s.selectedCompany);
  const activeLayers = useInvestorEyeStore((s) => s.activeLayers);
  const timeRange = useInvestorEyeStore((s) => s.timeRange);
  const economicMetric = useInvestorEyeStore((s) => s.economicMetric);
  const portfolioOverlay = useInvestorEyeStore((s) => s.portfolioOverlay);
  const mapMode = useInvestorEyeStore((s) => s.mapMode);
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
  const setEconomicMetric = useInvestorEyeStore((s) => s.setEconomicMetric);
  const setPortfolioOverlay = useInvestorEyeStore((s) => s.setPortfolioOverlay);
  const applyHighlights = useInvestorEyeStore((s) => s.applyHighlights);
  const clearHighlights = useInvestorEyeStore((s) => s.clearHighlights);

  const hours = timeRangeHours(timeRange);
  const stateTopicId = useMemo(() => registerStateTopic(hours), [hours]);
  const stateEntry = useTopic<InvestorEyeState>(stateTopicId);
  const state = stateEntry.data;

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
    if (state.events.some((e) => e.eventType === 'energy')) set.add('energy');
    if (state.events.some((e) => ['trade', 'tariff', 'shipping'].includes(e.eventType))) set.add('trade');
    if (state.events.some((e) => e.eventType === 'natural_disaster')) set.add('weather');
    if (economyEntry.data?.values && Object.keys(economyEntry.data.values).length > 0) set.add('economy');
    if (companiesEntry.data?.companies?.length) set.add('companies');
    if (portfolioExposure.length > 0) set.add('portfolio');
    set.add('risk');
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

  // Escape clears the current selection anywhere on the screen.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') clearSelection();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [clearSelection]);


  return (
    // MAP-FIRST LAYOUT: the whole screen scrolls. The map is the hero at full
    // width, with the layer/timeline controls directly beneath it, and all the
    // detail panels stacked below the fold where they never squeeze the map.
    <div className="flex h-full min-h-0 w-full flex-col overflow-y-auto p-2 md:p-3">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-primary/25 bg-primary/15">
            <Globe2 className="text-primary" size={18} />
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
          {/* Map presentation: flat vs 3D globe (globe lazy-loads echarts-gl). */}
          <div className="glass-button flex items-center gap-0.5 rounded-lg p-0.5">
            {(['2d', 'globe'] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMapMode(m)}
                title={m === '2d' ? 'Flat map' : '3D globe'}
                className={cn(
                  'rounded-md px-2 py-1 text-[10px] font-semibold transition-colors cursor-pointer',
                  mapMode === m ? 'bg-primary/20 text-foreground' : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {m === '2d' ? 'MAP' : 'GLOBE'}
              </button>
            ))}
          </div>
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

      {/* ── THE MAP — the hero, full width, tall ─────────────────────────── */}
      <div className="relative mt-2 h-[52vh] min-h-[320px] w-full shrink-0 overflow-hidden rounded-2xl border border-white/10 dark:border-white/5 glass-card md:h-[58vh]">
        {stateEntry.source === 'UNAVAILABLE' && (
          <div className="absolute left-1/2 top-2 z-20 -translate-x-1/2">
            <div className="glass-card-subtle rounded-lg border border-red-500/20 px-3 py-1 text-[10px] text-foreground">
              DATA UNAVAILABLE{state?.lastKnownAt ? ` · LAST KNOWN ${state.lastKnownAt.slice(11, 16)} UTC` : ''}
            </div>
          </div>
        )}
        <WorldMap
          className="absolute inset-0"
          layers={layers}
          highlightPoints={highlightPoints}
          onSelectCountry={handleSelectCountry}
          mode={mapMode}
          onModeUnavailable={() => setMapMode('2d')}
        />
        {/* Map is the hero; a subtle frame label keeps provenance in view. */}
        <div className="pointer-events-none absolute bottom-2 left-2 z-10 text-[9px] font-mono text-muted-foreground/50">
          NATURAL EARTH · BLACKECLIPSE{mapMode === 'globe' ? ' · 3D GLOBE' : ''}
        </div>
        {/* Live event count, so the map has an at-a-glance figure. */}
        {state && (
          <div className="pointer-events-none absolute bottom-2 right-2 z-10 rounded-md border border-white/10 bg-black/30 px-2 py-0.5 text-[9px] font-mono text-muted-foreground backdrop-blur-sm">
            {state.events.length} events · {state.markets.length} markets
          </div>
        )}
      </div>

      {/* Controls sit directly under the map, still above the fold. */}
      <div className="mt-2 shrink-0 space-y-2">
        <LayerController active={activeLayers} onToggle={toggleLayer} available={availableLayers} />
        <Timeline value={timeRange} onChange={setTimeRange} events={state?.events ?? []} windowHours={hours} />
      </div>

      {/* ── DETAIL — scrolls below the map ───────────────────────────────── */}
      <div className="mt-2 grid shrink-0 grid-cols-1 gap-2 lg:grid-cols-3">
        {/* Selection takes the first column when there is one. */}
        <div className="space-y-2 lg:col-span-1">
          {selectedCompany ? (
            <PanelShell onClose={() => setSelectedCompany(null)}>
              <CompanyPanel
                company={selectedCompany}
                onClose={() => setSelectedCompany(null)}
                onSelectCountry={(iso2) => { setSelectedCompany(null); handleSelectCountry(iso2); }}
              />
            </PanelShell>
          ) : selectedCountry ? (
            <PanelShell onClose={() => setSelectedCountry(null)}>
              <CountryPanel
                iso2={selectedCountry}
                name={countryByIso2(selectedCountry)?.name ?? selectedCountry}
                hours={hours}
                onClose={() => setSelectedCountry(null)}
                onSelectEvent={handleSelectEvent}
              />
            </PanelShell>
          ) : liveEvent ? (
            <PanelShell onClose={() => setSelectedEvent(null)}>
              <EventPanel
                event={liveEvent}
                onClose={() => setSelectedEvent(null)}
                onSelectCountry={handleSelectCountry}
              />
            </PanelShell>
          ) : selectedMarket ? (
            <PanelShell onClose={() => setSelectedMarket(null)}>
              <div className="px-4 py-3">
                <div className="text-sm font-semibold text-foreground">
                  {selectedMarket.name} — {selectedMarket.symbol}
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
          ) : (
            <div className="glass-card rounded-xl border border-white/10 px-3 py-4 text-[11px] text-muted-foreground">
              <div className="mb-1 font-semibold text-foreground">Explore the world</div>
              Click a country, an event pin or a market dot on the map — its intelligence appears here.
            </div>
          )}
        </div>

        {/* Then the standing panels: change summary, risk, transmission, graph. */}
        <div className="space-y-2 lg:col-span-1">
          {state && <WhatChanged events={state.events} markets={state.markets} windowHours={hours} />}
          <RiskPanel />
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
        </div>

        <div className="space-y-2 lg:col-span-1">
          <TransmissionsPanel />
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
        </div>
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
    </div>
  );
}

/** Frosted frame for a selection panel, so the three columns line up. */
function PanelShell({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="relative max-h-[420px] overflow-hidden rounded-2xl border border-white/10 dark:border-white/5 glass-card">
      <button
        onClick={onClose}
        className="absolute right-2 top-2 z-10 rounded-lg p-1 text-muted-foreground hover:bg-accent hover:text-foreground cursor-pointer"
        aria-label="Close panel"
      >
        <X size={13} />
      </button>
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
