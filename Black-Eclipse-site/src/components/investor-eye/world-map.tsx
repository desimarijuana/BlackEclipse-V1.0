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
import { DotGrid } from '@/components/ui/ascii-loader';
import {
  ensureWorldMapRegistered, iso2ForFeatureName, worldGlobeTexture, worldGlobeGlowTexture, type GeoFeature,
} from '@/lib/investor-eye/app-geo';
import { bindLayerEvents, buildMapOption, type MapMode, type MapSkin } from '@/lib/investor-eye/map-echarts';
import type { MapLayer } from '@/lib/investor-eye/types';
import { Starfield } from './starfield';

interface WorldMapProps {
  layers: MapLayer[];
  highlightPoints?: Array<{ iso2: string; name: string; lon: number; lat: number }>;
  onSelectCountry?: (iso2: string, name: string) => void;
  mode?: MapMode;
  /** Surface skin: blue "lit planet" vs the plain black terminal look. */
  skin?: MapSkin;
  /** Draw the animated starfield behind the map. Purely decorative. */
  showStars?: boolean;
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

/** Hard ceiling on globe initialisation before falling back to the flat map. */
const GLOBE_INIT_TIMEOUT_MS = 20_000;

export function WorldMap({ layers, highlightPoints, onSelectCountry, mode = '2d', skin = 'glow', showStars = true, onModeUnavailable, className }: WorldMapProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const featuresRef = useRef<GeoFeature[]>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'unavailable'>('loading');
  const [glReady, setGlReady] = useState(false);
  /**
   * Bumped every time a globe texture finishes drawing. The option-update effect
   * depends on it so switching SKIN re-renders the sphere with the new surface
   * without tearing down and rebuilding the chart.
   */
  const [texVersion, setTexVersion] = useState(0);

  // Keep the latest handlers/layers for the stable ECharts event callback, so
  // the init effect can run exactly once without depending on caller closures.
  const layersRef = useRef(layers);
  layersRef.current = layers;
  const onSelectCountryRef = useRef(onSelectCountry);
  onSelectCountryRef.current = onSelectCountry;
  const modeRef = useRef(mode);
  modeRef.current = mode;
  const geoReadyRef = useRef(false);
  /**
   * Equirectangular world texture for the 3D globe (drawn once per skin, then
   * reused). Keyed by skin: the blue and black planets are different textures.
   */
  const globeTextureRef = useRef<{ skin: MapSkin; url: string } | undefined>(undefined);
  /** Coastlines-only emission map — the globe's additive aura layer. */
  const globeGlowTextureRef = useRef<string | undefined>(undefined);

  const handleCountryClick = useMemo(
    () => (name: string) => {
      const iso2 = iso2ForFeatureName(featuresRef.current, name);
      if (iso2) onSelectCountryRef.current?.(iso2, name);
    },
    [],
  );

  // Load globe support when (and only when) it is requested. The surface
  // texture is drawn from the same GeoJSON as the 2D map, so it is awaited here
  // and passed into the option builder rather than imported there.
  //
  // Guarded on `globeTextureRef.current?.skin === skin`: that covers BOTH the
  // "never loaded" case and the "user switched skin" case. Reusing the previous
  // skin's cached texture (the earlier behaviour) would silently keep a blue
  // planet in the black skin.
  useEffect(() => {
    if (mode !== 'globe' || globeTextureRef.current?.skin === skin) return;
    let cancelled = false;
    // A hard ceiling on globe initialisation. `echarts-gl` is a large lazy
    // chunk and the texture is drawn to a 2048x1024 canvas; if either stalls
    // (a slow first compile, a software WebGL context) the surface would
    // otherwise sit on its loader forever. Falling back to the flat map is
    // always better than an unrecoverable spinner.
    const timeout = setTimeout(() => {
      if (cancelled) return;
      console.warn('[investor-eye] globe init exceeded its time budget; falling back to the flat map');
      onModeUnavailable?.();
    }, GLOBE_INIT_TIMEOUT_MS);
    void (async () => {
      const ok = await ensureGlobeSupport();
      if (cancelled) return;
      if (!ok) {
        onModeUnavailable?.();
        return;
      }
      try {
        // The emission texture is glow-skin only; skip drawing it for `black`.
        const [tex, glow] = await Promise.all([
          worldGlobeTexture(skin),
          skin === 'glow' ? worldGlobeGlowTexture() : Promise.resolve(undefined),
        ]);
        if (cancelled) return;
        globeTextureRef.current = { skin, url: tex };
        globeGlowTextureRef.current = glow;
      } catch (err) {
        // A texture failure must not blank the globe — echarts-gl falls back to
        // its own default surface, which is at least visible.
        console.warn('[investor-eye] globe texture failed, using default surface:', err);
      }
      if (!cancelled) {
        setGlReady(true);
        setTexVersion((v) => v + 1);
      }
    })();
    return () => {
      cancelled = true;
      clearTimeout(timeout);
    };
  }, [mode, skin, onModeUnavailable]);

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
        chart.setOption(buildMapOption({ layers: layersRef.current, highlightPoints, mode, skin, globeTexture: globeTextureRef.current?.url, globeGlowTexture: globeGlowTextureRef.current }));
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
    // regardless of which base component (geo or globe) is active. The skin's
    // base component (geo/globe) is merged by id, so it updates in place too.
    chart.setOption(
      buildMapOption({ layers, highlightPoints, mode, skin, globeTexture: globeTextureRef.current?.url, globeGlowTexture: globeGlowTextureRef.current }),
      { replaceMerge: ['series'] } as never,
    );
  }, [layers, highlightPoints, mode, skin, glReady, texVersion, handleCountryClick]);

  const overlay = useMemo(() => {
    // A SCOPED loader, never `TopLoader`. TopLoader portals to `document.body`
    // at z-[45], so using it here covered the ENTIRE app (sidebar included) and
    // left the user stuck on a 95% overlay whenever the map was still loading —
    // a map-local loader must stay inside the map box.
    if (status === 'loading' || (mode === 'globe' && !glReady)) {
      return (
        <div className="flex h-full w-full flex-col items-center justify-center gap-3">
          <DotGrid size={40} />
          <span className="font-mono text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
            {mode === 'globe' ? 'Initialising globe' : 'Loading map'}
          </span>
        </div>
      );
    }
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
      {/* Backdrop. With stars ON the starfield canvas paints the whole sky, so
          this is only visible where the canvas is (and when stars are OFF, where
          it is the entire background). Matched to the skin so switching stars off
          still looks deliberate rather than like a missing layer. */}
      {!showStars && (
        <div
          aria-hidden="true"
          className="absolute inset-0"
          style={{
            background: skin === 'glow'
              ? 'radial-gradient(120% 90% at 50% 42%, #071a3d 0%, #04102b 55%, #020a1c 100%)'
              : 'radial-gradient(120% 90% at 50% 42%, #101114 0%, #08090b 60%, #040405 100%)',
          }}
        />
      )}
      {/* Starfield sits behind the chart in BOTH projections: flat mode reads it
          as a dark sky, globe mode as space behind the planet. It is a canvas,
          not a CSS gradient, so the density scales with the container. The skin
          follows the surface — the plain skin gets a still, flat-black sky.
          Unmounting it (rather than hiding it) is what actually stops the rAF
          loop, which matters because this screen also runs a WebGL render loop. */}
      {showStars && (
        <Starfield className="absolute inset-0 h-full w-full" density={mode === 'globe' ? 1 : 0.7} skin={skin} />
      )}
      <div ref={ref} className="absolute inset-0 h-full w-full" />
      {overlay && <div className="pointer-events-none absolute inset-0 z-10">{overlay}</div>}
    </div>
  );
}
