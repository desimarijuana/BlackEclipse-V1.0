"use client";

// The chart surface — Eclipse's chart component.
//
// A chart is drawn by the runtime's chart engine (Python + matplotlib) and
// comes back as an artifact. This component owns the request, the loading
// state and the honest error state; the picture itself is the artifact's
// bytes, fetched through the artifact route.
//
// Rules this component keeps:
//   * the background is TRANSPARENT, so the frosted glass card behind it
//     still frosts — the figure is painted to sit on the card, not to replace
//     it;
//   * a failure says what failed. A chart that cannot be drawn is never an
//     empty box;
//   * the picture is labelled "computed" — it is a picture of numbers Eclipse
//     worked out, never a source.

import { useCallback, useEffect, useRef, useState } from "react";
import { downloadUrl } from "@/lib/harness/artifacts-browser";
import { renderChart, type ChartFigure, type ChartSpec } from "@/lib/harness/charts";

export interface PythonChartProps {
  /** The chart to draw. Changing it draws a new chart. */
  spec: ChartSpec;
  /** Extra classes for the wrapper. */
  className?: string;
  /** Accessible label for the picture. */
  alt?: string;
  /** Called when the picture is ready. */
  onRendered?: (figure: ChartFigure) => void;
  /** Called when the chart could not be drawn. */
  onError?: (message: string) => void;
}

type State =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; figure: ChartFigure; src: string }
  | { status: "error"; message: string };

export function PythonChart({
  spec,
  className,
  alt,
  onRendered,
  onError,
}: PythonChartProps) {
  const [state, setState] = useState<State>({ status: "idle" });
  const requestId = useRef(0);

  // The spec is a fresh object on every render in most callers, so the draw
  // is keyed on its CONTENT, not its identity.
  const key = useCallback(() => JSON.stringify(spec), [spec]);
  const specKey = key();

  useEffect(() => {
    const id = requestId.current + 1;
    requestId.current = id;
    let cancelled = false;
    setState({ status: "loading" });
    renderChart(spec)
      .then((rendered) => {
        if (cancelled || requestId.current !== id) return;
        const src = rendered.artifact.id ? downloadUrl(rendered.artifact.id) : null;
        if (!src) {
          const message = "the chart was drawn but could not be stored";
          setState({ status: "error", message });
          onError?.(message);
          return;
        }
        setState({ status: "ready", figure: rendered.figure, src });
        onRendered?.(rendered.figure);
      })
      .catch((err: unknown) => {
        if (cancelled || requestId.current !== id) return;
        const message = err instanceof Error ? err.message : "the chart could not be drawn";
        setState({ status: "error", message });
        onError?.(message);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [specKey]);

  if (state.status === "error") {
    return (
      <div
        className={`glass-card flex h-full min-h-[120px] flex-col items-center justify-center gap-1 p-4 text-center ${className ?? ""}`}
        data-testid="python-chart-error"
      >
        <span className="text-xs font-medium text-rose-300">Chart unavailable</span>
        <span className="text-[11px] text-muted-foreground">{state.message}</span>
      </div>
    );
  }

  if (state.status !== "ready") {
    return (
      <div
        className={`glass-card h-full min-h-[120px] w-full animate-pulse ${className ?? ""}`}
        aria-busy="true"
        data-testid="python-chart-loading"
      />
    );
  }

  const { figure, src } = state;
  return (
    <figure className={`glass-card relative overflow-hidden p-3 ${className ?? ""}`}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt={alt ?? figure.title ?? figure.summary}
        className="h-auto w-full"
        data-testid="python-chart-image"
      />
      <figcaption className="mt-2 flex items-center justify-between text-[10px] text-muted-foreground">
        <span>{figure.title ?? figure.summary}</span>
        <span
          className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 uppercase tracking-wide"
          title="A chart is a picture of numbers Eclipse worked out — never a source."
        >
          computed
        </span>
      </figcaption>
    </figure>
  );
}

export default PythonChart;
