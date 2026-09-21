'use client';

// ── Investor Eye — Full-page map mode ────────────────────────────────────────
// An immersive "map only" presentation: the world fills the viewport and just a
// minimal dock of controls remains. It is a VIEW of the same surface, not a
// second screen — it reuses the same `MapLayer[]`, store selection and panels.
//
// Portaled to `document.body` for the same containing-block reason as the
// market-workspace overlays (a transformed/animated ancestor would scope the
// frosted glass and trap the fixed positioning).

import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Minimize2, X, ScanEye } from 'lucide-react';
import { WorldMap } from './world-map';
import { EventPanel } from './event-panel';
import { LayerController } from './layer-controller';
import { MapViewControls } from './map-view-controls';
import { countryByIso2 } from '@/lib/investor-eye/countries';
import { TIME_RANGES, useInvestorEyeStore, type TimeRangeId } from '@/lib/investor-eye/store';
import { formatClock } from '@/lib/investor-eye/format';
import { useDisplayTimeZone } from '@/lib/timezone';
import type { MapLayer } from '@/lib/investor-eye/types';
import type { LayerId } from '@/lib/investor-eye/layers';
import { cn } from '@/lib/utils';

interface FullPageMapProps {
  layers: MapLayer[];
  highlightPoints: Array<{ iso2: string; name: string; lon: number; lat: number }>;
  availableLayers: Set<string>;
  onSelectCountry: (iso2: string, name: string) => void;
  eventCount: number;
  marketCount: number;
  dataUnavailable?: boolean;
  lastKnownAt?: string;
  onExit: () => void;
}

export function FullPageMap({
  layers, highlightPoints, availableLayers, onSelectCountry,
  eventCount, marketCount, dataUnavailable, lastKnownAt, onExit,
}: FullPageMapProps) {
  const activeLayers = useInvestorEyeStore((s) => s.activeLayers);
  const toggleLayer = useInvestorEyeStore((s) => s.toggleLayer);
  const mapMode = useInvestorEyeStore((s) => s.mapMode);
  const mapSkin = useInvestorEyeStore((s) => s.mapSkin);
  const showStars = useInvestorEyeStore((s) => s.showStars);
  const showCountryLabels = useInvestorEyeStore((s) => s.showCountryLabels);
  const tz = useDisplayTimeZone();
  const setMapMode = useInvestorEyeStore((s) => s.setMapMode);
  const timeRange = useInvestorEyeStore((s) => s.timeRange);
  const setTimeRange = useInvestorEyeStore((s) => s.setTimeRange);
  const selectedEvent = useInvestorEyeStore((s) => s.selectedEvent);
  const selectedCountry = useInvestorEyeStore((s) => s.selectedCountry);
  const setSelectedEvent = useInvestorEyeStore((s) => s.setSelectedEvent);
  const setSelectedCountry = useInvestorEyeStore((s) => s.setSelectedCountry);

  // Esc exits. Lock page scroll so the reclaimed viewport is actually usable.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onExit();
    };
    window.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [onExit]);

  if (typeof document === 'undefined') return null;

  const countryName = selectedCountry ? countryByIso2(selectedCountry)?.name ?? selectedCountry : null;

  return createPortal(
    <div className="fixed inset-0 z-[85] flex flex-col bg-background">
      <WorldMap
        className="absolute inset-0"
        layers={layers}
        highlightPoints={highlightPoints}
        onSelectCountry={onSelectCountry}
        mode={mapMode}
        skin={mapSkin}
        showStars={showStars}
        showCountryLabels={showCountryLabels}
        onModeUnavailable={() => setMapMode('2d')}
      />

      {/* ── Top strip: identity, mode, exit ─────────────────────────────── */}
      <div className="pointer-events-none absolute inset-x-0 top-0 z-20 flex items-start justify-between gap-2 p-3">
        <div className="pointer-events-auto flex items-center gap-2 rounded-xl border border-white/10 glass-card-subtle px-2.5 py-1.5">
          <ScanEye size={14} className="text-primary" />
          <span className="text-[10px] font-bold uppercase tracking-widest text-foreground">
            Investor Eye
          </span>
          <span className="font-mono text-[9px] text-muted-foreground">
            {eventCount} events · {marketCount} markets
          </span>
          {dataUnavailable && (
            <span className="rounded-md border border-red-500/25 bg-red-500/10 px-1.5 py-0.5 font-mono text-[9px] text-red-300">
              DATA UNAVAILABLE{lastKnownAt ? ` · LAST ${formatClock(lastKnownAt, tz)}` : ''}
            </span>
          )}
        </div>

        <div className="pointer-events-auto flex items-center gap-1.5">
          <MapViewControls />
          <button
            onClick={onExit}
            className="glass-button flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[10px] font-semibold text-muted-foreground hover:text-foreground cursor-pointer"
            title="Exit full-page map (Esc)"
          >
            <Minimize2 size={12} /> Exit
            <kbd className="ml-0.5 rounded bg-white/[0.06] px-1 py-0.5 font-mono text-[9px]">Esc</kbd>
          </button>
        </div>
      </div>

      {/* ── Bottom dock: colour-coded layers + time window ───────────────── */}
      <div className="absolute inset-x-0 bottom-0 z-20 flex flex-col gap-1.5 p-3">
        {selectedEvent && (
          <div className="ml-auto max-h-[46vh] w-full max-w-sm overflow-hidden rounded-2xl border border-white/10 glass-drawer">
            <EventPanel
              event={selectedEvent}
              onClose={() => setSelectedEvent(null)}
              onSelectCountry={(iso2) => { setSelectedEvent(null); onSelectCountry(iso2, countryByIso2(iso2)?.name ?? iso2); }}
            />
          </div>
        )}
        {!selectedEvent && countryName && (
          <div className="ml-auto w-full max-w-sm rounded-2xl border border-white/10 glass-drawer px-3 py-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] font-semibold text-foreground">{countryName}</span>
              <button onClick={() => setSelectedCountry(null)} className="rounded-md p-0.5 text-muted-foreground hover:text-foreground cursor-pointer" aria-label="Clear country selection">
                <X size={12} />
              </button>
            </div>
            <div className="mt-0.5 text-[9px] text-muted-foreground">
              Country selected on the map. Exit full page for the full intelligence panel.
            </div>
          </div>
        )}

        <LayerController
          active={activeLayers as LayerId[]}
          onToggle={toggleLayer}
          available={availableLayers}
          showLegend={false}
          className="mx-auto w-full max-w-5xl"
        />

        <div className="mx-auto flex items-center gap-1 rounded-xl border border-white/10 glass-card-subtle px-2 py-1">
          <span className="mr-1 text-[8px] font-bold uppercase tracking-widest text-muted-foreground/70">Window</span>
          {TIME_RANGES.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => setTimeRange(r.id as TimeRangeId)}
              className={cn(
                'rounded-md px-2 py-1 text-[10px] font-mono font-bold transition-colors cursor-pointer border',
                timeRange === r.id
                  ? 'border-primary/30 bg-primary/15 text-foreground'
                  : 'border-transparent text-muted-foreground hover:bg-accent/40 hover:text-foreground',
              )}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>
    </div>,
    document.body,
  );
}
