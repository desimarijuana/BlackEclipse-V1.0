'use client';

// ── The live chart — a real chart, not a picture ────────────────────────────
//
// The engine (Python) authors the chart as a Plotly FIGURE; this component
// renders it in the browser as vector SVG, with zoom, pan, hover, a legend and
// a PNG/zoom toolbar. It is a CHART, not an image of one.
//
// The library is loaded once from the app's own route (never a CDN: the app
// works offline) and then reused. If it cannot be loaded, the component says
// so and the caller falls back to the drawn picture.
//
// The background is TRANSPARENT: the chart sits on the app's frosted surface
// without hiding the frost.

import { useEffect, useRef, useState } from 'react';
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

const LIB_URL = "/api/harness/charts/plotly";
const SCRIPT_ID = "eclipse-plotly";

type PlotlyGlobal = {
  newPlot: (
    element: HTMLElement,
    data: unknown[],
    layout: unknown,
    config?: unknown,
  ) => Promise<unknown>;
  react?: (element: HTMLElement, data: unknown[], layout: unknown, config?: unknown) => void;
  purge?: (element: HTMLElement) => void;
};

declare global {
  interface Window {
    Plotly?: PlotlyGlobal;
  }
}

let loading: Promise<PlotlyGlobal | null> | null = null;

/** Load the chart library once; every chart after that is instant. */
function loadPlotly(): Promise<PlotlyGlobal | null> {
  if (typeof window === "undefined") return Promise.resolve(null);
  if (window.Plotly) return Promise.resolve(window.Plotly);
  if (loading) return loading;
  loading = new Promise<PlotlyGlobal | null>((resolve) => {
    const existing = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null;
    const script = existing ?? document.createElement("script");
    const done = () => resolve(window.Plotly ?? null);
    if (!existing) {
      script.id = SCRIPT_ID;
      script.src = LIB_URL;
      script.async = true;
      script.onload = done;
      script.onerror = () => resolve(null);
      document.head.appendChild(script);
    } else {
      script.addEventListener("load", done);
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

export function PlotlyChart({
  figure,
  fallbackSrc,
  height = 320,
  className,
  alt,
}: PlotlyChartProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "ready" | "unavailable">("idle");

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !figure) return;
    let cancelled = false;
    setState("loading");
    loadPlotly()
      .then((Plotly) => {
        if (cancelled) return;
        if (!Plotly) {
          setState("unavailable");
          return;
        }
        const config = {
          displayModeBar: true,
          displaylogo: false,
          responsive: true,
          scrollZoom: true,
          modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"],
          toImageButtonOptions: { format: "png", scale: 2 },
        };
        const layout = {
          ...(figure.layout ?? {}),
          autosize: true,
          height,
        };
        void Plotly.newPlot(host, figure.data ?? [], layout, config).then(() => {
          if (!cancelled) setState("ready");
        });
      })
      .catch(() => {
        if (!cancelled) setState("unavailable");
      });
    return () => {
      cancelled = true;
      // Plotly leaves listeners and DOM behind; purge before the next chart.
      try {
        window.Plotly?.purge?.(host);
      } catch {
        // A chart that cannot be purged is replaced by the next render anyway.
      }
      host.replaceChildren();
    };
  }, [figure, height]);

  if (!figure) {
    if (!fallbackSrc) return null;
    return (
      /* eslint-disable-next-line @next/next/no-img-element */
      <img
        src={fallbackSrc}
        alt={alt ?? "Chart"}
        className={cn("block h-auto max-w-full object-contain", className)}
        style={{ maxHeight: height }}
      />
    );
  }

  return (
    <div className={cn("relative w-full", className)} style={{ height }}>
      {state !== "ready" && fallbackSrc && (
        /* eslint-disable-next-line @next/next/no-img-element */
        <img
          src={fallbackSrc}
          alt={alt ?? "Chart"}
          className="absolute inset-0 h-full w-full object-contain opacity-40"
        />
      )}
      {state === "unavailable" && (
        <div className="absolute inset-0 flex items-center justify-center">
          <p className="text-xs italic text-muted-foreground/70">
            The interactive chart library is unavailable — showing the picture.
          </p>
        </div>
      )}
      <div ref={hostRef} className="h-full w-full" data-testid="plotly-chart" />
    </div>
  );
}

export default PlotlyChart;
