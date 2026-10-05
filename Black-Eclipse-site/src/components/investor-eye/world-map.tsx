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
  ensureWorldMapRegistered, iso2ForFeatureName, worldGlobeTexture, worldGlobeGlowTexture,
  countryIsoForPoint, countryOutlineRings, type GeoFeature,
} from '@/lib/investor-eye/app-geo';
import {
  bindLayerEvents, buildMapOption, buildCountryOutlineSeries, hasDrawableBox,
  type MapMode, type MapSkin,
} from '@/lib/investor-eye/map-echarts';
import type { MapLayer } from '@/lib/investor-eye/types';
import { Starfield } from './starfield';

interface WorldMapProps {
  layers: MapLayer[];
  highlightPoints?: Array<{ iso2: string; name: string; lon: number; lat: number }>;
  /**
   * Key (`id ?? dedupKey`) of the selected event. A trade line matching it is
   * emphasised and the other routes dimmed, so clicking a link answers "what is
   * traded on THIS route?".
  */
  selectedEventKey?: string | null;
  onSelectCountry?: (iso2: string, name: string) => void;
  mode?: MapMode;
  /** Surface skin: blue "lit planet" vs the plain black terminal look. */
  skin?: MapSkin;
  /** Draw the animated starfield behind the map. Purely decorative. */
  showStars?: boolean;
  /** Draw country names on the map/globe. */
  showCountryLabels?: boolean;
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

export function WorldMap({ layers, highlightPoints, selectedEventKey, onSelectCountry, mode = '2d', skin = 'glow', showStars = true, showCountryLabels = true, onModeUnavailable, className }: WorldMapProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const featuresRef = useRef<GeoFeature[]>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'unavailable'>('loading');
  const [glReady, setGlReady] = useState(false);
  /**
   * Live container box (CSS px). The globe camera distance is derived from it so
   * the sphere fills the map; without re-rendering the option on resize the globe
   * would keep its first size after the layout changes.
   */
  const [box, setBox] = useState({ width: 0, height: 0 });
  /**
   * Bumped every time a globe texture finishes drawing. The option-update effect
   * depends on it so switching SKIN re-renders the sphere with the new surface
   * without tearing down and rebuilding the chart.
   */
  const [texVersion, setTexVersion] = useState(0);
  /**
   * Bumped each time a chart instance is CREATED or disposed. The chart is built
   * asynchronously (world geometry is awaited), so effects that need the live
   * instance cannot rely on `mode`/`glReady` alone — they can run a frame before
   * `chartRef.current` is populated, and a later `setOption` on a null ref is
   * silently lost. This nonce makes those effects re-run once the instance
   * genuinely exists.
   */
  const [chartNonce, setChartNonce] = useState(0);
  /**
   * ISO2 of the country under the pointer, or null. When the Trade layer is on,
   * this narrows the map to the routes that touch the hovered country, so
   * "what does THIS country trade?" is answered by the pointer alone.
   */
  const [hoveredCountryIso, setHoveredCountryIso] = useState<string | null>(null);

  // Keep the latest handlers/layers for the stable ECharts event callback, so
  // the init effect can run exactly once without depending on caller closures.
  const layersRef = useRef(layers);
  layersRef.current = layers;
  const onSelectCountryRef = useRef(onSelectCountry);
  onSelectCountryRef.current = onSelectCountry;
  const modeRef = useRef(mode);
  modeRef.current = mode;
  const selectedEventKeyRef = useRef(selectedEventKey);
  selectedEventKeyRef.current = selectedEventKey;
  const hoveredCountryIsoRef = useRef(hoveredCountryIso);
  hoveredCountryIsoRef.current = hoveredCountryIso;
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

  const handleCountryHover = useMemo(
    () => (name: string | undefined) => {
      setHoveredCountryIso(name ? (iso2ForFeatureName(featuresRef.current, name) ?? null) : null);
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

    /**
     * ECharts' geo map cannot be initialised against a zero-size container: the
     * internal View throws `Cannot read properties of null (reading '0')` from
     * its matrix copy. The full-screen map always has an explicit height, but an
     * embedded one (the Command Center widget) can mount a frame before flex
     * layout gives it a height. So the init waits for a non-zero box — the
     * ResizeObserver below then fires `initChart` once the box is real.
     */
    let chart: echarts.ECharts | null = null;
    let ro: ResizeObserver | null = null;

    const initChart = async () => {
      if (chart) return;
      const el = ref.current;
      // ECharts' geo View throws on a zero-size container (see `hasDrawableBox`).
      if (!el || !hasDrawableBox(el.clientWidth, el.clientHeight)) return;
      try {
        const features = await ensureWorldMapRegistered();
        if (cancelled || !ref.current) return;
        // The box may have been re-hidden while the geometry loaded.
        if (!hasDrawableBox(ref.current.clientWidth, ref.current.clientHeight)) return;
        featuresRef.current = features;
        geoReadyRef.current = true;

        chart = echarts.init(ref.current, undefined, { renderer: 'canvas' });
        chartRef.current = chart;
        setChartNonce((n) => n + 1);
        bindLayerEvents(chart, layersRef.current, { onCountryClick: handleCountryClick, onCountryHover: handleCountryHover });
        chart.setOption(buildMapOption({
          layers: layersRef.current, highlightPoints, selectedEventKey: selectedEventKeyRef.current,
          hoveredCountryIso: hoveredCountryIsoRef.current,
          mode, skin, showCountryLabels,
          globeTexture: globeTextureRef.current?.url, globeGlowTexture: globeGlowTextureRef.current,
          width: ref.current.clientWidth, height: ref.current.clientHeight,
        }));
        setStatus('ready');
      } catch (err) {
        console.error('[investor-eye] world map init failed:', err);
        if (!cancelled) setStatus('unavailable');
      }
    };

    ro = new ResizeObserver(() => {
      const el = ref.current;
      if (el) {
        setBox((prev) => {
          const next = { width: el.clientWidth, height: el.clientHeight };
          return prev.width === next.width && prev.height === next.height ? prev : next;
        });
      }
      if (chart) chart.resize();
      else void initChart();
    });
    ro.observe(ref.current);
    void initChart();

    return () => {
      cancelled = true;
      ro?.disconnect();
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
    bindLayerEvents(chart, layers, { onCountryClick: handleCountryClick, onCountryHover: handleCountryHover });
    // Only the series change here, so `replaceMerge: ['series']` is always valid
    // regardless of which base component (geo or globe) is active. The skin's
    // base component (geo/globe) is merged by id, so it updates in place too.
    // `visualMap` is part of the replace set so that turning the heatmap OFF
    // actually REMOVES its legend/colour mapping. `replaceMerge: ['series']`
    // alone left the stale visualMap mounted, which is what made the event pins
    // keep the heatmap's colouring after the layer was switched off.
    chart.setOption(
      buildMapOption({
        layers, highlightPoints, selectedEventKey, hoveredCountryIso, mode, skin, showCountryLabels,
        globeTexture: globeTextureRef.current?.url, globeGlowTexture: globeGlowTextureRef.current,
        width: box.width, height: box.height,
      }),
      { replaceMerge: ['series', 'visualMap'] } as never,
    );
  }, [layers, highlightPoints, selectedEventKey, hoveredCountryIso, mode, skin, showCountryLabels, glReady, texVersion, box, handleCountryClick, handleCountryHover]);

  /**
   * GLOBE country picking.
   *
   * The 3D `globe` is one textured sphere with no per-country geometry, so it
   * emits no geo hover/click — unlike the 2D `geo` component, which highlights a
   * country natively. To give the globe the same behaviour, a screen point is
   * raycast onto the sphere (`viewGL.castRay` + `Ray.intersectSphere`), converted
   * to lon/lat with the globe's own `pointToData`, then tested against the loaded
   * GeoJSON. The hovered country's rings are drawn as a `lines3D` outline and a
   * click selects it, so the globe is as interactive as the flat map.
   */
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || mode !== 'globe' || !glReady) return;
    const zr = chart.getZr();
    const el = ref.current;
    if (!el) return;

    type GlobeLike = {
      dataToPoint: (d: number[]) => number[];
      pointToData: (p: number[], out?: number[]) => number[];
      viewGL: { castRay: (x: number, y: number, out: unknown) => unknown };
      radius: number;
    };

    const getCoordSys = (): GlobeLike | null => {
      try {
        // `getModel` is marked private in the typings but is the documented way
        // to reach a component's coordinate system at runtime; cast through the
        // public surface rather than forking ECharts' types.
        const model = (chart as unknown as {
          getModel: () => { getComponent: (t: string) => { coordinateSystem?: GlobeLike } | undefined };
        }).getModel();
        const globe = model.getComponent('globe');
        const cs = globe?.coordinateSystem;
        return cs && cs.viewGL ? cs : null;
      } catch {
        return null;
      }
    };

    /**
     * Ray-cast a screen point onto the globe and resolve the country there.
     *
     * `ViewGL.castRay(x, y, out)` merely forwards `out` to the camera and then
     * returns that SAME `out` — passing `undefined` yields `undefined`, not a ray
     * (a real gotcha; the camera would build an internal `Ray`, but it is never
     * handed back). So a minimal ray is supplied and filled in place: the camera
     * writes `origin.array` / `direction.array`. The sphere intersection is then
     * done directly (|o + t·d|² = R²) instead of importing claygl's `Ray` just
     * for `intersectSphere` — no extra bundle weight for four lines of algebra.
     */
    const pick = (offsetX: number, offsetY: number): string | undefined => {
      const cs = getCoordSys();
      if (!cs) return undefined;
      try {
        const ray = { origin: { array: [0, 0, 0] }, direction: { array: [0, 0, 0] } };
        cs.viewGL.castRay(offsetX, offsetY, ray);
        const o = ray.origin.array;
        const d = ray.direction.array;
        const R = cs.radius;
        // a = 1 (d is normalized). b = 2·d·o, c = |o|² − R².
        const b = 2 * (d[0] * o[0] + d[1] * o[1] + d[2] * o[2]);
        const c = o[0] * o[0] + o[1] * o[1] + o[2] * o[2] - R * R;
        const disc = b * b - 4 * c;
        if (disc < 0) return undefined; // ray misses the sphere (clicked space)
        const t = (-b - Math.sqrt(disc)) / 2; // near intersection
        if (t < 0) return undefined;
        const point = [o[0] + d[0] * t, o[1] + d[1] * t, o[2] + d[2] * t];
        const [lon, lat] = cs.pointToData(point);
        return countryIsoForPoint(featuresRef.current, lon, lat);
      } catch {
        return undefined;
      }
    };

    // The outline series is only touched when the hovered country CHANGES, and
    // only on an animation frame. `setOption` is synchronous and re-runs the
    // whole series pipeline, so calling it per pointer event (as the first cut
    // did) competed with the orbit control every frame and made rotation stutter.
    let lastIso: string | undefined;
    let pending = false;
    let lastOffset = { x: 0, y: 0 };
    let raf = 0;

    const applyOutline = (iso: string | undefined) => {
      if (iso === lastIso) return;
      lastIso = iso;
      // The globe resolves its own hover by raycast, so the trade-isolation
      // state must be set here too (the 2D path sets it from geo hover).
      setHoveredCountryIso(iso ?? null);
      if (!iso) {
        zr.setCursorStyle('default');
        chart.setOption({ series: [buildCountryOutlineSeries([])] });
        return;
      }
      zr.setCursorStyle('pointer');
      chart.setOption({ series: [buildCountryOutlineSeries(countryOutlineRings(featuresRef.current, iso))] });
    };

    const flush = () => {
      raf = 0;
      if (!pending) return;
      pending = false;
      applyOutline(pick(lastOffset.x, lastOffset.y));
    };

    const onMove = (e: {
      offsetX: number; offsetY: number; target?: unknown;
      buttons?: number; which?: number; event?: { buttons?: number };
    }) => {
      // A hit on a pin/tooltip target is not a country pick — the pins own it.
      if (e.target) return;
      // While a mouse button is down the user is ROTATING the globe. Picking
      // mid-drag would run a point-in-polygon scan and possibly rebuild the
      // outline every frame, which is exactly the stutter being fixed — so the
      // pick is deferred until the drag ends (see `onUp`).
      //
      // zrender's event packet does NOT copy `buttons`; it keeps the native
      // event under `e.event` and a `which` shorthand. Reading only one of these
      // silently disables the guard (the first version read `e.event.buttons`
      // but zrender's `which` is the more reliably populated field), so all
      // three are checked.
      const dragging = (e.event?.buttons ?? 0) > 0 || e.buttons === 1 || e.buttons === 2 || e.which === 1 || e.which === 3;
      lastOffset = { x: e.offsetX, y: e.offsetY };
      if (dragging) {
        pending = true;
        return;
      }
      pending = true;
      if (!raf) raf = requestAnimationFrame(flush);
    };

    const onClick = (e: { offsetX: number; offsetY: number; target?: unknown }) => {
      if (e.target) return;
      const iso = pick(e.offsetX, e.offsetY);
      if (!iso) return;
      const name = featuresRef.current.find((f) => f.properties.iso2?.toUpperCase() === iso)?.properties.name ?? iso;
      onSelectCountryRef.current?.(iso, name);
    };

    const onLeave = () => {
      if (raf) { cancelAnimationFrame(raf); raf = 0; }
      pending = false;
      lastIso = undefined;
      setHoveredCountryIso(null);
      zr.setCursorStyle('default');
      chart.setOption({ series: [buildCountryOutlineSeries([])] });
    };

    // On button-up, re-pick once so the outline matches the settled view (the
    // drag itself skipped picking).
    const onUp = () => {
      pending = true;
      if (!raf) raf = requestAnimationFrame(flush);
    };

    zr.on('mousemove', onMove);
    zr.on('click', onClick);
    zr.on('globalout', onLeave);
    zr.on('mouseup', onUp);
    return () => {
      if (raf) cancelAnimationFrame(raf);
      zr.off('mousemove', onMove);
      zr.off('click', onClick);
      zr.off('globalout', onLeave);
      zr.off('mouseup', onUp);
    };
  }, [mode, glReady, chartNonce, handleCountryClick]);

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
