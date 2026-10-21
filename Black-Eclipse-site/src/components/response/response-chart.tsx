'use client';

// ── ResponseChart — a chat chart, drawn by the Python chart engine ──────────
//
// A chart block in an answer is drawn by the runtime's chart engine
// (matplotlib): the browser asks the engine for the picture and shows the
// artifact it produced.
//
// The block may arrive in two shapes:
//
//   * the SIMPLE form — `chartType` plus `series` — which the engine renders
//     directly;
//   * the SCENE form — `panels` of `marks` — which is compositional, so the
//     model can draw ANY chart the user asks for (a violin, a box plot, a
//     Gantt, a funnel, a ridgeline, a dual-axis chart) without a new chart
//     kind existing for it.
//
// The picture is a LIVE chart: the engine authors it as a vector figure, so
// the reader can zoom, pan, hover a point and export it. What it is not is a
// canvas the app owns: the values a tooltip would show live in the block's own
// table/text.

import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom';
import { downloadUrl } from '@/lib/harness/artifacts-browser';
import { renderChart, type ChartFigureData } from '@/lib/harness/charts';
import { PlotlyChart } from '@/components/charts/plotly-chart';
import { chartBlockToSpec } from '@/lib/response/chart-spec';
import { registerChartArtifact, unregisterChart } from '@/lib/response/chart-registry';
import { Maximize2, Minimize2, X } from '@/lib/icons';
import type { ChartBlock } from '@/lib/response/contract';
import { cn } from '@/lib/utils';

export interface ResponseChartProps {
  block: ChartBlock;
  height?: number;
  className?: string;
  /** When false the chart keeps its inline size and offers no focus control. */
  focusable?: boolean;
}

type State =
  | { status: 'loading' }
  | { status: 'ready'; src: string; chart?: ChartFigureData }
  | { status: 'error'; message: string };

export function ResponseChart({ block, height = 260, className, focusable = true }: ResponseChartProps) {
  const [state, setState] = useState<State>({ status: 'loading' });
  const [focused, setFocused] = useState(false);

  const plan = useMemo(
    // Drawn close to how it is displayed, so the labels stay crisp. The title
    // is NOT drawn in the picture - the chat shows it above the chart.
    () => chartBlockToSpec(block, { theme: 'eclipse-dark', width: 1000, height: 560 }),
    [block],
  );
  const specKey = useMemo(() => (plan ? JSON.stringify(plan.spec) : ''), [plan]);

  useEffect(() => {
    if (!plan) return;
    const chartId = block.id;
    let cancelled = false;
    setState({ status: 'loading' });
    renderChart(plan.spec)
      .then((rendered) => {
        if (cancelled) return;
        const artifactId = rendered.artifact.id;
        if (!artifactId) {
          setState({ status: 'error', message: 'the chart was drawn but could not be stored' });
          return;
        }
        // The export helpers fetch the picture by artifact id.
        if (chartId) registerChartArtifact(chartId, artifactId);
        setState({
          status: 'ready',
          src: downloadUrl(artifactId),
          chart: rendered.chart,
        });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setState({
          status: 'error',
          message: err instanceof Error ? err.message : 'the chart could not be drawn',
        });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [specKey]);

  useEffect(() => {
    const chartId = block.id;
    if (!chartId) return;
    return () => unregisterChart(chartId);
  }, [block.id]);

  if (!plan) {
    return (
      <div
        className={cn('glass-card-subtle flex items-center justify-center rounded-xl p-3', className)}
        style={{ height }}
      >
        <p className="text-xs italic text-muted-foreground/70">No data series available to chart.</p>
      </div>
    );
  }

  if (state.status === 'error') {
    return (
      <div
        className={cn('glass-card-subtle flex items-center justify-center rounded-xl p-3 text-center', className)}
        style={{ height }}
        data-testid="response-chart-error"
      >
        <p className="text-xs italic text-muted-foreground/70">{state.message}</p>
      </div>
    );
  }

  const card = (
    <div
      className={cn(
        // Plain: no glass panel behind a chart - the chart IS the surface.
        'w-full',
        focused && 'mx-auto flex max-h-full max-w-[1600px] flex-col',
      )}
    >
      {focusable && (
        <div className="mb-1 flex justify-end gap-1">
          <button
            type="button"
            onClick={() => setFocused((value) => !value)}
            aria-label={focused ? 'Leave focus view' : 'Open focus view'}
            aria-pressed={focused}
            className="flex h-6 w-6 items-center justify-center rounded-md border border-border/50 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            {focused ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
          </button>
          {focused && (
            <button
              type="button"
              onClick={() => setFocused(false)}
              aria-label="Close focus view"
              className="flex h-6 w-6 items-center justify-center rounded-md border border-border/50 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <X size={12} />
            </button>
          )}
        </div>
      )}
      {state.status === 'ready' ? (
        <div className={cn('relative mx-auto w-full', focused ? 'max-w-[1400px]' : 'max-w-[1100px]')}>
          {/* The LIVE chart: vector, zoomable, pannable, with a hover readout.
              The drawn picture is the fallback (and the export). */}
          <PlotlyChart
            figure={state.chart}
            fallbackSrc={state.src}
            height={
              focused
                ? typeof window !== 'undefined'
                  ? Math.round(window.innerHeight * 0.82)
                  : 640
                : Math.max(420, height)
            }
            alt={block.title ?? 'Chart'}
            className="w-full"
          />
          {plan.notes.length > 0 && (
            <p className="mt-1 text-[10px] text-muted-foreground/70">{plan.notes.join(' ')}</p>
          )}
        </div>
      ) : (
        <div
          className="flex w-full items-center justify-center rounded-xl border border-border/10"
          style={{ height }}
          aria-busy="true"
          data-testid="response-chart-loading"
        >
          <span className="flex items-center gap-2 text-xs text-muted-foreground/70">
            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-primary" />
            Drawing the chart…
          </span>
        </div>
      )}
    </div>
  );

  if (!focused) return card;

  // The full view is PORTALLED to <body>: inside the chat it would live in the
  // chat's stacking context, so the app's own header (the top bar and the
  // price ribbon) would paint OVER the chart and collide with its toolbar. On
  // <body> the overlay sits above the shell, and its opaque backdrop hides the
  // header entirely - a full-width chart is a full-width chart.
  if (typeof document === 'undefined') return card;
  return createPortal(
    <div
      className="fixed inset-0 z-[300] flex flex-col bg-background/95 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={block.title ? `Chart: ${block.title}` : 'Chart focus view'}
      onClick={() => setFocused(false)}
      data-testid="response-chart-focus"
    >
      {card}
    </div>,
    document.body,
  );
}

export default ResponseChart;
