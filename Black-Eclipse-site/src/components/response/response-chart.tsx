'use client';

// ── ResponseChart — lazily-loaded ECharts binding ─────────────────────────────
// The only place in the response engine that pulls in ECharts. It is imported
// via `next/dynamic({ ssr: false })` from the chart block so the ~1MB library
// is only fetched when a response actually contains a chart.

import { useEffect, useMemo } from 'react';
import * as echarts from 'echarts';
import { useEChart, baseChartOption } from '@/components/screens/portfolio/use-echart';
import { useChartPalette } from '@/lib/chart-palette-store';
import { buildChartOption, chartHasData } from '@/lib/response/chart-option';
import { registerChart, unregisterChart } from '@/lib/response/chart-registry';
import type { ChartBlock } from '@/lib/response/contract';
import { cn } from '@/lib/utils';

export interface ResponseChartProps {
  block: ChartBlock;
  height?: number;
  className?: string;
}

export function ResponseChart({ block, height = 260, className }: ResponseChartProps) {
  const palette = useChartPalette();
  const colors = useMemo(
    () => ({ primary: palette.lines.primary, series: palette.lines.series }),
    [palette.lines.primary, palette.lines.series],
  );
  const option = useMemo(
    () => ({ ...baseChartOption(), ...buildChartOption(block, colors) }),
    [block, colors],
  );
  const empty = !chartHasData(block);
  const ref = useEChart(() => option, [option]);

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
        className={cn('flex items-center justify-center rounded-xl border border-white/10 bg-accent/10', className)}
        style={{ height }}
      >
        <p className="text-xs italic text-muted-foreground/70">No data series available to chart.</p>
      </div>
    );
  }

  return <div ref={ref} className={cn('w-full', className)} style={{ height }} />;
}

export default ResponseChart;
