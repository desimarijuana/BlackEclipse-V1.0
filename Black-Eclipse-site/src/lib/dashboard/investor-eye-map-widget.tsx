'use client';

// ── Investor Eye — Command Center MAP widget ─────────────────────────────────
// The spatial companion to the Investor Eye feed widget: the same interactive
// world map / 3D globe the full Investor Eye screen renders, embedded in the
// customizable dashboard grid.
//
// It renders the SAME data path as the full screen — DataHub state topics →
// `buildAllLayers()` (pure) → <WorldMap> — so there is one fetch path, one cache
// and no fabricated data. A failed/unavailable topic renders UNAVAILABLE, never
// an empty globe that reads as "nothing is happening".
//
// Selection (event / country / market / company) is written to the shared
// `useInvestorEyeStore`, so clicking a pin here is the same selection the full
// screen sees. The detail dossier is NOT embedded (the map is the point); a
// small "Open" affordance navigates to the Investor Eye tab where the panel
// lives. That keeps the heavy `echarts-gl` globe and its panel tree lazy.

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import dynamic from 'next/dynamic';
import { Loader2, Maximize2, Minimize2, ScanEye } from 'lucide-react';
import { useTopic } from '@/lib/workspace/data-hub';
import { registerStateTopic } from '@/lib/investor-eye/topics';
import { buildAllLayers, type LayerId } from '@/lib/investor-eye/layers';
import { TIME_RANGES, timeRangeHours, useInvestorEyeStore, type TimeRangeId } from '@/lib/investor-eye/store';
import { formatClock } from '@/lib/investor-eye/format';
import { useDisplayTimeZone } from '@/lib/timezone';
import { useCommandStore } from '@/lib/search/store';
import type { InvestorEyeState } from '@/lib/investor-eye/types';
import type { WidgetConfigField } from '@/lib/workspace/widget-def';
import type { WidgetPlacement } from '@/lib/workspace/types';

// The map (ECharts + lazy `echarts-gl`) is code-split so a dashboard WITHOUT
// this widget never pays for it. The lazy chunk is only requested when the
// widget is actually mounted (placed, unhidden).
const WorldMap = dynamic(
  () => import('@/components/investor-eye/world-map').then((m) => m.WorldMap),
  { ssr: false, loading: () => <MapLoader /> },
);

export const INVESTOR_EYE_MAP_RANGE_FIELD: WidgetConfigField = {
  key: 'range', label: 'Time window', type: 'select',
  options: [
    { value: '1h', label: 'Last hour' },
    { value: '6h', label: 'Last 6 hours' },
    { value: '24h', label: 'Last 24 hours' },
    { value: '7d', label: 'Last 7 days' },
    { value: '30d', label: 'Last 30 days' },
  ],
  default: '24h',
};

function MapLoader() {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-2">
      <Loader2 size={18} className="animate-spin text-muted-foreground/60" />
      <span className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground">Loading map</span>
    </div>
  );
}

export function InvestorEyeMapWidget({ placement }: { placement: WidgetPlacement }) {
  const cfg = placement.config ?? {};
  const range: TimeRangeId = TIME_RANGES.some((r) => r.id === cfg.range) ? (cfg.range as TimeRangeId) : '24h';
  const hours = timeRangeHours(range);

  // topics.ts registers a state topic for every window at module load, so the id
  // is always live — constructing it is pure (no fetch-registration race).
  const topicId = useMemo(() => registerStateTopic(hours), [hours]);
  const stateEntry = useTopic<InvestorEyeState>(topicId);
  const state = stateEntry.data;
  // The hub's initial entry is `{data:null, source:'UNAVAILABLE'}`; `updatedAt`
  // is set only once a fetch settles, so it is the honest "we tried" signal.
  const settled = stateEntry.updatedAt !== null;
  const loading = !state && !settled;
  const unavailable = !state && settled;
  const lastKnownAt = state?.lastKnownAt ?? null;
  const tz = useDisplayTimeZone();

  // Presentation + visibility come from the shared store, so the widget matches
  // the full screen (and the two stay in sync). Layers follow the store too.
  const activeLayers = useInvestorEyeStore((s) => s.activeLayers);
  const mapMode = useInvestorEyeStore((s) => s.mapMode);
  const mapSkin = useInvestorEyeStore((s) => s.mapSkin);
  const showStars = useInvestorEyeStore((s) => s.showStars);
  const setMapMode = useInvestorEyeStore((s) => s.setMapMode);
  const setSelectedEvent = useInvestorEyeStore((s) => s.setSelectedEvent);
  const setSelectedCountry = useInvestorEyeStore((s) => s.setSelectedCountry);
  const setSelectedMarket = useInvestorEyeStore((s) => s.setSelectedMarket);

  const [expanded, setExpanded] = useState(false);

  const layers = useMemo(() => {
    if (!state) return [];
    return buildAllLayers({
      state,
      onSelectEvent: (e) => { setSelectedEvent(e); setSelectedCountry(null); },
      onSelectMarket: (m) => setSelectedMarket({ ...m }),
    }).map((layer) => ({
      ...layer,
      // The store owns visibility; the layer builders own data/behavior.
      enabled: activeLayers.includes(layer.id as LayerId)
        // Event Density is the spatial component of the risk layer.
        || (layer.id === 'density' && activeLayers.includes('risk')),
    }));
  }, [state, activeLayers, setSelectedEvent, setSelectedCountry, setSelectedMarket]);

  const handleSelectCountry = useCallback((iso2: string) => {
    setSelectedCountry(iso2);
    setSelectedEvent(null);
  }, [setSelectedCountry, setSelectedEvent]);

  // Fullscreen reuses the SAME map, just in a bigger box — no second screen.
  const rootRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!expanded) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setExpanded(false); };
    window.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener('keydown', onKey);
    };
  }, [expanded]);

  const openFullScreen = () => useCommandStore.getState().dispatch({ tab: 'investor-eye' });

  const map = (
    <WorldMap
      className="absolute inset-0"
      layers={layers}
      onSelectCountry={(iso2) => handleSelectCountry(iso2)}
      mode={mapMode}
      skin={mapSkin}
      showStars={showStars}
      onModeUnavailable={() => setMapMode('2d')}
    />
  );

  const header = (
    <div className="flex items-center justify-between gap-2">
      <div className="flex min-w-0 items-center gap-1.5">
        <ScanEye size={13} className="shrink-0 text-primary" />
        <h3 className="font-serif text-sm font-semibold text-foreground truncate">Investor Eye Map</h3>
        {state && (
          <span className="font-mono text-[9px] text-muted-foreground/70">
            {state.events.length} events · {state.markets.length} markets
          </span>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {unavailable && (
          <span className="rounded-md border border-red-500/25 bg-red-500/10 px-1.5 py-0.5 font-mono text-[9px] text-red-300">
            UNAVAILABLE{lastKnownAt ? ` · LAST ${formatClock(lastKnownAt, tz)}` : ''}
          </span>
        )}
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="rounded-lg border border-white/15 dark:border-white/10 bg-accent/30 p-1.5 text-muted-foreground transition-all hover:border-primary/40 hover:text-primary cursor-pointer"
          title={expanded ? 'Exit fullscreen (Esc)' : 'Expand map'}
        >
          {expanded ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
        </button>
        <button
          type="button"
          onClick={openFullScreen}
          className="rounded-lg border border-white/15 dark:border-white/10 bg-accent/30 px-2 py-1.5 text-[9px] font-bold uppercase tracking-wide text-muted-foreground transition-all hover:border-primary/40 hover:text-primary cursor-pointer"
          title="Open Investor Eye for the full intelligence panels"
        >
          Open
        </button>
      </div>
    </div>
  );

  const body = (
    <div className="relative min-h-0 flex-1 overflow-hidden rounded-xl border border-white/10 dark:border-white/5">
      {loading && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-2 bg-background/40">
          <Loader2 size={18} className="animate-spin text-muted-foreground/60" />
          <span className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground">Loading world state</span>
        </div>
      )}
      {map}
      <div className="pointer-events-none absolute bottom-1.5 left-2 z-10 font-mono text-[8px] text-muted-foreground/50">
        NATURAL EARTH · BLACKECLIPSE{mapMode === 'globe' ? ' · 3D GLOBE' : ''}{mapSkin === 'black' ? ' · BLACK' : ' · GLOW'}
      </div>
    </div>
  );

  // One tree for both modes: expanding reuses the same header/body elements,
  // and the overlay is PORTALED to `document.body` for the same containing-block
  // reason the heatmap widget portals its expanded view — the Command Center
  // root carries `animate-fade-in-up`, whose transform would otherwise scope
  // `position: fixed` to the (short) widget card instead of the viewport.
  if (expanded && typeof document !== 'undefined') {
    return createPortal(
      <div className="fixed inset-0 z-[100] animate-fade-in">
        <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setExpanded(false)} />
        <div className="absolute inset-2 flex flex-col overflow-hidden rounded-2xl border border-white/10 glass-card-strong p-4 shadow-2xl shadow-black/50 sm:inset-5">
          {header}
          <div className="mt-3 flex min-h-0 flex-1">{body}</div>
        </div>
      </div>,
      document.body,
    );
  }

  return (
    <div ref={rootRef} className="flex h-full flex-col p-4">
      {header}
      <div className="mt-2.5 flex min-h-0 flex-1">{body}</div>
    </div>
  );
}
