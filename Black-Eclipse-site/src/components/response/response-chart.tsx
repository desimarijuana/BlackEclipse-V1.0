'use client';

// ── ResponseChart — lazily-loaded ECharts binding ─────────────────────────────
// The only place in the response engine that pulls in ECharts. It is imported
// via `next/dynamic({ ssr: false })` from the chart block so the ~1MB library
// is only fetched when a response actually contains a chart.
//
// Focus mode enlarges the SAME chart instance into a fixed overlay instead of
// mounting a second ECharts canvas: the ResizeObserver in `useEChart` notices
// the container change and resizes, so the focused view is the live chart.

import { useCallback, useEffect, useMemo, useState } from 'react';
import * as echarts from 'echarts';
import { useEChart, baseChartOption } from '@/components/screens/portfolio/use-echart';
import { useChartPalette } from '@/lib/chart-palette-store';
import { useDarkScheme } from '@/hooks/use-dark-scheme';
import { buildChartOption, chartHasData, mergeChartOption } from '@/lib/response/chart-option';
import { registerChart, unregisterChart } from '@/lib/response/chart-registry';
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
        className={cn('glass-card-subtle flex items-center justify-center rounded-xl p-3', className)}
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
        !focused && className,
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

export default ResponseChart;
