'use client';

// ── Investor Eye — World Map ─────────────────────────────────────────────────
// The visualization layer. It knows how to render `MapLayer[]` with ECharts and
// nothing about events, markets, geopolitics, or provenance. All of that is
// passed in.
//
// Responsibilities:
//   - register the world map geometry once,
//   - build the option from layers,
//   - rebind click handlers when layers change,
//   - resize responsively (ResizeObserver),
//   - render honest loading / unavailable states instead of a blank canvas.

import { useEffect, useMemo, useRef, useState } from 'react';
import * as echarts from 'echarts';
import { TopLoader } from '@/components/ui/top-loader';
import { ensureWorldMapRegistered, iso2ForFeatureName, type GeoFeature } from '@/lib/investor-eye/app-geo';
import { bindLayerEvents, buildMapOption } from '@/lib/investor-eye/map-echarts';
import type { MapLayer } from '@/lib/investor-eye/types';

interface WorldMapProps {
  layers: MapLayer[];
  highlightPoints?: Array<{ iso2: string; name: string; lon: number; lat: number }>;
  onSelectCountry?: (iso2: string, name: string) => void;
  className?: string;
}

export function WorldMap({ layers, highlightPoints, onSelectCountry, className }: WorldMapProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const featuresRef = useRef<GeoFeature[]>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'unavailable'>('loading');

  // Keep the latest handlers/layers for the stable ECharts event callback, so
  // the init effect can run exactly once without depending on caller closures.
  const layersRef = useRef(layers);
  layersRef.current = layers;
  const onSelectCountryRef = useRef(onSelectCountry);
  onSelectCountryRef.current = onSelectCountry;
  const geoReadyRef = useRef(false);

  const handleCountryClick = useMemo(
    () => (name: string) => {
      const iso2 = iso2ForFeatureName(featuresRef.current, name);
      if (iso2) onSelectCountryRef.current?.(iso2, name);
    },
    [],
  );

  useEffect(() => {
    let cancelled = false;
    if (!ref.current) return;

    const init = async () => {
      try {
        const features = await ensureWorldMapRegistered();
        if (cancelled || !ref.current) return;
        featuresRef.current = features;
        geoReadyRef.current = true;
        const chart = echarts.init(ref.current, undefined, { renderer: 'canvas' });
        chartRef.current = chart;

        // Stable click bridge: resolves the layer/datum at click time.
        bindLayerEvents(chart, layersRef.current, { onCountryClick: handleCountryClick });
        chart.setOption(buildMapOption({ layers: layersRef.current }));
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
    // Init runs once; option updates are handled below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Update the option whenever the layers change (no re-init).
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !geoReadyRef.current) return;
    // Re-bind so the event bridge always sees the current layer callbacks.
    bindLayerEvents(chart, layers, { onCountryClick: handleCountryClick });
    chart.setOption(buildMapOption({ layers, highlightPoints }), { replaceMerge: ['series'] });
  }, [layers, highlightPoints, handleCountryClick]);

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
    return null;
  }, [status]);

  return (
    <div className={className}>
      <div ref={ref} className="h-full w-full" />
      {overlay && <div className="pointer-events-none absolute inset-0 z-10">{overlay}</div>}
    </div>
  );
}
