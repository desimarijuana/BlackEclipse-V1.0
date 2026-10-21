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
// What a drawn picture cannot do, stated plainly: there is no hover tooltip
// and no crosshair. The values live in the block's own table/text, and the
// picture is the picture.

import { useEffect, useMemo, useState } from 'react';
import { downloadUrl } from '@/lib/harness/artifacts-browser';
import { renderChart } from '@/lib/harness/charts';
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
  | { status: 'ready'; src: string }
  | { status: 'error'; message: string };

export function ResponseChart({ block, height = 260, className, focusable = true }: ResponseChartProps) {
  const [state, setState] = useState<State>({ status: 'loading' });
  const [focused, setFocused] = useState(false);

  const plan = useMemo(
    () => chartBlockToSpec(block, { theme: 'eclipse-dark' }),
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
        setState({ status: 'ready', src: downloadUrl(artifactId) });
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
        'glass-card-subtle rounded-xl p-3',
        focused && 'w-full max-w-[1400px] shadow-2xl',
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
        <>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={state.src}
            alt={block.title ?? 'Chart'}
            className="w-full"
            style={focused ? { maxHeight: '78vh' } : { maxHeight: height }}
            data-testid="response-chart-image"
          />
          {plan.notes.length > 0 && (
            <p className="mt-1 text-[10px] text-muted-foreground/70">{plan.notes.join(' ')}</p>
          )}
        </>
      ) : (
        <div className="w-full animate-pulse" style={{ height }} aria-busy="true" />
      )}
    </div>
  );

  if (!focused) return card;

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/55 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={block.title ? `Chart: ${block.title}` : 'Chart focus view'}
      onClick={() => setFocused(false)}
    >
      {card}
    </div>
  );
}

export default ResponseChart;
