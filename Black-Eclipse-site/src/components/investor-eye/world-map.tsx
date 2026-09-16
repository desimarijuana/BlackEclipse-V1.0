'use client';

// ── Investor Eye — World Map ─────────────────────────────────────────────────
// The visualization layer. It knows how to render `MapLayer[]` with ECharts and
// nothing about events, markets, geopolitics, or provenance. All of that is
// passed in.
//
// Two presentations share one data path:
//   - `2d`    the flat ECharts geo map (default, no extra bundle cost)
//   - `globe` a rotatable 3D globe via `echarts-gl`, LAZY-LOADED
//
// The globe is deliberately an enhancement, not a requirement: `echarts-gl` is
// a large dependency, so it is fetched only when the user asks for the globe,
// and if that fetch fails the map stays on the flat projection and says so.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as echarts from 'echarts';
import { TopLoader } from '@/components/ui/top-loader';
import { ensureWorldMapRegistered, iso2ForFeatureName, type GeoFeature } from '@/lib/investor-eye/app-geo';
import { bindLayerEvents, buildMapOption, type MapMode } from '@/lib/investor-eye/map-echarts';
import type { MapLayer } from '@/lib/investor-eye/types';

interface WorldMapProps {
  layers: MapLayer[];
  highlightPoints?: Array<{ iso2: string; name: string; lon: number; lat: number }>;
  onSelectCountry?: (iso2: string, name: string) => void;
  mode?: MapMode;
  /** Called when the globe can't load, so the parent can revert the toggle. */
  onModeUnavailable?: () => void;
  className?: string;
}

/**
 * Load `echarts-gl` once. It registers itself against the ECharts instance, so
 * it must import the SAME `echarts` module (it does, via its peer dependency).
 * A failed load is remembered so we never retry on every render.
 */
let glLoaded: Promise<boolean> | null = null;
function ensureGlobeSupport(): Promise<boolean> {
  if (!glLoaded) {
    glLoaded = import('echarts-gl')
      .then(() => true)
      .catch((err) => {
        console.warn('[investor-eye] echarts-gl unavailable, staying on the flat map:', err);
        return false;
      });
  }
  return glLoaded;
}

export function WorldMap({ layers, highlightPoints, onSelectCountry, mode = '2d', onModeUnavailable, className }: WorldMapProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const featuresRef = useRef<GeoFeature[]>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'unavailable'>('loading');
  const [glReady, setGlReady] = useState(false);

  // Keep the latest handlers/layers for the stable ECharts event callback, so
  // the init effect can run exactly once without depending on caller closures.
  const layersRef = useRef(layers);
  layersRef.current = layers;
  const onSelectCountryRef = useRef(onSelectCountry);
  onSelectCountryRef.current = onSelectCountry;
  const modeRef = useRef(mode);
  modeRef.current = mode;
  const geoReadyRef = useRef(false);

  const handleCountryClick = useMemo(
    () => (name: string) => {
      const iso2 = iso2ForFeatureName(featuresRef.current, name);
      if (iso2) onSelectCountryRef.current?.(iso2, name);
    },
    [],
  );

  // Load globe support when (and only when) it is requested.
  useEffect(() => {
    if (mode !== 'globe' || glReady) return;
    let cancelled = false;
    void ensureGlobeSupport().then((ok) => {
      if (cancelled) return;
      if (ok) setGlReady(true);
      else onModeUnavailable?.();
    });
    return () => { cancelled = true; };
  }, [mode, glReady, onModeUnavailable]);

  // Create the chart. Re-runs when the presentation changes, because a globe
  // and a geo map are different component sets: reusing the same instance across
  // a switch leaves the old component mounted (ECharts merges by default), and
  // `replaceMerge: ['globe']` throws when echarts-gl is not registered.
  // Recreating is the only approach that is correct in both directions.
  useEffect(() => {
    let cancelled = false;
    if (!ref.current) return;
    // In globe mode, wait for echarts-gl — otherwise the option would name a
    // component ECharts does not have.
    if (mode === 'globe' && !glReady) return;

    const init = async () => {
      try {
        const features = await ensureWorldMapRegistered();
        if (cancelled || !ref.current) return;
        featuresRef.current = features;
        geoReadyRef.current = true;

        const chart = echarts.init(ref.current, undefined, { renderer: 'canvas' });
        chartRef.current = chart;
        bindLayerEvents(chart, layersRef.current, { onCountryClick: handleCountryClick });
        chart.setOption(buildMapOption({ layers: layersRef.current, highlightPoints, mode }));
        setStatus('ready');

        const ro = new ResizeObserver(() => chart.resize());
        ro.observe(ref.current);
        return () => ro.disconnect();
      } catch (err) {
        console.error('[investor-eye] world map init failed:', err);
        if (!cancelled) setStatus('unavailable');
      }
    };

    const cleanupPromise = init();

    return () => {
      cancelled = true;
      void cleanupPromise.then((cleanup) => cleanup?.());
      chartRef.current?.dispose();
      chartRef.current = null;
    };
    // `highlightPoints` is intentionally read at init only; the update effect
    // below handles later changes without a full recreate.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, glReady, handleCountryClick]);

  // Update the option in place when data changes (no recreate).
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !geoReadyRef.current) return;
    if (mode === 'globe' && !glReady) return;
    bindLayerEvents(chart, layers, { onCountryClick: handleCountryClick });
    // Only the series change here, so `replaceMerge: ['series']` is always valid
    // regardless of which base component (geo or globe) is active.
    chart.setOption(
      buildMapOption({ layers, highlightPoints, mode }),
      { replaceMerge: ['series'] } as never,
    );
  }, [layers, highlightPoints, mode, glReady, handleCountryClick]);

  const overlay = useMemo(() => {
    if (status === 'loading') return <TopLoader />;
    if (status === 'unavailable') {
      return (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="glass-card-subtle rounded-xl border border-white/10 px-4 py-3 text-center">
            <div className="text-[11px] font-semibold tracking-wide text-foreground">MAP DATA UNAVAILABLE</div>
            <div className="mt-1 text-[10px] text-muted-foreground">
              Country geometry could not be loaded. Event and market data are unaffected.
            </div>
          </div>
        </div>
      );
    }
    if (mode === 'globe' && !glReady) return <TopLoader />;
    return null;
  }, [status, mode, glReady]);

  // ECharts needs a resize when the container's size changes with the layout
  // (the map moves between hero/beside modes), not just on window resize.
  const resize = useCallback(() => chartRef.current?.resize(), []);
  useEffect(() => {
    const t = setTimeout(resize, 120);
    return () => clearTimeout(t);
  }, [mode, resize]);

  return (
    <div className={className}>
      <div ref={ref} className="h-full w-full" />
      {overlay && <div className="pointer-events-none absolute inset-0 z-10">{overlay}</div>}
    </div>
  );
}
