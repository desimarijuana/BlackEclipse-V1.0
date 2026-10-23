'use client';

// ── The live chart — a real chart, not a picture ────────────────────────────
//
// The engine (Python) authors the chart as a Plotly FIGURE; this component
// renders it in the browser as vector SVG, with zoom, pan, hover, a legend and
// a PNG/zoom toolbar. It is a CHART, not an image of one.
//
// Loading is staged so the first paint is instant:
//
//   1. the drawn PNG (already fetched by the caller) is shown immediately;
//   2. the library is loaded only when the chart scrolls near the viewport,
//      on an idle frame — never on the critical path of the answer;
//   3. once the library is ready the live chart cross-fades in over the PNG.
//
// The library is loaded once from the app's own route (never a CDN: the app
// works offline) and then reused. If it cannot be loaded, the component keeps
// the drawn picture and says so.
//
// The background is TRANSPARENT: the chart sits on the app's frosted surface
// without hiding the frost.

import { useCallback, useEffect, useRef, useState } from 'react';
import { RotateCcw, ZoomIn, ZoomOut } from '@/lib/icons';
import { cn } from '@/lib/utils';

export interface PlotlyFigure {
  data: Array<Record<string, unknown>>;
  layout: Record<string, unknown>;
}

export interface PlotlyChartProps {
  /** The figure the engine authored. */
  figure?: PlotlyFigure | null;
  /** The drawn picture, shown while the chart loads (or if it cannot). */
  fallbackSrc?: string | null;
  height?: number;
  className?: string;
  alt?: string;
}

const LIB_URL = '/api/harness/charts/plotly';
const SCRIPT_ID = 'eclipse-plotly';

type PlotlyGlobal = {
  newPlot: (
    element: HTMLElement,
    data: unknown[],
    layout: unknown,
    config?: unknown,
  ) => Promise<unknown>;
  react?: (element: HTMLElement, data: unknown[], layout: unknown, config?: unknown) => void;
  relayout?: (element: HTMLElement, update: Record<string, unknown>) => Promise<unknown>;
  purge?: (element: HTMLElement) => void;
};

type Vec3 = { x: number; y: number; z: number };

type PlotlyAxis = {
  range?: [unknown, unknown];
  fixedrange?: boolean;
  r2l?: (value: unknown) => number;
  l2r?: (value: number) => unknown;
};

type PlotlyScene = { camera?: { eye?: Vec3; center?: Vec3 } };

type PlotlyHost = HTMLElement & {
  _fullLayout?: Record<string, PlotlyAxis | PlotlyScene>;
};

const PLOTLY_CONFIG = {
  displayModeBar: true,
  displaylogo: false,
  responsive: true,
  scrollZoom: true,
  doubleClick: 'reset',
  modeBarButtonsToRemove: ['select2d', 'lasso2d', 'autoScale2d'],
  toImageButtonOptions: { format: 'png', scale: 2 },
};

declare global {
  interface Window {
    Plotly?: PlotlyGlobal;
  }
}

let loading: Promise<PlotlyGlobal | null> | null = null;

/** Load the chart library once; every chart after that is instant. */
export function loadPlotly(): Promise<PlotlyGlobal | null> {
  if (typeof window === 'undefined') return Promise.resolve(null);
  if (window.Plotly) return Promise.resolve(window.Plotly);
  if (loading) return loading;
  loading = new Promise<PlotlyGlobal | null>((resolve) => {
    const existing = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null;
    const script = existing ?? document.createElement('script');
    const done = () => resolve(window.Plotly ?? null);
    if (!existing) {
      script.id = SCRIPT_ID;
      script.src = LIB_URL;
      script.async = true;
      script.onload = done;
      script.onerror = () => {
        // A failed load must be retryable on the next mount.
        loading = null;
        resolve(null);
      };
      document.head.appendChild(script);
    } else {
      script.addEventListener('load', done);
      // The script may already be loaded (the element exists but Plotly is not
      // on the window yet) - poll once, then give up.
      let tries = 0;
      const poll = window.setInterval(() => {
        tries += 1;
        if (window.Plotly || tries > 100) {
          window.clearInterval(poll);
          resolve(window.Plotly ?? null);
        }
      }, 50);
    }
  });
  return loading;
}

type IdleWindow = Window & {
  requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number;
  cancelIdleCallback?: (id: number) => void;
};

/** Run the work when the main thread is quiet; the PNG is already on screen. */
function onIdle(run: () => void): () => void {
  const w = window as IdleWindow;
  if (typeof w.requestIdleCallback === 'function') {
    const id = w.requestIdleCallback(run, { timeout: 1200 });
    return () => w.cancelIdleCallback?.(id);
  }
  const id = window.setTimeout(run, 150);
  return () => window.clearTimeout(id);
}

export function PlotlyChart({
  figure,
  fallbackSrc,
  height = 320,
  className,
  alt,
}: PlotlyChartProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [state, setState] = useState<'idle' | 'loading' | 'ready' | 'unavailable'>('idle');

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !figure) return;
    let cancelled = false;
    let cancelIdle: (() => void) | null = null;
    let observer: IntersectionObserver | null = null;

    const draw = () => {
      setState('loading');
      loadPlotly()
        .then(async (Plotly) => {
          if (cancelled) return;
          if (!Plotly) {
            setState('unavailable');
            return;
          }
          const layout = {
            ...(figure.layout ?? {}),
            autosize: true,
            height,
          };
          try {
            await Plotly.newPlot(host, figure.data ?? [], layout, PLOTLY_CONFIG);
            if (!cancelled) setState('ready');
          } catch {
            if (!cancelled) setState('unavailable');
          }
        })
        .catch(() => {
          if (!cancelled) setState('unavailable');
        });
    };

    const schedule = () => {
      cancelIdle = onIdle(draw);
    };

    // Load the 4.7 MB library only when the chart is about to be seen.
    if (typeof IntersectionObserver !== 'undefined') {
      observer = new IntersectionObserver(
        (entries) => {
          if (!entries.some((entry) => entry.isIntersecting)) return;
          observer?.disconnect();
          observer = null;
          schedule();
        },
        { rootMargin: '400px 0px' },
      );
      observer.observe(host);
    } else {
      schedule();
    }

    return () => {
      cancelled = true;
      observer?.disconnect();
      cancelIdle?.();
      // Plotly leaves listeners and DOM behind; purge before the next chart.
      try {
        window.Plotly?.purge?.(host);
      } catch {
        // A chart that cannot be purged is replaced by the next render anyway.
      }
      host.replaceChildren();
    };
  }, [figure, height]);

  const is3d = Boolean(
    figure?.data?.some((trace) => trace.type === 'scatter3d' || trace.type === 'surface'),
  );

  /** Scale the current view around its centre: <1 zooms in, >1 zooms out. */
  const zoomBy = useCallback(
    (factor: number) => {
      const host = hostRef.current as PlotlyHost | null;
      const Plotly = window.Plotly;
      if (!host || !Plotly?.relayout) return;
      try {
        if (is3d) {
          const scene = host._fullLayout?.scene as PlotlyScene | undefined;
          const camera = scene?.camera;
          const eye = camera?.eye;
          if (!eye) return;
          const center = camera?.center ?? { x: 0, y: 0, z: 0 };
          const scale = (value: number, pivot: number) => pivot + (value - pivot) * factor;
          void Plotly.relayout(host, {
            'scene.camera.eye': {
              x: scale(eye.x, center.x),
              y: scale(eye.y, center.y),
              z: scale(eye.z, center.z),
            },
          });
          return;
        }

        const update: Record<string, unknown> = {};
        for (const [key, raw] of Object.entries(host._fullLayout ?? {})) {
          if (!/^[xy]axis\d*$/.test(key)) continue;
          const axis = raw as PlotlyAxis;
          if (axis.fixedrange || !axis.range || !axis.r2l || !axis.l2r) continue;
          const [from, to] = axis.range;
          const low = axis.r2l(from);
          const high = axis.r2l(to);
          if (!Number.isFinite(low) || !Number.isFinite(high) || low === high) continue;
          const middle = (low + high) / 2;
          const half = (Math.abs(high - low) / 2) * factor;
          update[`${key}.range`] = [
            axis.l2r(middle - half),
            axis.l2r(middle + half),
          ];
        }
        if (Object.keys(update).length > 0) void Plotly.relayout(host, update);
      } catch {
        // A chart that cannot be zoomed keeps its current view.
      }
    },
    [is3d],
  );

  /** Put the chart back exactly as the engine authored it (axes or camera). */
  const resetView = useCallback(() => {
    const host = hostRef.current as PlotlyHost | null;
    const Plotly = window.Plotly;
    if (!host || !Plotly || !figure) return;
    try {
      if (Plotly.react) {
        void Plotly.react(
          host,
          figure.data ?? [],
          { ...(figure.layout ?? {}), autosize: true, height },
          PLOTLY_CONFIG,
        );
        return;
      }
      const update: Record<string, unknown> = {};
      for (const [key, raw] of Object.entries(host._fullLayout ?? {})) {
        if (!/^[xy]axis\d*$/.test(key)) continue;
        if (!(raw as PlotlyAxis).fixedrange) update[`${key}.autorange`] = true;
      }
      if (is3d) update['scene.camera'] = (figure.layout?.scene as { camera?: unknown } | undefined)?.camera;
      if (Object.keys(update).length > 0) void Plotly.relayout?.(host, update);
    } catch {
      // A chart that cannot be reset keeps its current view.
    }
  }, [figure, height, is3d]);

  if (!figure) {
    if (!fallbackSrc) return null;
    return (
      /* eslint-disable-next-line @next/next/no-img-element */
      <img
        src={fallbackSrc}
        alt={alt ?? 'Chart'}
        loading="eager"
        decoding="async"
        className={cn('block h-auto max-w-full object-contain', className)}
        style={{ maxHeight: height }}
      />
    );
  }

  const showPicture = state !== 'ready' && Boolean(fallbackSrc);

  return (
    <div className={cn('relative w-full', className)} style={{ height }}>
      <div
        ref={hostRef}
        className={cn(
          'h-full w-full transition-opacity duration-300',
          state === 'ready' ? 'opacity-100' : 'opacity-0',
        )}
        data-testid="plotly-chart"
      />
      {showPicture && (
        /* eslint-disable-next-line @next/next/no-img-element */
        <img
          src={fallbackSrc ?? ''}
          alt={alt ?? 'Chart'}
          loading="eager"
          decoding="async"
          className="pointer-events-none absolute inset-0 h-full w-full object-contain"
        />
      )}
      {state === 'ready' && (
        <div
          role="group"
          aria-label="Chart view controls"
          className="glass-card-subtle absolute bottom-2 left-2 z-10 flex items-center gap-0.5 rounded-lg p-0.5 opacity-80 transition-opacity hover:opacity-100 focus-within:opacity-100"
          data-testid="chart-view-controls"
        >
          <button
            type="button"
            onClick={() => zoomBy(0.7)}
            aria-label="Zoom in"
            title="Zoom in"
            className="flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <ZoomIn size={13} />
          </button>
          <button
            type="button"
            onClick={() => zoomBy(1 / 0.7)}
            aria-label="Zoom out"
            title="Zoom out"
            className="flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <ZoomOut size={13} />
          </button>
          <button
            type="button"
            onClick={resetView}
            aria-label="Reset view"
            title="Reset view"
            className="flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <RotateCcw size={13} />
          </button>
        </div>
      )}
      {state === 'unavailable' && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex justify-end p-1">
          <p className="rounded bg-background/70 px-1.5 py-0.5 text-[10px] italic text-muted-foreground/70">
            The interactive chart library is unavailable — showing the picture.
          </p>
        </div>
      )}
      {state === 'unavailable' && !fallbackSrc && (
        <div className="absolute inset-0 flex items-center justify-center">
          <p className="text-xs italic text-muted-foreground/70">
            The interactive chart library is unavailable.
          </p>
        </div>
      )}
    </div>
  );
}

export default PlotlyChart;
