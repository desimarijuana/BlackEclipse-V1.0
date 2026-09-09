'use client';

// ── EChartsContainer — reusable BlackEclipse chart shell ─────────────────────
// Wraps the existing useEChart binding with consistent loading / empty / error
// states and a shared dark-theme base option. All journal charts render
// through this so typography, tooltips, grid and axis styling stay uniform.

import React from 'react';
import * as echarts from 'echarts';
import type { EChartsOption } from 'echarts';
import { useEChart, baseChartOption } from '@/components/screens/portfolio/use-echart';
import { cssVarToHex } from '@/lib/chart-colors';
import { cn } from '@/lib/utils';

export interface EChartsContainerProps {
  option: EChartsOption | null;
  deps?: unknown[];
  height?: number | string;
  className?: string;
  loading?: boolean;
  empty?: boolean;
  emptyText?: string;
  title?: string;
  hint?: string;
}

/** Shared axis/grid styling matching the terminal's frosted look. */
export function journalBaseOption(): EChartsOption {
  const primary = cssVarToHex('--primary', '#7aff78');
  return {
    ...baseChartOption(),
    grid: { left: 8, right: 8, top: 20, bottom: 0, containLabel: true },
    xAxis: {
      type: 'category',
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#7a7a7a', fontSize: 10, fontFamily: 'monospace' },
    },
    yAxis: {
      type: 'value',
      scale: true,
      splitLine: { show: false },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#7a7a7a', fontSize: 10, fontFamily: 'monospace' },
    },
    color: [primary, '#60a5fa', '#fbbf24', '#f472b6', '#a78bfa', '#2dd4bf', '#fb7185', '#f97316'],
  } as EChartsOption;
}

export function EChartsContainer({
  option,
  deps = [],
  height = 240,
  className,
  loading = false,
  empty = false,
  emptyText = 'No data yet',
  title,
  hint,
}: EChartsContainerProps) {
  const ref = useEChart(() => option, deps);

  return (
    <div className={cn('flex flex-col', className)}>
      {(title || hint) && (
        <div className="mb-2 flex items-center justify-between gap-2">
          {title && <h3 className="font-serif text-sm font-semibold text-foreground truncate">{title}</h3>}
          {hint && <span className="font-mono text-[9px] text-muted-foreground/70 shrink-0">{hint}</span>}
        </div>
      )}
      <div className="relative" style={{ height }}>
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-background/40">
            <span className="h-5 w-5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-primary" />
          </div>
        )}
        {empty && !loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center">
            <p className="text-xs text-muted-foreground/70 italic">{emptyText}</p>
          </div>
        )}
        {!empty && <div ref={ref} className="h-full w-full" />}
      </div>
    </div>
  );
}

/** Format an R value with sign, e.g. +2.4R. */
export function fmtR(v: number): string {
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}R`;
}

/** Format a currency value compactly. */
export function fmtMoney(v: number): string {
  const abs = Math.abs(v);
  const sign = v < 0 ? '-' : v > 0 ? '+' : '';
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(1)}K`;
  return `${sign}$${abs.toFixed(2)}`;
}

export { echarts };
