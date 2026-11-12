'use client';

// ── The chart shell — one surface for every drawn chart ──────────────────────
//
// A chart is drawn by the Python chart engine (matplotlib) in the runtime. This
// shell owns the request, the loading state, the empty state and the honest
// error state; the picture itself is the artifact's bytes, fetched back
// through the artifact route.
//
// What this component keeps:
//   * the background is TRANSPARENT, so the frosted glass card behind it
//     still frosts — the figure is painted to sit on the card, not to replace
//     it;
//   * a failure says what failed. A chart that cannot be drawn is never an
//     empty box;
//   * the picture is labelled "computed" — it is a picture of numbers Eclipse
//     worked out, never a source.
//
// The widgets build a `ChartSpec` (data) and hand it here. There is no option
// object, no callback and no per-widget rendering logic left.

import { useEffect, useMemo, useRef, useState } from "react";
import { downloadUrl } from "@/lib/harness/clients/artifacts-browser";
import { renderChart, type ChartFigure, type ChartSpec } from "@/lib/harness/charts";
import { cn } from "@/lib/utils";

export interface PythonChartProps {
  /** The chart to draw. `null` means "there is nothing to draw" (empty state). */
  spec: ChartSpec | null;
  /** The picture's height in pixels (the width is fluid). */
  height?: number;
  className?: string;
  /** A title above the picture. */
  title?: string;
  /** A short note beside the title (a unit, a window). */
  hint?: string;
  /** What the empty state says. */
  emptyText?: string;
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
  height = 240,
  className,
  title,
  hint,
  emptyText = "No data yet",
  alt,
  onRendered,
  onError,
}: PythonChartProps) {
  const [state, setState] = useState<State>({ status: "idle" });
  const requestId = useRef(0);

  // The spec is a fresh object on every render in most callers, so the draw
  // is keyed on its CONTENT, not its identity.
  const specKey = useMemo(() => (spec ? JSON.stringify(spec) : ""), [spec]);

  useEffect(() => {
    if (!spec) {
      setState({ status: "idle" });
      return;
    }
    const id = requestId.current + 1;
    requestId.current = id;
    let cancelled = false;
    setState({ status: "loading" });
    renderChart(spec)
      .then((rendered) => {
        if (cancelled || requestId.current !== id) return;
        const artifactId = rendered.artifact.id;
        if (!artifactId) {
          const message = "the chart was drawn but could not be stored";
          setState({ status: "error", message });
          onError?.(message);
          return;
        }
        setState({ status: "ready", figure: rendered.figure, src: downloadUrl(artifactId) });
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

  const header = title || hint ? (
    <div className="mb-2 flex items-center justify-between gap-2">
      {title && <h3 className="font-serif text-sm font-semibold text-foreground truncate">{title}</h3>}
      {hint && <span className="font-mono text-[9px] text-muted-foreground/70 shrink-0">{hint}</span>}
    </div>
  ) : null;

  if (!spec) {
    return (
      <div className={cn("flex flex-col", className)}>
        {header}
        <div className="flex items-center justify-center" style={{ height }}>
          <p className="text-xs text-muted-foreground/70 italic">{emptyText}</p>
        </div>
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col", className)}>
      {header}
      <div className="relative" style={{ height }}>
        {state.status === "loading" && (
          <div className="absolute inset-0 z-10 flex items-center justify-center">
            <span className="h-5 w-5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-primary" />
          </div>
        )}
        {state.status === "error" && (
          <div className="absolute inset-0 z-10 flex items-center justify-center px-3 text-center">
            <p className="text-xs text-muted-foreground/70 italic">{state.message}</p>
          </div>
        )}
        {state.status === "ready" && (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img
            src={state.src}
            alt={alt ?? state.figure.title ?? state.figure.summary}
            className="h-full w-full object-contain"
            data-testid="python-chart-image"
          />
        )}
      </div>
    </div>
  );
}

export default PythonChart;
