'use client';

// ── ResponseChart — a chat chart, drawn by EITHER engine ────────────────────
//
// A chart block in an answer can be drawn two ways:
//
//   * `eclipse` — the interactive ECharts chart: a live canvas with a crosshair,
//     a hover tooltip and a legend (the default, unchanged).
//   * `python`  — the picture the Python chart engine (matplotlib) draws in the
//     runtime. The browser asks the engine for the picture and shows the
//     artifact it produced. A flat picture: no pointer interaction, but the
//     chart is the SAME chart the agent's own figures use.
//
// The engine is a user preference (Settings › the toggle on the chart), so
// both paths are always reachable and neither is a second product.
//
// The frosted-glass tooltip recipe lives in `baseChartOption()`; it belongs to
// the ECharts path only — a drawn picture has no tooltip to frost.

import { useCallback, useEffect, useMemo, useState } from 'react';
import * as echarts from 'echarts';
import { useEChart, baseChartOption } from '@/components/screens/portfolio/use-echart';
import { useChartPalette } from '@/lib/chart-palette-store';
import { useDarkScheme } from '@/hooks/use-dark-scheme';
import { buildChartOption, chartHasData, mergeChartOption } from '@/lib/response/chart-option';
import { chartBlockToSpec } from '@/lib/response/chart-spec';
import {
  getChatChartEngine,
  hydrateChatChartEngine,
  setChatChartEngine,
  subscribeChatChartEngine,
  type ChatChartEngine,
} from '@/lib/response/chart-engine';
import {
  registerChart,
  registerChartArtifact,
  unregisterChart,
} from '@/lib/response/chart-registry';
import { renderChart } from '@/lib/harness/charts';
import { downloadUrl } from '@/lib/harness/artifacts-browser';
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

export function ResponseChart({ block, height = 260, className, focusable = true }: ResponseChartProps) {
  const [engine, setEngine] = useState<ChatChartEngine>('eclipse');

  useEffect(() => {
    hydrateChatChartEngine();
    setEngine(getChatChartEngine());
    return subscribeChatChartEngine(setEngine);
  }, []);

  const toggleEngine = useCallback(() => {
    setChatChartEngine(engine === 'eclipse' ? 'python' : 'eclipse');
  }, [engine]);

  const body =
    engine === 'python' ? (
      <PythonChartBody block={block} height={height} />
    ) : (
      <EChartsChartBody block={block} height={height} focusable={focusable} />
    );

  return (
    <div className={cn('relative', className)}>
      {focusable && (
        <div className="mb-1 flex items-center justify-end gap-1">
          <button
            type="button"
            onClick={toggleEngine}
            title={
              engine === 'eclipse'
                ? 'Draw this chart with the Python chart engine'
                : 'Draw this chart interactively (ECharts)'
            }
            aria-label="Change the chart engine"
            className="rounded-md border border-border/50 px-1.5 py-0.5 text-[9px] font-mono font-semibold text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            {engine === 'eclipse' ? 'EC' : 'PY'}
          </button>
        </div>
      )}
      {body}
    </div>
  );
}

// ── The ECharts path (interactive) ──────────────────────────────────────────

function EChartsChartBody({
  block,
  height,
  focusable,
}: {
  block: ChartBlock;
  height: number;
  focusable: boolean;
}) {
  const palette = useChartPalette();
  const isDark = useDarkScheme();
  const [focused, setFocused] = useState(false);
  const colors = useMemo(
    () => ({ primary: palette.lines.primary, series: palette.lines.series }),
    [palette.lines.primary, palette.lines.series],
  );
  const option = useMemo(() => {
    // Merge — never drop the frosted tooltip recipe from `baseChartOption`.
    return mergeChartOption(baseChartOption(), buildChartOption(block, colors, isDark));
  }, [block, colors, isDark]);
  const empty = !chartHasData(block);
  const ref = useEChart(() => option, [option]);

  const close = useCallback(() => setFocused(false), []);

  useEffect(() => {
    if (!focused) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [focused, close]);

  // Expose the live instance to the export helpers (PNG / PDF) by block id.
  useEffect(() => {
    const id = block.id;
    if (!id) return;
    const el = ref.current;
    const instance = el ? echarts.getInstanceByDom(el) : undefined;
    if (instance) registerChart(id, instance);
    return () => unregisterChart(id);
  }, [block.id, option, ref]);

  if (empty) {
    return (
      <div
        className="glass-card-subtle flex items-center justify-center rounded-xl p-3"
        style={{ height }}
      >
        <p className="text-xs italic text-muted-foreground/70">No data series available to chart.</p>
      </div>
    );
  }

  const card = (
    <div
      className={cn(
        'glass-card-subtle rounded-xl p-3',
        focused && 'w-full max-w-[1400px] shadow-2xl',
      )}
      onClick={focused ? (event) => event.stopPropagation() : undefined}
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
              onClick={close}
              aria-label="Close focus view"
              className="flex h-6 w-6 items-center justify-center rounded-md border border-border/50 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <X size={12} />
            </button>
          )}
        </div>
      )}
      <div ref={ref} className="w-full" style={{ height: focused ? 'min(78vh, 900px)' : height }} />
    </div>
  );

  if (!focused) return card;

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/55 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={block.title ? `Chart: ${block.title}` : 'Chart focus view'}
      onClick={close}
    >
      {card}
    </div>
  );
}

// ── The Python path (a drawn picture) ────────────────────────────────────────

type PythonState =
  | { status: 'loading' }
  | { status: 'ready'; src: string }
  | { status: 'error'; message: string };

function PythonChartBody({ block, height }: { block: ChartBlock; height: number }) {
  const [state, setState] = useState<PythonState>({ status: 'loading' });
  const [focused, setFocused] = useState(false);

  const plan = useMemo(
    () => chartBlockToSpec(block, { theme: 'eclipse-dark' }),
    [block],
  );
  const specKey = useMemo(() => (plan ? JSON.stringify(plan.spec) : ''), [plan]);

  useEffect(() => {
    if (!plan) return;
    const id = block.id;
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
        if (id) registerChartArtifact(id, artifactId);
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

  if (!plan) {
    return (
      <div
        className="glass-card-subtle flex items-center justify-center rounded-xl p-3"
        style={{ height }}
      >
        <p className="text-xs italic text-muted-foreground/70">No data series available to chart.</p>
      </div>
    );
  }

  if (state.status === 'error') {
    return (
      <div
        className="glass-card-subtle flex items-center justify-center rounded-xl p-3 text-center"
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
