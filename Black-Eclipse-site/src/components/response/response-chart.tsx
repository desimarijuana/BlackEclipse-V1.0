'use client';

// ── ResponseChart — a chat chart, drawn by the Python chart engine ──────────
//
// A chart block in an answer is drawn by the runtime's chart engine: the browser
// asks the engine for the picture (and the live Plotly figure) and shows the
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
// A block (or a scene mark) may NAME its series (`dataSource`); it is resolved
// through the app's own price-history route before the spec is built.
//
// Loading is fast by design: the drawn PNG paints the moment it arrives, and
// the live Plotly chart is loaded lazily (in the PlotlyChart component) only
// when the chart is about to be seen. A render is cached per spec, so chat
// history scrolls without asking the engine to draw the same chart again.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { downloadUrl } from '@/lib/harness/artifacts-browser';
import { renderChart, type ChartFigureData, type RenderedChart } from '@/lib/harness/charts';
import { PlotlyChart } from '@/components/charts/plotly-chart';
import { chartBlockToSpec, type ChartPlan } from '@/lib/response/chart-spec';
import { chartSpecWarning } from '@/lib/response/chart-capabilities';
import { fetchQuantFigure, hydrateChartBlock } from '@/lib/response/chart-data';
import { registerChartArtifact, unregisterChart } from '@/lib/response/chart-registry';
import { Code, Loader2, Maximize2, Minimize2, X } from '@/lib/icons';
import { generateChartSource } from '@/lib/harness/notebook-client';
import { useNotebook } from '@/components/chat/notebook-provider';
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
  | { status: 'ready'; src: string; chart?: ChartFigureData; plan: ChartPlan }
  | { status: 'empty'; message: string }
  | { status: 'error'; message: string };

// A render is keyed on the resolved SPEC, not the block: the same numbers draw
// the same chart, so re-mounting a message (scrolling, focus) is instant.
const RENDER_CACHE = new Map<string, RenderedChart>();
const RENDER_IN_FLIGHT = new Map<string, Promise<RenderedChart>>();
const RENDER_CACHE_LIMIT = 40;

function cachedRender(specKey: string, spec: ChartPlan['spec']): Promise<RenderedChart> {
  const cached = RENDER_CACHE.get(specKey);
  if (cached) return Promise.resolve(cached);
  const inFlight = RENDER_IN_FLIGHT.get(specKey);
  if (inFlight) return inFlight;
  const run = renderChart(spec)
    .then((rendered) => {
      RENDER_CACHE.set(specKey, rendered);
      if (RENDER_CACHE.size > RENDER_CACHE_LIMIT) {
        const oldest = RENDER_CACHE.keys().next().value;
        if (oldest !== undefined) RENDER_CACHE.delete(oldest);
      }
      return rendered;
    })
    .finally(() => RENDER_IN_FLIGHT.delete(specKey));
  RENDER_IN_FLIGHT.set(specKey, run);
  return run;
}

export function ResponseChart({ block, height = 260, className, focusable = true }: ResponseChartProps) {
  const [state, setState] = useState<State>({ status: 'loading' });
  const [focused, setFocused] = useState(false);
  const [editingCode, setEditingCode] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const notebook = useNotebook();

  // The block is a fresh object on every render in most callers, so the work is
  // keyed on its CONTENT, not its identity.
  const blockKey = useMemo(() => JSON.stringify(block), [block]);
  // A computed quant figure has no series of its own; its spec is built from a
  // stored experiment. It still gets a registry id so PNG/PDF export works.
  const chartId = block.id ?? (
    block.quant ? `quant:${block.quant.experimentId}:${block.quant.figure}` : undefined
  );

  useEffect(() => {
    let cancelled = false;
    setState({ status: 'loading' });
    void (async () => {
      try {
        let plan: ChartPlan | null;
        if (block.quant) {
          const spec = await fetchQuantFigure(block.quant);
          if (cancelled) return;
          plan = { spec, kind: spec.kind, notes: [] };
        } else {
          const hydrated = await hydrateChartBlock(block);
          if (cancelled) return;
          plan = chartBlockToSpec(hydrated, { theme: 'eclipse-dark', width: 1000, height: 560 });
        }
        if (!plan) {
          setState({ status: 'empty', message: 'No data series available to chart.' });
          return;
        }
        const warning = chartSpecWarning(plan.spec);
        if (warning) {
          setState({ status: 'error', message: warning });
          return;
        }
        const specKey = JSON.stringify(plan.spec);
        const rendered = await cachedRender(specKey, plan.spec);
        if (cancelled) return;
        const artifactId = rendered.artifact.id;
        if (!artifactId) {
          setState({ status: 'error', message: 'the chart was drawn but could not be stored' });
          return;
        }
        // The export helpers fetch the picture by artifact id.
        if (chartId) registerChartArtifact(chartId, artifactId);
        setState({ status: 'ready', src: downloadUrl(artifactId), chart: rendered.chart, plan });
      } catch (err) {
        if (cancelled) return;
        setState({
          status: 'error',
          message: err instanceof Error ? err.message : 'the chart could not be drawn',
        });
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blockKey]);

  useEffect(() => {
    if (!chartId) return;
    return () => unregisterChart(chartId);
  }, [chartId]);

  const editCode = useCallback(async () => {
    if (!notebook || state.status !== 'ready' || editingCode) return;
    setEditingCode(true);
    setEditError(null);
    try {
      const generated = await generateChartSource(state.plan.spec);
      notebook.createChartCell({
        source: generated.source,
        chartBlockId: block.id,
        // Use the runtime's resolved spec: a named `dataSource` is now inline,
        // so the script's `inputs["chart"]` is exactly what it draws.
        inputs: { chart: generated.spec ?? state.plan.spec },
        unsupported: generated.unsupported,
      });
    } catch (err) {
      setEditError(err instanceof Error ? err.message : 'The chart code could not be opened.');
    } finally {
      setEditingCode(false);
    }
  }, [block.id, editingCode, notebook, state]);

  const body = (() => {
    if (state.status === 'ready') {
      return (
        <div className="space-y-1">
          {/* The LIVE chart: vector, zoomable, pannable. The drawn picture is
              shown immediately and is the fallback (and the export). */}
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
          {state.plan.notes.length > 0 && (
            <p className="text-[10px] text-muted-foreground/70">{state.plan.notes.join(' ')}</p>
          )}
          {block.quant && (
            <p className="text-[10px] text-muted-foreground/60">
              {block.quant.caption
                || `Computed by the quant engine from ${block.quant.experimentId} · ${block.quant.figure}`}
            </p>
          )}
        </div>
      );
    }
    if (state.status === 'loading') {
      return (
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
      );
    }
    return (
      <div
        className={cn(
          'flex w-full items-center justify-center rounded-xl border border-border/10 px-3 text-center',
          state.status === 'error' && 'border-amber-500/20',
        )}
        style={{ height }}
        data-testid={state.status === 'error' ? 'response-chart-error' : 'response-chart-empty'}
      >
        <p className={cn('text-xs italic', state.status === 'error' ? 'text-amber-500/80' : 'text-muted-foreground/70')}>
          {state.message}
        </p>
      </div>
    );
  })();

  const card = (
    <div
      className={cn('w-full', focused && 'mx-auto flex max-h-full max-w-[1600px] flex-col')}
      // The focus overlay closes on a backdrop click; the chart's own toolbar
      // (and its zoom/reset controls) must not count as a backdrop click.
      onClick={(event) => event.stopPropagation()}
    >
      {focusable && state.status === 'ready' && (
        <div className="mb-1 flex justify-end gap-1">
          {notebook && (
            <button
              type="button"
              onClick={() => void editCode()}
              disabled={editingCode}
              aria-label="Edit code"
              title="Edit the code behind this chart"
              className="flex h-6 w-6 items-center justify-center rounded-md border border-border/50 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-40"
            >
              {editingCode ? <Loader2 size={12} className="animate-spin" /> : <Code size={12} />}
            </button>
          )}
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
      <div className={cn('relative mx-auto w-full', focused ? 'max-w-[1400px]' : 'max-w-[1100px]')}>
        {body}
        {editError && <p className="mt-1 text-[10px] text-amber-400/80">{editError}</p>}
      </div>
    </div>
  );

  if (!focused) return card;

  // The full view is PORTALLED to <body>: inside the chat it would live in the
  // chat's stacking context, so the app's own header (the top bar and the
  // price ribbon) would paint OVER the chart and collide with its toolbar. On
  // <body> the overlay sits above the shell, so the chart's toolbar is clear of
  // the header - and the backdrop stays the same frosted blur it has always
  // been, so the app reads through it.
  if (typeof document === 'undefined') return card;
  return createPortal(
    <div
      className="fixed inset-0 z-[300] flex flex-col bg-black/55 p-4 backdrop-blur-sm"
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
